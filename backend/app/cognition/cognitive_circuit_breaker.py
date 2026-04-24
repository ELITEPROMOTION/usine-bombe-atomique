"""V5.4 AJOUT CLAUDE 1 - Cognitive Circuit Breaker.

Seuils kill-switch : duree 5min, tokens 100k, iterations 50, memory 2GB.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

KILL_THRESHOLDS = {
    "timeout_5min": 300,       # seconds
    "tokens_100k": 100_000,
    "iterations_50": 50,
    "memory_2gb": 2 * 1024 * 1024 * 1024,
}


@dataclass
class BreakerState:
    start_time: float
    tokens_used: int = 0
    iterations: int = 0
    memory_bytes: int = 0

    def elapsed_sec(self) -> float:
        return time.perf_counter() - self.start_time


def check(state: BreakerState) -> tuple[bool, str | None]:
    """Retourne (triggered, reason)."""
    if state.elapsed_sec() > KILL_THRESHOLDS["timeout_5min"]:
        return True, "timeout_5min"
    if state.tokens_used > KILL_THRESHOLDS["tokens_100k"]:
        return True, "tokens_100k"
    if state.iterations > KILL_THRESHOLDS["iterations_50"]:
        return True, "iterations_50"
    if state.memory_bytes > KILL_THRESHOLDS["memory_2gb"]:
        return True, "memory_2gb"
    return False, None


async def record_kill(
    pool: asyncpg.Pool, trace_id: str | None, reason: str,
    details: dict[str, Any] | None = None,
) -> int:
    if reason not in KILL_THRESHOLDS and reason not in ("infinite_loop", "stuck_state"):
        raise ValueError(f"unknown kill reason: {reason}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO cognitive_kill_events(trace_id, reason, details)
            VALUES ($1, $2, $3::jsonb)
            RETURNING id
            """,
            UUID(trace_id) if trace_id else None,
            reason,
            json.dumps(details or {}),
        )
    return int(row["id"])


async def recent(
    pool: asyncpg.Pool, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT reason, trace_id, created_at FROM cognitive_kill_events "
            "ORDER BY created_at DESC LIMIT $1", limit,
        )
    return [{
        "reason": r["reason"],
        "trace_id": str(r["trace_id"]) if r["trace_id"] else None,
        "created_at": r["created_at"].isoformat(),
    } for r in rows]
