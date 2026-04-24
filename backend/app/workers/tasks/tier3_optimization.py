"""Tier 3 - Optimization (nocturne).

Tasks :
  - task_nightly_optimizer
  - task_meta_optimizer
  - task_innovation_scout
  - task_autonomy_chaos
  - task_drift_detection
  - task_failure_archetype_mining
  - task_rework_convergence_audit
"""
from __future__ import annotations

from typing import Any

from app.database import get_pool

from ._base import workflow_task


@workflow_task("task_nightly_optimizer", timeout_s=300)
async def task_nightly_optimizer(_ctx: dict[str, Any] | None = None,
                                  **_: Any) -> dict[str, Any]:
    """Retune thresholds global via auto_tuner."""
    from app.orchestration.auto_tuner import retune_global
    pool = get_pool()
    try:
        t = await retune_global(pool)
        return {"retuned": True,
                "thresholds": t.to_dict() if hasattr(t, "to_dict") else str(t)}
    except Exception as exc:
        return {"retuned": False, "error": str(exc)}


@workflow_task("task_meta_optimizer", timeout_s=180)
async def task_meta_optimizer(_ctx: dict[str, Any] | None = None,
                               **_: Any) -> dict[str, Any]:
    """Capture meta-metriques : runs 24h par status."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT status, COUNT(*) AS n
            FROM workflow_executions
            WHERE started_at > NOW() - INTERVAL '24 hours'
            GROUP BY status
            """,
        )
    by_status = {r["status"]: int(r["n"]) for r in rows}
    total = sum(by_status.values())
    succ = by_status.get("succeeded", 0)
    return {
        "total_runs_24h": total,
        "by_status": by_status,
        "success_rate": (succ / total) if total else 1.0,
    }


@workflow_task("task_innovation_scout", timeout_s=240)
async def task_innovation_scout(_ctx: dict[str, Any] | None = None,
                                 **_: Any) -> dict[str, Any]:
    """Delegue au module innovation_scout si dispo."""
    try:
        from app.orchestration import innovation_scout
        pool = get_pool()
        if hasattr(innovation_scout, "run_cycle"):
            out = await innovation_scout.run_cycle(pool)
            return {"ran": True, "summary": out}
    except Exception as exc:
        return {"ran": False, "error": str(exc)}
    return {"ran": False, "reason": "no run_cycle()"}


@workflow_task("task_autonomy_chaos", timeout_s=300)
async def task_autonomy_chaos(_ctx: dict[str, Any] | None = None,
                               **_: Any) -> dict[str, Any]:
    """Echantillon de scenarios chaos (dry_run)."""
    try:
        from app.autonomy import autonomy_chaos_engine
        pool = get_pool()
        if hasattr(autonomy_chaos_engine, "run_all"):
            res = await autonomy_chaos_engine.run_all(pool, dry_run=True)
            return {"ran": True, "summary": str(res)[:500]}
    except Exception as exc:
        return {"ran": False, "error": str(exc)}
    return {"ran": False, "reason": "chaos engine absent"}


@workflow_task("task_drift_detection", timeout_s=120)
async def task_drift_detection(_ctx: dict[str, Any] | None = None,
                                **_: Any) -> dict[str, Any]:
    """Drift naif : moyenne scores 7j vs 1j."""
    pool = get_pool()
    async with pool.acquire() as conn:
        hist = await conn.fetchval(
            """
            SELECT AVG(validation_score) FROM tasks
            WHERE completed_at > NOW() - INTERVAL '7 days'
              AND validation_score IS NOT NULL
            """,
        )
        recent = await conn.fetchval(
            """
            SELECT AVG(validation_score) FROM tasks
            WHERE completed_at > NOW() - INTERVAL '1 day'
              AND validation_score IS NOT NULL
            """,
        )
    h = float(hist) if hist is not None else None
    r = float(recent) if recent is not None else None
    drift = (r - h) if (h is not None and r is not None) else None
    return {"avg_7d": h, "avg_1d": r, "drift": drift,
            "alert": bool(drift is not None and drift < -0.1)}


@workflow_task("task_failure_archetype_mining", timeout_s=180)
async def task_failure_archetype_mining(_ctx: dict[str, Any] | None = None,
                                         **_: Any) -> dict[str, Any]:
    """Clustering erreurs recentes par message."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT error, COUNT(*) AS n
            FROM workflow_executions
            WHERE status IN ('failed','timeout')
              AND started_at > NOW() - INTERVAL '7 days'
              AND error IS NOT NULL
            GROUP BY error
            ORDER BY n DESC
            LIMIT 10
            """,
        )
    archetypes = [{"error": r["error"][:200], "count": int(r["n"])} for r in rows]
    return {"archetypes": archetypes, "archetype_count": len(archetypes)}


@workflow_task("task_rework_convergence_audit", timeout_s=180)
async def task_rework_convergence_audit(_ctx: dict[str, Any] | None = None,
                                         **_: Any) -> dict[str, Any]:
    """Ratio retries/total sur 24h."""
    pool = get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM workflow_executions "
            "WHERE started_at > NOW() - INTERVAL '24 hours'",
        )
        retries = await conn.fetchval(
            "SELECT COUNT(*) FROM workflow_executions "
            "WHERE tries > 1 AND started_at > NOW() - INTERVAL '24 hours'",
        )
    total_i = int(total or 0)
    retries_i = int(retries or 0)
    return {
        "total_24h": total_i,
        "retries_24h": retries_i,
        "rework_ratio": (retries_i / total_i) if total_i else 0.0,
    }


ALL_TASKS = [
    task_nightly_optimizer,
    task_meta_optimizer,
    task_innovation_scout,
    task_autonomy_chaos,
    task_drift_detection,
    task_failure_archetype_mining,
    task_rework_convergence_audit,
]
