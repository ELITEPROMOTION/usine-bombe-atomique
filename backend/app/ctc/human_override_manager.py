"""V5.3 BLOC 17 - Human Override Manager.

Toute override humaine est tracee + liee a un evidence_chain_event.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.ctc import evidence_chain

logger = logging.getLogger(__name__)


async def override(
    pool: asyncpg.Pool, *,
    original_verdict_id: str | None,
    new_verdict: str, justification: str, human_id: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    if not justification or len(justification.strip()) < 20:
        raise ValueError("justification requise (min 20 chars)")
    # Append evidence_chain_event
    ev = await evidence_chain.append(
        pool, actor_type="human", actor_id=human_id[:120],
        input_payload={"original_verdict_id": original_verdict_id,
                        "new_verdict": new_verdict},
        output_payload={"justification": justification[:500]},
        verdict=new_verdict,
        task_id=task_id,
        justification=f"human_override by {human_id}: {justification[:200]}",
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO human_overrides(original_verdict_id, new_verdict,
                justification, human_id, evidence_chain_event_id, status)
            VALUES ($1, $2, $3, $4, $5, 'active')
            RETURNING override_id
            """,
            UUID(original_verdict_id) if original_verdict_id else None,
            new_verdict[:30], justification[:2000], human_id[:120],
            UUID(ev.event_id),
        )
    return {
        "override_id": str(row["override_id"]),
        "evidence_chain_event_id": ev.event_id,
        "new_verdict": new_verdict,
    }


async def list_active(
    pool: asyncpg.Pool, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT override_id, original_verdict_id, new_verdict,
                   justification, human_id, status, created_at
            FROM human_overrides WHERE status = 'active'
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    return [{
        "override_id": str(r["override_id"]),
        "original_verdict_id": str(r["original_verdict_id"])
            if r["original_verdict_id"] else None,
        "new_verdict": r["new_verdict"],
        "justification": r["justification"][:200],
        "human_id": r["human_id"], "status": r["status"],
        "created_at": r["created_at"].isoformat(),
    } for r in rows]


async def revoke(pool: asyncpg.Pool, override_id: str) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE human_overrides SET status = 'revoked' "
            "WHERE override_id = $1 AND status = 'active'",
            UUID(override_id),
        )
    return result.endswith("1")
