"""Evidence Ledger V4.1 - journal immuable chaine (hash-linked, append-only).

Chaque event contient :
- kind : decision | artifact | test | override | arbiter | contradiction |
         hypothesis | challenger | repair | contract_violation
- payload_hash : SHA-256 du JSON canonique du payload
- prev_hash   : chain_hash de l'event precedent (toute la table)
- chain_hash  : SHA-256(prev_hash || payload_hash)

`verify_chain()` rejoue la chaine et detecte toute alteration.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64


def _canon(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class LedgerEvent:
    event_id: str
    task_id: str | None
    actor: str
    kind: str
    payload_hash: str
    prev_hash: str
    chain_hash: str
    payload: dict[str, Any]


async def record(
    pool: asyncpg.Pool,
    kind: str,
    actor: str,
    payload: dict[str, Any],
    task_id: str | None = None,
) -> str:
    """Ecrit un event et renvoie son `event_id` (UUID)."""
    payload_hash = _sha256(_canon(payload))
    async with pool.acquire() as conn, conn.transaction():
        last = await conn.fetchrow(
            "SELECT chain_hash FROM evidence_ledger ORDER BY id DESC LIMIT 1 FOR UPDATE",
        )
        prev_hash = last["chain_hash"] if last else GENESIS_HASH
        chain_hash = _sha256(prev_hash + payload_hash)
        row = await conn.fetchrow(
            """
            INSERT INTO evidence_ledger
              (task_id, actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            RETURNING event_id
            """,
            UUID(task_id) if task_id else None,
            actor, kind, payload_hash, prev_hash, chain_hash, _canon(payload),
        )
    return str(row["event_id"])


async def verify_chain(pool: asyncpg.Pool, limit: int = 10_000) -> dict[str, Any]:
    """Rejoue toute la chaine et retourne un rapport d'integrite."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, event_id, payload_hash, prev_hash, chain_hash
            FROM evidence_ledger ORDER BY id ASC LIMIT $1
            """, limit,
        )
    broken: list[dict[str, Any]] = []
    expected_prev = GENESIS_HASH
    for r in rows:
        if r["prev_hash"] != expected_prev and r["prev_hash"] != GENESIS_HASH:
            broken.append({"id": r["id"], "reason": "prev_hash mismatch"})
        recomputed = _sha256(r["prev_hash"] + r["payload_hash"])
        if recomputed != r["chain_hash"]:
            broken.append({"id": r["id"], "reason": "chain_hash mismatch"})
        expected_prev = r["chain_hash"]
    return {
        "events_checked": len(rows),
        "broken": broken,
        "integrity_ok": len(broken) == 0,
    }


async def tail(pool: asyncpg.Pool, limit: int = 50) -> list[dict[str, Any]]:
    """Retourne les N derniers events du journal pour l'UI."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_id, task_id, actor, kind, chain_hash, payload_json, created_at
            FROM evidence_ledger ORDER BY id DESC LIMIT $1
            """, limit,
        )
    return [
        {
            "event_id": str(r["event_id"]),
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "actor": r["actor"],
            "kind": r["kind"],
            "chain_hash": r["chain_hash"],
            "payload": r["payload_json"],
            "created_at": r["created_at"].isoformat(),
        } for r in rows
    ]
