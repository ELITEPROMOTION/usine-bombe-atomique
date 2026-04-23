"""V4.8 BLOC 3 - Meta-optimiseur.

Cliche hebdomadaire des metriques systeme. Si une metrique se degrade vs
baseline, declenche `self_improver` automatiquement et logge l'evenement.

Metriques suivies :
- projects_last_7d        : volume
- avg_duration_ms         : vitesse
- rework_rate             : qualite (fail / total)
- avg_cost_usd            : cout LLM
- verdict_distribution    : PASS / CONDITIONAL / SOFT / HARD
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.orchestration import audit_events, self_improver

logger = logging.getLogger(__name__)


DEGRADATION_THRESHOLDS = {
    "avg_duration_ms": 1.30,   # +30% vs precedent snapshot = degradation
    "rework_rate":     1.25,
    "avg_cost_usd":    1.40,
}


@dataclass
class MetaSnapshot:
    projects_last_7d: int
    avg_duration_ms: int
    rework_rate: float
    avg_cost_usd: float
    verdict_distribution: dict[str, int]
    degraded_metrics: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "projects_last_7d": self.projects_last_7d,
            "avg_duration_ms": self.avg_duration_ms,
            "rework_rate": round(self.rework_rate, 4),
            "avg_cost_usd": round(self.avg_cost_usd, 6),
            "verdict_distribution": self.verdict_distribution,
            "degraded_metrics": self.degraded_metrics,
        }


async def _load_current(pool: asyncpg.Pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n,
                   COALESCE(AVG(duration_ms), 0) AS avg_dur,
                   COALESCE(AVG(total_cost_usd), 0) AS avg_cost
            FROM project_memory
            WHERE created_at > NOW() - INTERVAL '7 days'
            """
        )
        dist = await conn.fetch(
            """
            SELECT verdict, COUNT(*) AS n FROM project_memory
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY verdict
            """
        )
    verdict_dist = {r["verdict"]: int(r["n"]) for r in dist}
    total = sum(verdict_dist.values()) or 1
    fails = verdict_dist.get("HARD_FAIL", 0) + verdict_dist.get("SOFT_FAIL", 0)
    return {
        "projects_last_7d": int(row["n"] or 0),
        "avg_duration_ms": int(row["avg_dur"] or 0),
        "rework_rate": fails / total,
        "avg_cost_usd": float(row["avg_cost"] or 0),
        "verdict_distribution": verdict_dist,
    }


async def _load_previous(pool: asyncpg.Pool) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT avg_duration_ms, rework_rate, avg_cost_usd
            FROM meta_metrics_snapshots ORDER BY captured_at DESC LIMIT 1
            """
        )
    if not row:
        return None
    return {
        "avg_duration_ms": int(row["avg_duration_ms"] or 0),
        "rework_rate": float(row["rework_rate"] or 0),
        "avg_cost_usd": float(row["avg_cost_usd"] or 0),
    }


def _detect_degradation(
    current: dict[str, Any], previous: dict[str, Any] | None,
) -> list[str]:
    if not previous:
        return []
    degraded: list[str] = []
    for metric, ratio in DEGRADATION_THRESHOLDS.items():
        prev = float(previous.get(metric) or 0)
        curr = float(current.get(metric) or 0)
        if prev <= 0:
            continue
        if curr / prev >= ratio:
            degraded.append(
                f"{metric}: {prev:.4g} -> {curr:.4g} (x{curr/prev:.2f})"
            )
    return degraded


async def capture_and_analyze(pool: asyncpg.Pool) -> MetaSnapshot:
    current = await _load_current(pool)
    previous = await _load_previous(pool)
    degraded = _detect_degradation(current, previous)
    snap = MetaSnapshot(
        projects_last_7d=current["projects_last_7d"],
        avg_duration_ms=current["avg_duration_ms"],
        rework_rate=current["rework_rate"],
        avg_cost_usd=current["avg_cost_usd"],
        verdict_distribution=current["verdict_distribution"],
        degraded_metrics=degraded,
    )
    await _persist(pool, snap)
    if degraded:
        try:
            await self_improver.run_cycle(pool)
        except Exception as exc:
            logger.warning("self_improver trigger failed: %s", exc)
        await audit_events.emit(
            pool, action="meta_degradation_detected", actor="meta_optimizer",
            payload={"degraded": degraded},
        )
    logger.info("meta snapshot captured, degraded=%d", len(degraded))
    return snap


async def _persist(pool: asyncpg.Pool, snap: MetaSnapshot) -> None:
    import json
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO meta_metrics_snapshots
              (projects_last_7d, avg_duration_ms, rework_rate, avg_cost_usd,
               verdict_distribution, degraded_metrics)
            VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb)
            """,
            snap.projects_last_7d, snap.avg_duration_ms,
            snap.rework_rate, snap.avg_cost_usd,
            json.dumps(snap.verdict_distribution),
            json.dumps(snap.degraded_metrics),
        )


async def latest(pool: asyncpg.Pool) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM meta_metrics_snapshots "
            "ORDER BY captured_at DESC LIMIT 1"
        )
    if not row:
        return None
    d = dict(row)
    d.pop("id", None)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d
