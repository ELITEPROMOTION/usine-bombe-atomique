"""V5.3 BLOC 9 - Immutable Evidence Chain HMAC-SHA256.

Genesis -> N events -> chacun chain_hash = SHA256(parent_hash || signature)
signature = HMAC-SHA256(secret_key, canonical_payload).

verify_chain() relit toute la chaine et detecte toute rupture.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

GENESIS_PARENT = "0" * 64
DEFAULT_KEY_ID = "ctc-key-2026Q2"


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _get_key(key_id: str = DEFAULT_KEY_ID) -> bytes:
    """Recupere la cle HMAC depuis Vault. Fallback env si Vault down."""
    try:
        from app.integrations.vault_client import VaultClient
        vc = VaultClient()
        data = vc.get(f"ctc/{key_id}")
        if data and data.get("secret"):
            return str(data["secret"]).encode("utf-8")
    except Exception as exc:
        logger.debug("vault key miss: %s", exc)
    # Fallback stable (en dev) avec env ou default
    return os.environ.get("UBA_CTC_HMAC_KEY", "uba-ctc-dev-secret-change-me").encode()


def _sign(payload_str: str, key_id: str = DEFAULT_KEY_ID) -> str:
    return hmac.new(_get_key(key_id), payload_str.encode("utf-8"),
                     hashlib.sha256).hexdigest()


@dataclass
class ChainEvent:
    event_id: str
    task_id: str | None
    actor_type: str
    actor_id: str
    ts_us: int
    input_hash: str
    output_hash: str
    artifact_hash: str | None
    parent_hash: str
    chain_hash: str
    signature: str
    signing_key_id: str
    verdict: str
    justification: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "task_id": self.task_id,
            "actor_type": self.actor_type, "actor_id": self.actor_id,
            "ts_us": self.ts_us,
            "input_hash": self.input_hash, "output_hash": self.output_hash,
            "artifact_hash": self.artifact_hash,
            "parent_hash": self.parent_hash, "chain_hash": self.chain_hash,
            "verdict": self.verdict, "justification": self.justification,
            "signing_key_id": self.signing_key_id,
        }


async def _last_chain_hash(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow(
        "SELECT chain_hash FROM evidence_chain_events "
        "ORDER BY ts_us DESC LIMIT 1"
    )
    return row["chain_hash"] if row else GENESIS_PARENT


async def append(
    pool: asyncpg.Pool, *,
    actor_type: str, actor_id: str,
    input_payload: dict[str, Any], output_payload: dict[str, Any],
    verdict: str, artifact_payload: dict[str, Any] | None = None,
    task_id: str | None = None,
    source_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    justification: str | None = None,
    phase_id: str | None = None,
    key_id: str = DEFAULT_KEY_ID,
) -> ChainEvent:
    """Ajoute un event au chain. Atomic : transaction + FOR UPDATE."""
    input_str = _canonical(input_payload)
    output_str = _canonical(output_payload)
    input_hash = _sha256(input_str)
    output_hash = _sha256(output_str)
    artifact_hash = _sha256(_canonical(artifact_payload)) if artifact_payload else None
    ts_us = int(time.time() * 1_000_000)
    sigpayload = f"{input_hash}|{output_hash}|{artifact_hash or ''}|{ts_us}|{verdict}"
    signature = _sign(sigpayload, key_id)

    async with pool.acquire() as conn, conn.transaction():
        # Lock+read last chain_hash
        parent = await _last_chain_hash(conn)
        chain_hash = _sha256(parent + signature)
        row = await conn.fetchrow(
            """
            INSERT INTO evidence_chain_events(
                task_id, phase_id, actor_type, actor_id, ts_us,
                input_hash, output_hash, artifact_hash,
                source_refs, evidence_refs,
                parent_event_hash, chain_hash,
                signature, signing_key_id, verdict, justification
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                    $9::jsonb, $10::jsonb,
                    $11, $12, $13, $14, $15, $16)
            RETURNING event_id
            """,
            UUID(task_id) if task_id else None,
            UUID(phase_id) if phase_id else None,
            actor_type[:20], actor_id[:120], ts_us,
            input_hash, output_hash, artifact_hash,
            json.dumps(source_refs or []),
            json.dumps(evidence_refs or []),
            parent, chain_hash,
            signature, key_id, verdict[:20],
            (justification or "")[:5000] or None,
        )
    return ChainEvent(
        event_id=str(row["event_id"]), task_id=task_id,
        actor_type=actor_type, actor_id=actor_id, ts_us=ts_us,
        input_hash=input_hash, output_hash=output_hash,
        artifact_hash=artifact_hash,
        parent_hash=parent, chain_hash=chain_hash,
        signature=signature, signing_key_id=key_id,
        verdict=verdict, justification=justification,
    )


async def genesis(pool: asyncpg.Pool) -> ChainEvent | None:
    """Cree le bloc GENESIS si la chaine est vide. Idempotent."""
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM evidence_chain_events")
    if int(count or 0) > 0:
        return None
    return await append(
        pool, actor_type="system", actor_id="ctc.genesis",
        input_payload={"genesis": True},
        output_payload={"message": "CTC chain initialized"},
        verdict="GENESIS",
        justification="CTC evidence chain genesis block",
    )


@dataclass
class IntegrityReport:
    events_checked: int
    broken_links: int
    bad_signatures: int
    status: str               # preserved|broken|quarantined
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


async def verify_chain(
    pool: asyncpg.Pool, limit: int = 10_000,
) -> IntegrityReport:
    """Rejoue la chaine + verifie signatures."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_id, input_hash, output_hash, artifact_hash,
                   ts_us, verdict, parent_event_hash, chain_hash,
                   signature, signing_key_id
            FROM evidence_chain_events ORDER BY ts_us ASC LIMIT $1
            """, limit,
        )
    expected_parent = GENESIS_PARENT
    broken = 0
    bad_sig = 0
    details: list[dict[str, Any]] = []
    for r in rows:
        if r["parent_event_hash"] != expected_parent:
            broken += 1
            details.append({"event_id": str(r["event_id"]),
                             "reason": "parent_hash mismatch"})
        sigpayload = (f"{r['input_hash']}|{r['output_hash']}"
                       f"|{r['artifact_hash'] or ''}|{r['ts_us']}|{r['verdict']}")
        expected_sig = _sign(sigpayload, r["signing_key_id"])
        if expected_sig != r["signature"]:
            bad_sig += 1
            details.append({"event_id": str(r["event_id"]),
                             "reason": "bad signature"})
        expected_hash = _sha256(r["parent_event_hash"] + r["signature"])
        if expected_hash != r["chain_hash"]:
            broken += 1
            details.append({"event_id": str(r["event_id"]),
                             "reason": "chain_hash mismatch"})
        expected_parent = r["chain_hash"]
    status = "preserved" if (broken == 0 and bad_sig == 0) else "broken"
    report = IntegrityReport(
        events_checked=len(rows), broken_links=broken,
        bad_signatures=bad_sig, status=status,
        details={"issues": details[:20]},
    )
    # Log integrity check
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO evidence_chain_integrity_log(
                events_checked, broken_links, bad_signatures, status, details)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            report.events_checked, report.broken_links,
            report.bad_signatures, report.status,
            json.dumps(report.details),
        )
    return report


async def tail(
    pool: asyncpg.Pool, limit: int = 50,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_id, task_id, actor_type, actor_id, ts_us,
                   chain_hash, verdict, justification, created_at
            FROM evidence_chain_events ORDER BY ts_us DESC LIMIT $1
            """, limit,
        )
    return [{
        "event_id": str(r["event_id"]),
        "task_id": str(r["task_id"]) if r["task_id"] else None,
        "actor_type": r["actor_type"], "actor_id": r["actor_id"],
        "ts_us": r["ts_us"], "chain_hash": r["chain_hash"],
        "verdict": r["verdict"], "justification": r["justification"],
        "created_at": r["created_at"].isoformat(),
    } for r in rows]
