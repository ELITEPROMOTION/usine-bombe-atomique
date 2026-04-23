"""V5.1 BLOC 14 - Correlation ID universel.

Un meme correlation_id suit un artefact de bout-en-bout : ingestion ->
DAG -> validation -> patch -> runtime -> incident. Permet de reconstituer
exactement le cycle de vie d'une decision autonome.

API :
  - new_id(origin) : cree un id + enregistre dans correlation_ledger
  - hop(cid, actor) : incremente le hop_count
  - close(cid, final_verdict) : ferme le correlation trail
  - trace(cid) : reconstitue la frise chronologique (audit + evidence)
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


def new_id(prefix: str = "uba") -> str:
    """Genere un correlation id lisible + aleatoire (ex: uba-ab12cd34ef)."""
    return f"{prefix}-{secrets.token_hex(6)}"


async def register(
    pool: asyncpg.Pool, cid: str, origin: str,
    task_id: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO correlation_ledger(correlation_id, task_id, origin)
            VALUES ($1, $2, $3)
            ON CONFLICT (correlation_id) DO NOTHING
            """,
            cid[:64], UUID(task_id) if task_id else None, origin[:60],
        )


async def hop(pool: asyncpg.Pool, cid: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE correlation_ledger SET hop_count = hop_count + 1 "
            "WHERE correlation_id = $1",
            cid[:64],
        )


async def close(
    pool: asyncpg.Pool, cid: str, final_verdict: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE correlation_ledger SET closed_at = NOW(), "
            "final_verdict = $2 WHERE correlation_id = $1",
            cid[:64], final_verdict[:30],
        )


async def trace(pool: asyncpg.Pool, cid: str) -> dict[str, Any]:
    """Assemble la frise : ledger + evidence + audit + ambiguity + leases."""
    async with pool.acquire() as conn:
        cor = await conn.fetchrow(
            "SELECT * FROM correlation_ledger WHERE correlation_id=$1",
            cid[:64],
        )
        if cor is None:
            return {"correlation_id": cid, "found": False}
        amb = await conn.fetch(
            "SELECT level, kind, resolved, created_at FROM ambiguity_ledger "
            "WHERE correlation_id=$1 ORDER BY created_at ASC",
            cid[:64],
        )
        proofs = await conn.fetch(
            "SELECT form_type, c_sub_type, verdict, reason, created_at "
            "FROM human_necessity_proofs WHERE correlation_id=$1 "
            "ORDER BY created_at ASC",
            cid[:64],
        )
    return {
        "correlation_id": cid,
        "found": True,
        "origin": cor["origin"],
        "task_id": str(cor["task_id"]) if cor["task_id"] else None,
        "opened_at": cor["created_at"].isoformat(),
        "closed_at": cor["closed_at"].isoformat() if cor["closed_at"] else None,
        "final_verdict": cor["final_verdict"],
        "hops": cor["hop_count"],
        "ambiguity_timeline": [_iso(a) for a in amb],
        "necessity_proofs": [_iso(p) for p in proofs],
    }


def _iso(row: Any) -> dict[str, Any]:
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d
