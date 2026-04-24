"""Tier 4 - Memoire + prompts + benchmarks (nocturne)."""
from __future__ import annotations

from typing import Any

from app.database import get_pool

from ._base import workflow_task


@workflow_task("task_memory_consolidation", timeout_s=240)
async def task_memory_consolidation(_ctx: dict[str, Any] | None = None,
                                     **_: Any) -> dict[str, Any]:
    """Stats project_memory (> 180 jours = candidat pruning)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='project_memory')",
        )
        if not exists:
            return {"pruned": 0, "reason": "project_memory table absent"}
        old = await conn.fetchval(
            "SELECT COUNT(*) FROM project_memory "
            "WHERE created_at < NOW() - INTERVAL '180 days'",
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM project_memory")
    return {"total": int(total or 0),
            "prunable_over_180d": int(old or 0),
            "pruned": 0}


@workflow_task("task_prompt_variants_rebalance", timeout_s=180)
async def task_prompt_variants_rebalance(_ctx: dict[str, Any] | None = None,
                                          **_: Any) -> dict[str, Any]:
    """Rebalance AB via prompt_ab si dispo."""
    pool = get_pool()
    try:
        from app.orchestration import prompt_ab
        if hasattr(prompt_ab, "rebalance"):
            out = await prompt_ab.rebalance(pool)
            return {"rebalanced": True, "summary": str(out)[:300]}
    except Exception as exc:
        return {"rebalanced": False, "error": str(exc)}
    return {"rebalanced": False, "reason": "prompt_ab.rebalance absent"}


@workflow_task("task_benchmarks_run", timeout_s=600)
async def task_benchmarks_run(_ctx: dict[str, Any] | None = None,
                               **_: Any) -> dict[str, Any]:
    """Run benchmarks cognition si dispo."""
    pool = get_pool()
    try:
        from app.cognition import benchmarks
        if hasattr(benchmarks, "run_all_families"):
            out = await benchmarks.run_all_families(pool)
            return {"ran": True, "summary": str(out)[:300]}
    except Exception as exc:
        return {"ran": False, "error": str(exc)}
    return {"ran": False, "reason": "benchmarks absent"}


ALL_TASKS = [
    task_memory_consolidation,
    task_prompt_variants_rebalance,
    task_benchmarks_run,
]
