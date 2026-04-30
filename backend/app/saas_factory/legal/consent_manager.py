"""ConsentManager : record + query consents (GDPR Art 6.1.a).

Chaque consentement est enregistre avec :
- owner_email (PII pseudonymisee via SHA-256 lookup)
- scope (TOS / privacy / cookie_analytics / marketing / etc.)
- doc_version (version du document accepte au moment du consent)
- ip_hash (SHA-256 IP pour traçabilite)
- accepted_at + revoked_at

GDPR Art 7.3 : "le retrait du consentement doit etre aussi simple que
l'octroi". `revoke_consent` est l'inverse exact de `record_consent`.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.legal.types import ConsentScope

logger = logging.getLogger(__name__)


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


class ConsentAlreadyRecordedError(RuntimeError):
    """Tentative de re-recorder un consent deja actif (idempotency)."""


@dataclass(frozen=True)
class ConsentRecord:
    consent_id: UUID
    owner_email: str
    scope: ConsentScope
    doc_version: str
    accepted_at: datetime
    revoked_at: datetime | None
    ip_hash: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class ConsentManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_consent(
        self,
        *,
        owner_email: str,
        scope: ConsentScope,
        doc_version: str,
        ip: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConsentRecord:
        """Enregistre un nouveau consent. Echoue si actif deja existant."""
        if not owner_email or "@" not in owner_email:
            raise ValueError("owner_email invalide")
        if not doc_version:
            raise ValueError("doc_version requis")

        import json
        meta_json = json.dumps(metadata or {}, sort_keys=True,
                               ensure_ascii=False, default=str)

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT consent_id FROM user_consents
                 WHERE owner_email = $1 AND scope = $2
                   AND revoked_at IS NULL
                """,
                owner_email.lower(), scope.value,
            )
            if existing is not None:
                raise ConsentAlreadyRecordedError(
                    f"consent actif deja existant pour "
                    f"{owner_email}/{scope.value}",
                )

            row = await conn.fetchrow(
                """
                INSERT INTO user_consents (
                    owner_email, scope, doc_version, ip_hash, metadata_json
                ) VALUES ($1, $2, $3, $4, $5::jsonb)
                RETURNING consent_id, accepted_at
                """,
                owner_email.lower(), scope.value, doc_version,
                _hash_ip(ip), meta_json,
            )

        logger.info(
            "consent.recorded scope=%s email=%s version=%s",
            scope.value, owner_email, doc_version,
        )
        return ConsentRecord(
            consent_id=row["consent_id"],
            owner_email=owner_email.lower(),
            scope=scope,
            doc_version=doc_version,
            accepted_at=row["accepted_at"],
            revoked_at=None,
            ip_hash=_hash_ip(ip),
            metadata=metadata or {},
        )

    async def revoke_consent(
        self,
        *,
        owner_email: str,
        scope: ConsentScope,
        reason: str = "user_request",
    ) -> bool:
        """GDPR Art 7.3 : retrait aussi simple que l'octroi."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE user_consents
                   SET revoked_at = NOW(),
                       revocation_reason = $3
                 WHERE owner_email = $1 AND scope = $2
                   AND revoked_at IS NULL
                RETURNING consent_id
                """,
                owner_email.lower(), scope.value, reason[:200],
            )
        if row is None:
            return False
        logger.info(
            "consent.revoked scope=%s email=%s reason=%s",
            scope.value, owner_email, reason[:80],
        )
        return True

    async def has_active_consent(
        self,
        *,
        owner_email: str,
        scope: ConsentScope,
    ) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM user_consents
                 WHERE owner_email = $1 AND scope = $2
                   AND revoked_at IS NULL
                """,
                owner_email.lower(), scope.value,
            )
        return row is not None

    async def list_consents(
        self,
        owner_email: str,
        *,
        active_only: bool = False,
    ) -> list[ConsentRecord]:
        async with self._pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch(
                    """
                    SELECT consent_id, owner_email, scope, doc_version,
                           accepted_at, revoked_at, ip_hash, metadata_json
                      FROM user_consents
                     WHERE owner_email = $1 AND revoked_at IS NULL
                     ORDER BY accepted_at DESC
                    """,
                    owner_email.lower(),
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT consent_id, owner_email, scope, doc_version,
                           accepted_at, revoked_at, ip_hash, metadata_json
                      FROM user_consents
                     WHERE owner_email = $1
                     ORDER BY accepted_at DESC
                    """,
                    owner_email.lower(),
                )
        return [_row_to_record(r) for r in rows]


def _row_to_record(row: asyncpg.Record) -> ConsentRecord:
    import json
    meta = row["metadata_json"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    return ConsentRecord(
        consent_id=row["consent_id"],
        owner_email=row["owner_email"],
        scope=ConsentScope(row["scope"]),
        doc_version=row["doc_version"],
        accepted_at=row["accepted_at"],
        revoked_at=row["revoked_at"],
        ip_hash=row["ip_hash"],
        metadata=meta or {},
    )
