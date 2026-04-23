"""Marketplace des agents V4 - benchmark continu + statut dynamique.

Lit `agent_benchmarks` et calcule un statut par agent :
- `new`        : < 3 executions
- `healthy`    : success_rate >= 0.90 ET avg_score >= 0.75
- `at_risk`    : 0.70 <= success_rate < 0.90 OU 0.50 <= avg_score < 0.75
- `deprecated` : success_rate < 0.70 OU avg_score < 0.50 (desactive du DAG)

Le statut est persiste dans `agent_marketplace`. `is_enabled(agent_id)` est
utilise par l'orchestrateur pour court-circuiter les agents deprecated.
"""
from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

HEALTHY_MIN_RATE = 0.90
HEALTHY_MIN_SCORE = 0.75
AT_RISK_MIN_RATE = 0.70
AT_RISK_MIN_SCORE = 0.50
NEW_MAX_EXEC = 2


def classify(executions: int, success_rate: float, avg_score: float) -> str:
    """Determine new / healthy / at_risk / deprecated selon les metriques."""
    if executions <= NEW_MAX_EXEC:
        return "new"
    if success_rate < AT_RISK_MIN_RATE or avg_score < AT_RISK_MIN_SCORE:
        return "deprecated"
    if success_rate < HEALTHY_MIN_RATE or avg_score < HEALTHY_MIN_SCORE:
        return "at_risk"
    return "healthy"


async def refresh_marketplace(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Recalcule tous les statuts depuis agent_benchmarks et persiste."""
    async with pool.acquire() as conn:
        bench = await conn.fetch("""
            SELECT agent_id, agent_name, executions, successes, failures, avg_score
            FROM agent_benchmarks
            ORDER BY executions DESC
        """)
    snapshot: list[dict[str, Any]] = []
    async with pool.acquire() as conn, conn.transaction():
        for rank, r in enumerate(bench, start=1):
            execs = int(r["executions"])
            succ = int(r["successes"])
            rate = succ / execs if execs else 0.0
            score = float(r["avg_score"])
            status = classify(execs, rate, score)
            enabled = status != "deprecated"
            reason = _reason(status, execs, rate, score)
            await conn.execute("""
                    INSERT INTO agent_marketplace
                      (agent_id, agent_name, enabled, status, rank, reason)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (agent_id) DO UPDATE SET
                      agent_name = EXCLUDED.agent_name,
                      enabled = EXCLUDED.enabled,
                      status = EXCLUDED.status,
                      rank = EXCLUDED.rank,
                      reason = EXCLUDED.reason,
                      last_change = NOW()
                """, r["agent_id"], r["agent_name"], enabled, status, rank, reason)
            snapshot.append({
                "agent_id": r["agent_id"],
                "agent_name": r["agent_name"],
                "executions": execs, "success_rate": round(rate, 4),
                "avg_score": round(score, 4),
                "status": status, "enabled": enabled,
                "rank": rank, "reason": reason,
            })
    logger.info("marketplace refreshed: %d agents", len(snapshot))
    return snapshot


def _reason(status: str, execs: int, rate: float, score: float) -> str:
    if status == "new":
        return f"Periode de rodage ({execs} execution(s))"
    if status == "deprecated":
        return f"succes={rate:.0%} score={score:.2f} < seuils critiques"
    if status == "at_risk":
        return f"succes={rate:.0%} score={score:.2f} sous seuils healthy"
    return f"succes={rate:.0%} score={score:.2f} : performant"


async def is_enabled(pool: asyncpg.Pool, agent_id: str) -> bool:
    """Indique si un agent est actif dans le marketplace (sinon court-circuit)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT enabled FROM agent_marketplace WHERE agent_id=$1", agent_id,
        )
    return True if row is None else bool(row["enabled"])


async def snapshot(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Cliche des agents avec rang, statut, success_rate et duree moyenne."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT m.agent_id, m.agent_name, m.enabled, m.status, m.rank, m.reason,
                   m.last_change, b.executions, b.successes, b.failures,
                   b.avg_score, b.total_duration_ms
            FROM agent_marketplace m
            LEFT JOIN agent_benchmarks b USING (agent_id)
            ORDER BY m.rank NULLS LAST, m.agent_id
        """)
    out: list[dict[str, Any]] = []
    for r in rows:
        execs = int(r["executions"] or 0)
        out.append({
            "agent_id": r["agent_id"],
            "agent_name": r["agent_name"],
            "enabled": bool(r["enabled"]),
            "status": r["status"],
            "rank": r["rank"],
            "reason": r["reason"],
            "executions": execs,
            "success_rate": round(int(r["successes"] or 0) / execs, 4) if execs else 0.0,
            "avg_score": float(r["avg_score"] or 0),
            "avg_duration_ms": round(int(r["total_duration_ms"] or 0) / execs, 1) if execs else 0.0,
            "last_change": r["last_change"].isoformat(),
        })
    return out
