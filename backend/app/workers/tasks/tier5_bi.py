"""Tier 5 - Business Intelligence reports (matin)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database import get_pool

from ._base import workflow_task


@workflow_task("task_cost_report_generation", timeout_s=120)
async def task_cost_report_generation(_ctx: dict[str, Any] | None = None,
                                       **_: Any) -> dict[str, Any]:
    """Agrege le cout journalier via cost_ledger si dispo."""
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='cost_ledger')",
        )
        if not exists:
            return {"ran": False, "reason": "cost_ledger absent"}
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(cost_usd), 0) AS total, COUNT(*) AS n
            FROM cost_ledger
            WHERE created_at > NOW() - INTERVAL '1 day'
            """,
        )
    return {"total_cost_usd_24h": float(row["total"]),
            "entries": int(row["n"])}


@workflow_task("task_agent_performance_report", timeout_s=120)
async def task_agent_performance_report(_ctx: dict[str, Any] | None = None,
                                         **_: Any) -> dict[str, Any]:
    """Par-agent : success_rate 7 jours."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent_id,
                   SUM((status='success')::int) AS ok,
                   COUNT(*) AS total,
                   AVG(duration_ms)::int AS avg_ms
            FROM agent_executions
            WHERE started_at > NOW() - INTERVAL '7 days'
            GROUP BY agent_id
            ORDER BY total DESC
            LIMIT 30
            """,
        )
    report = [
        {
            "agent_id": r["agent_id"],
            "success_rate": (int(r["ok"]) / int(r["total"])) if r["total"] else 0.0,
            "avg_ms": int(r["avg_ms"] or 0),
            "total": int(r["total"]),
        }
        for r in rows
    ]
    return {"agents": report, "agent_count": len(report)}


@workflow_task("task_coverage_report", timeout_s=600)
async def task_coverage_report(_ctx: dict[str, Any] | None = None,
                                **_: Any) -> dict[str, Any]:
    """Recherche coverage.xml / .coverage sur disque."""
    candidates = [
        Path("/app/coverage.xml"), Path("/app/.coverage"),
        Path("backend/coverage.xml"), Path("backend/.coverage"),
    ]
    for p in candidates:
        if p.exists():
            return {"found": True, "path": str(p),
                    "size_bytes": p.stat().st_size}
    return {"found": False, "paths_checked": [str(p) for p in candidates]}


ALL_TASKS = [
    task_cost_report_generation,
    task_agent_performance_report,
    task_coverage_report,
]
