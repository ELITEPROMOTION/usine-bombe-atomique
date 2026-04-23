"""V5.4 AJOUT CLAUDE 5 - Cognitive Dependency Graph.

Track quelle trace depend de quelle trace precedente.
Cascade invalidation si parent faux.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def add_dependency(
    pool: asyncpg.Pool, *, parent_trace: str, child_trace: str,
    dependency_type: str = "derives",
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reasoning_dependencies(
                parent_trace, child_trace, dependency_type)
            VALUES ($1, $2, $3)
            """,
            UUID(parent_trace), UUID(child_trace), dependency_type[:30],
        )


async def descendants(
    pool: asyncpg.Pool, trace_id: str, max_depth: int = 10,
) -> list[dict[str, Any]]:
    """Retourne tous les descendants via recursive CTE."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH RECURSIVE chain AS (
                SELECT child_trace, 1 AS depth
                FROM reasoning_dependencies
                WHERE parent_trace = $1::uuid
                UNION ALL
                SELECT r.child_trace, c.depth + 1
                FROM reasoning_dependencies r
                JOIN chain c ON r.parent_trace = c.child_trace
                WHERE c.depth < $2
            )
            SELECT DISTINCT child_trace, depth FROM chain
            """, UUID(trace_id), max_depth,
        )
    return [{"trace_id": str(r["child_trace"]), "depth": r["depth"]}
            for r in rows]


async def invalidate_cascade(
    pool: asyncpg.Pool, trace_id: str,
) -> dict[str, Any]:
    """Marque une trace + tous ses descendants comme 'failed'."""
    desc = await descendants(pool, trace_id)
    ids = [UUID(trace_id)] + [UUID(d["trace_id"]) for d in desc]
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reasoning_traces SET status = 'failed' "
            "WHERE trace_id = ANY($1::uuid[])", ids,
        )
    return {"root": trace_id, "invalidated_count": len(ids),
            "descendants": [d["trace_id"] for d in desc]}


async def ancestors(
    pool: asyncpg.Pool, trace_id: str, max_depth: int = 10,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH RECURSIVE chain AS (
                SELECT parent_trace, 1 AS depth
                FROM reasoning_dependencies
                WHERE child_trace = $1::uuid
                UNION ALL
                SELECT r.parent_trace, c.depth + 1
                FROM reasoning_dependencies r
                JOIN chain c ON r.child_trace = c.parent_trace
                WHERE c.depth < $2
            )
            SELECT DISTINCT parent_trace, depth FROM chain
            """, UUID(trace_id), max_depth,
        )
    return [{"trace_id": str(r["parent_trace"]), "depth": r["depth"]}
            for r in rows]
