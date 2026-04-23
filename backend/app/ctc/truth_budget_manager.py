"""V5.3 BLOC 15 - Truth Budget Manager.

Budgets par couche + circuit breakers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


LAYER_BUDGETS_SEC = {
    "1_source_trust": 5,
    "2_assertion_extraction": 10,
    "3_cross_source_triangulation": 30,
    "4_deterministic_validation": 60,
    "5_artifact_binding": 10,
    "6_truth_judgment": 15,
    "7_continuous_enforcement": 10,
}

# Token budget par verification (Anthropic Sonnet pricing)
MAX_TOKENS_PER_TRIANGULATION = 50_000
TOKEN_COST_PER_1M_IN = 3.0
TOKEN_COST_PER_1M_OUT = 15.0
DAILY_COST_BUDGET_USD = 100.0

# Circuit breaker thresholds
CB_FAIL_THRESHOLD = 3
CB_WINDOW_SECONDS = 3600   # 1h


@dataclass
class BudgetCheck:
    ok: bool
    reason: str
    degraded_mode: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def check_latency_budget(layer: str, elapsed_sec: float) -> BudgetCheck:
    limit = LAYER_BUDGETS_SEC.get(layer, 30)
    if elapsed_sec <= limit:
        return BudgetCheck(True, "within budget", False,
                            {"limit": limit, "used": elapsed_sec})
    return BudgetCheck(False, f"{layer} exceeded {limit}s (was {elapsed_sec:.1f}s)",
                        True, {"limit": limit, "used": elapsed_sec})


def check_token_budget(tokens_in: int, tokens_out: int) -> BudgetCheck:
    total = tokens_in + tokens_out
    if total <= MAX_TOKENS_PER_TRIANGULATION:
        cost = (tokens_in / 1e6) * TOKEN_COST_PER_1M_IN + \
               (tokens_out / 1e6) * TOKEN_COST_PER_1M_OUT
        return BudgetCheck(True, "within token budget", False,
                            {"tokens_total": total, "cost_usd": round(cost, 4)})
    return BudgetCheck(False, f"token budget exceeded ({total} > "
                                f"{MAX_TOKENS_PER_TRIANGULATION})",
                        True, {"tokens_total": total})


async def record_usage(
    pool: asyncpg.Pool, *,
    layer: str, tokens_used: int = 0, latency_ms: int = 0,
    cost_usd: float = 0.0, degraded: bool = False,
    details: dict[str, Any] | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO truth_budget_usage(
                layer, tokens_used, latency_ms, cost_usd, degraded_mode, details)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            """,
            layer[:40], tokens_used, latency_ms, cost_usd, degraded,
            __import__("json").dumps(details or {}),
        )


async def daily_cost(pool: asyncpg.Pool) -> float:
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM truth_budget_usage "
            "WHERE recorded_at >= NOW() - INTERVAL '1 day'"
        )
    return float(val or 0)


async def check_daily_budget(pool: asyncpg.Pool) -> BudgetCheck:
    cost = await daily_cost(pool)
    if cost <= DAILY_COST_BUDGET_USD:
        return BudgetCheck(True, f"daily cost {cost:.2f} <= {DAILY_COST_BUDGET_USD}",
                            False, {"cost_usd": cost})
    return BudgetCheck(False, f"daily cost {cost:.2f} > {DAILY_COST_BUDGET_USD}",
                        True, {"cost_usd": cost})


async def circuit_state(pool: asyncpg.Pool, source_id: str) -> str:
    """Retourne l'etat du circuit pour une source : closed | half_open | open."""
    from uuid import UUID
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE error IS NOT NULL) AS fails
            FROM evidence_harvesting_log
            WHERE source_id = $1
              AND fetched_at >= NOW() - ($2 || ' seconds')::INTERVAL
            """, UUID(source_id), str(CB_WINDOW_SECONDS),
        )
    fails = int(row["fails"] or 0) if row else 0
    if fails >= CB_FAIL_THRESHOLD:
        return "open"
    if fails > 0:
        return "half_open"
    return "closed"
