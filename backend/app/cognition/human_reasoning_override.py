"""V5.4 AJOUT CLAUDE 8 - Human Reasoning Override.

Ahmed peut forcer decision contraire systeme avec justification min 50 chars.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

MIN_JUSTIFICATION_LEN = 50


async def override_reasoning(
    pool: asyncpg.Pool, *,
    trace_id: str, human_id: str, new_decision: dict[str, Any],
    justification: str, impact_level: str = "medium",
) -> int:
    if len(justification.strip()) < MIN_JUSTIFICATION_LEN:
        raise ValueError(
            f"justification too short ({len(justification)} < {MIN_JUSTIFICATION_LEN})")
    import json as _j
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO cognitive_human_overrides(
                trace_id, human_id, new_decision, justification, impact_level)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            RETURNING id
            """,
            UUID(trace_id), human_id[:120],
            _j.dumps(new_decision), justification, impact_level[:20],
        )
    return int(row["id"])


async def list_overrides(
    pool: asyncpg.Pool, limit: int = 20,
) -> list[dict[str, Any]]:
    import json as _j
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, trace_id, human_id, new_decision, justification,
                   impact_level, created_at
            FROM cognitive_human_overrides
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    out = []
    for r in rows:
        nd = r["new_decision"]
        if isinstance(nd, str):
            try:
                nd = _j.loads(nd)
            except _j.JSONDecodeError:
                pass
        out.append({
            "id": r["id"],
            "trace_id": str(r["trace_id"]) if r["trace_id"] else None,
            "human_id": r["human_id"], "new_decision": nd,
            "justification": r["justification"][:200],
            "impact_level": r["impact_level"],
            "created_at": r["created_at"].isoformat(),
        })
    return out
