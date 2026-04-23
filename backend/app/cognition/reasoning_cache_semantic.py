"""V5.4 AJOUT CLAUDE 2 - Reasoning Cache Semantic.

V1 : cache strict par fingerprint. V2 ajoutera pgvector / cosine.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.cognition import reasoning_fingerprint

logger = logging.getLogger(__name__)


def _hash(text: str) -> str:
    return reasoning_fingerprint.fingerprint(text, [])


async def lookup(
    pool: asyncpg.Pool, problem_statement: str,
) -> dict[str, Any] | None:
    h = _hash(problem_statement)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cache_id, final_answer, confidence, hit_count,
                   expires_at, original_trace_id
            FROM reasoning_cache WHERE problem_hash = $1
              AND expires_at > NOW()
            """, h,
        )
    if not row:
        return None
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reasoning_cache SET hit_count = hit_count + 1 "
            "WHERE cache_id = $1", row["cache_id"],
        )
    final_answer = row["final_answer"]
    if isinstance(final_answer, str):
        try:
            final_answer = json.loads(final_answer)
        except json.JSONDecodeError:
                logger.debug("json decode skipped") if "logger" in globals() else None
    return {
        "cache_id": str(row["cache_id"]),
        "final_answer": final_answer,
        "confidence": float(row["confidence"] or 0),
        "hit_count": row["hit_count"],
        "expires_at": row["expires_at"].isoformat(),
        "original_trace_id": str(row["original_trace_id"])
            if row["original_trace_id"] else None,
    }


async def store(
    pool: asyncpg.Pool, *, problem_statement: str,
    final_answer: Any, confidence: float,
    trace_id: str | None = None,
) -> str:
    h = _hash(problem_statement)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO reasoning_cache(problem_hash, problem_statement,
                final_answer, confidence, original_trace_id)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            ON CONFLICT (problem_hash) DO UPDATE SET
              final_answer = EXCLUDED.final_answer,
              confidence = EXCLUDED.confidence,
              original_trace_id = EXCLUDED.original_trace_id,
              expires_at = NOW() + INTERVAL '7 days'
            RETURNING cache_id
            """,
            h, problem_statement[:4000], json.dumps(final_answer),
            confidence,
            UUID(trace_id) if trace_id else None,
        )
    return str(row["cache_id"])


async def invalidate_all(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE reasoning_cache SET expires_at = NOW() "
            "WHERE expires_at > NOW()"
        )
    try:
        return int(result.split()[-1])
    except Exception:
        return 0


async def stats(pool: asyncpg.Pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM reasoning_cache")
        active = await conn.fetchval(
            "SELECT COUNT(*) FROM reasoning_cache WHERE expires_at > NOW()")
        hits = await conn.fetchval(
            "SELECT COALESCE(SUM(hit_count), 0) FROM reasoning_cache")
    return {
        "total_entries": int(total or 0),
        "active_entries": int(active or 0),
        "total_hits": int(hits or 0),
    }
