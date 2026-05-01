"""Module C : moteur de mandats numeriques eIDAS Article 26.

Chaque mandat est sceelle dans une chaine de hash SHA-256 (chain_hash =
sha256(prev_hash || payload_hash)) qui rend toute alteration retroactive
detectable. La revocation est elle-meme un maillon de la chaine, jamais une
mutation : aucune ligne n'est UPDATE-ee, on append un evenement de revocation
au champ `audit_log`.

Persistance : table `mandates` (migration 044).
"""
from __future__ import annotations

import enum
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

ZERO_HASH = "0" * 64


class MandateType(str, enum.Enum):
    ACCOUNT_CREATION = "account_creation"
    SUB_AUTHORIZATION = "sub_authorization"
    DATA_PROCESSING = "data_processing"
    PAYMENT_AUTHORIZATION = "payment_authorization"


@dataclass
class Mandate:
    mandate_id: UUID
    mandate_type: MandateType
    principal_id: str
    agent_identity: str
    scope: dict[str, Any]
    payload_hash: str
    prev_hash: str
    chain_hash: str
    signed_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return not (
            self.expires_at is not None and self.expires_at <= datetime.now(UTC)
        )


def _canon(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _compute_payload_hash(
    *,
    mandate_type: MandateType,
    principal_id: str,
    agent_identity: str,
    scope: dict[str, Any],
    signed_at: datetime,
) -> str:
    return _sha256(
        _canon(
            {
                "mandate_type": mandate_type.value,
                "principal_id": principal_id,
                "agent_identity": agent_identity,
                "scope": scope,
                "signed_at": signed_at.isoformat(),
            }
        )
    )


def _compute_chain_hash(prev_hash: str, payload_hash: str) -> str:
    return _sha256(prev_hash + payload_hash)


class MandateEngine:
    """API minimale pour creer / lire / revoquer / verifier des mandats."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _last_chain_hash(self, conn: asyncpg.Connection) -> str:
        row = await conn.fetchrow(
            "SELECT chain_hash FROM mandates ORDER BY id DESC LIMIT 1"
        )
        return row["chain_hash"] if row else ZERO_HASH

    async def issue(
        self,
        *,
        mandate_type: MandateType,
        principal_id: str,
        agent_identity: str,
        scope: dict[str, Any],
        ttl: timedelta | None = None,
    ) -> Mandate:
        signed_at = datetime.now(UTC)
        expires_at = signed_at + ttl if ttl else None

        payload_hash = _compute_payload_hash(
            mandate_type=mandate_type,
            principal_id=principal_id,
            agent_identity=agent_identity,
            scope=scope,
            signed_at=signed_at,
        )

        async with self._pool.acquire() as conn, conn.transaction():
            prev_hash = await self._last_chain_hash(conn)
            chain_hash = _compute_chain_hash(prev_hash, payload_hash)

            audit_entry = {
                "event": "issued",
                "at": signed_at.isoformat(),
                "agent": agent_identity,
            }

            row = await conn.fetchrow(
                """
                INSERT INTO mandates (
                    mandate_type, principal_id, agent_identity,
                    scope_json, payload_hash, prev_hash, chain_hash,
                    signed_at, expires_at, audit_log
                ) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10::jsonb)
                RETURNING mandate_id, signed_at
                """,
                mandate_type.value,
                principal_id,
                agent_identity,
                _canon(scope),
                payload_hash,
                prev_hash,
                chain_hash,
                signed_at,
                expires_at,
                _canon([audit_entry]),
            )

        logger.info(
            "mandate.issued type=%s principal=%s chain=%s...",
            mandate_type.value,
            principal_id,
            chain_hash[:12],
        )

        return Mandate(
            mandate_id=row["mandate_id"],
            mandate_type=mandate_type,
            principal_id=principal_id,
            agent_identity=agent_identity,
            scope=scope,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
            chain_hash=chain_hash,
            signed_at=row["signed_at"],
            expires_at=expires_at,
            revoked_at=None,
            revocation_reason=None,
            audit_log=[audit_entry],
        )

    async def revoke(self, mandate_id: UUID, reason: str) -> Mandate:
        revoked_at = datetime.now(UTC)
        revocation_entry = {
            "event": "revoked",
            "at": revoked_at.isoformat(),
            "reason": reason[:500],
        }

        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE mandates
                   SET revoked_at = $2,
                       revocation_reason = $3,
                       audit_log = audit_log || $4::jsonb
                 WHERE mandate_id = $1 AND revoked_at IS NULL
                RETURNING *
                """,
                mandate_id,
                revoked_at,
                reason[:500],
                _canon([revocation_entry]),
            )

        if row is None:
            raise LookupError(f"mandate {mandate_id} introuvable ou deja revoque")

        logger.info("mandate.revoked id=%s reason=%s", mandate_id, reason[:80])
        return _row_to_mandate(row)

    async def get(self, mandate_id: UUID) -> Mandate | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM mandates WHERE mandate_id = $1", mandate_id
            )
        return _row_to_mandate(row) if row else None

    async def verify_chain(self, *, limit: int | None = None) -> dict[str, Any]:
        """Recalcule la chaine de bout en bout. Detecte toute alteration."""
        async with self._pool.acquire() as conn:
            sql = (
                "SELECT id, payload_hash, prev_hash, chain_hash "
                "FROM mandates ORDER BY id ASC"
            )
            if limit is not None:
                sql += f" LIMIT {int(limit)}"
            rows = await conn.fetch(sql)

        if not rows:
            return {"valid": True, "checked": 0, "first_break": None}

        prev = ZERO_HASH
        for r in rows:
            expected = _compute_chain_hash(prev, r["payload_hash"])
            if expected != r["chain_hash"] or r["prev_hash"] != prev:
                return {
                    "valid": False,
                    "checked": int(r["id"]),
                    "first_break": int(r["id"]),
                    "expected": expected,
                    "actual": r["chain_hash"],
                }
            prev = r["chain_hash"]

        return {"valid": True, "checked": len(rows), "first_break": None}


def _row_to_mandate(row: asyncpg.Record) -> Mandate:
    audit_raw = row["audit_log"]
    if isinstance(audit_raw, str):
        audit_raw = json.loads(audit_raw)
    scope_raw = row["scope_json"]
    if isinstance(scope_raw, str):
        scope_raw = json.loads(scope_raw)

    return Mandate(
        mandate_id=row["mandate_id"],
        mandate_type=MandateType(row["mandate_type"]),
        principal_id=row["principal_id"],
        agent_identity=row["agent_identity"],
        scope=scope_raw or {},
        payload_hash=row["payload_hash"],
        prev_hash=row["prev_hash"],
        chain_hash=row["chain_hash"],
        signed_at=row["signed_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        revocation_reason=row["revocation_reason"],
        audit_log=audit_raw or [],
    )


# --- helpers exposes pour les tests (purs, sans DB) ---
__all__ = [
    "Mandate",
    "MandateEngine",
    "MandateType",
    "ZERO_HASH",
    "_compute_chain_hash",
    "_compute_payload_hash",
]
