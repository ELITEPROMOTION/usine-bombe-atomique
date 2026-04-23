"""V5.4 AJOUT CLAUDE 7 - Cognitive Health Monitor.

Compare semaine N vs semaine N-1. Alerte regression.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg


REGRESSION_THRESHOLD = 0.05   # 5% delta


async def weekly_scores(
    pool: asyncpg.Pool, family: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        sql = (
            "SELECT AVG(score_0_100) AS avg_score, COUNT(*) AS n "
            "FROM cognitive_benchmarks "
            "WHERE ran_at >= $1 AND ran_at < $2"
        )
        args = [now - timedelta(days=7), now]
        if family:
            sql += " AND family = $3"
            args.append(family)
        cur = await conn.fetchrow(sql, *args)
        args_prev = [now - timedelta(days=14), now - timedelta(days=7)]
        if family:
            args_prev.append(family)
        prev = await conn.fetchrow(sql, *args_prev)
    cur_avg = float(cur["avg_score"] or 0) if cur else 0
    prev_avg = float(prev["avg_score"] or 0) if prev else 0
    delta = cur_avg - prev_avg
    regression = delta < -REGRESSION_THRESHOLD * 100   # 5 points/100
    return {
        "current_week_avg": round(cur_avg, 2),
        "previous_week_avg": round(prev_avg, 2),
        "delta": round(delta, 2),
        "regression_detected": regression,
        "family": family or "all",
        "current_samples": int(cur["n"] or 0) if cur else 0,
        "previous_samples": int(prev["n"] or 0) if prev else 0,
    }


async def health_report(pool: asyncpg.Pool) -> dict[str, Any]:
    families = ["logic", "mathematical", "coding",
                "reasoning_heavy", "compliance"]
    out: dict[str, Any] = {}
    for f in families:
        out[f] = await weekly_scores(pool, family=f)
    overall = await weekly_scores(pool, family=None)
    return {"overall": overall, "by_family": out}
