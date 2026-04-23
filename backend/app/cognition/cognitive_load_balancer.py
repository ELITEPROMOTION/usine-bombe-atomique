"""V5.4 AJOUT CLAUDE 10 - Cognitive Load Balancer.

Pool Arq dedie cognitive_reasoning_worker (separe truth engine).
Distribue raisonnements selon charge/priorite.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg


DEDICATED_QUEUE = "cognitive_reasoning_tasks"
MAX_IN_FLIGHT_PER_TIER = {"P0": 5, "P1": 10, "P2": 20, "P3": 40}


@dataclass
class LoadSnapshot:
    in_flight: int
    queued: int
    budget_tier_counts: dict[str, int]


async def snapshot(pool: asyncpg.Pool) -> dict[str, Any]:
    """Etat approximatif via reasoning_traces.status."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM reasoning_traces "
            "GROUP BY status"
        )
        last_hour = await conn.fetchval(
            "SELECT COUNT(*) FROM reasoning_traces "
            "WHERE created_at >= NOW() - INTERVAL '1 hour'"
        )
    counts = {r["status"]: int(r["n"]) for r in rows}
    return {
        "by_status": counts,
        "last_hour_total": int(last_hour or 0),
        "queue_name": DEDICATED_QUEUE,
        "limits_per_tier": MAX_IN_FLIGHT_PER_TIER,
    }


def pick_worker_for_tier(tier: str) -> str:
    """Retourne le nom de queue/worker pour un tier."""
    return f"{DEDICATED_QUEUE}:{tier.upper()}"


def should_throttle(in_flight: int, tier: str) -> bool:
    limit = MAX_IN_FLIGHT_PER_TIER.get(tier.upper(), 10)
    return in_flight >= limit
