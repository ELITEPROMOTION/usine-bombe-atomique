"""V5.5 Automation - 9 endpoints workflow dashboard.

Routes :
  GET  /workflows/active            : runs en cours
  GET  /workflows/scheduled         : 26 cron schedules
  GET  /workflows/history           : 100 dernieres executions
  GET  /workflows/metrics           : agregation 7 jours
  GET  /workflows/failures          : derniers echecs + DLQ
  GET  /workflows/dependencies      : dependances event -> task
  POST /workflows/trigger/{task}    : enqueue manuel
  POST /workflows/pause/{task}      : desactive un schedule
  POST /workflows/resume/{task}     : reactive un schedule
"""
from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.database import get_pool

router = APIRouter(prefix="/workflows", tags=["automation_v5_5"])


def _redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings(
        host=s.REDIS_HOST, port=s.REDIS_PORT,
        password=s.REDIS_PASSWORD or None, database=s.REDIS_DB,
    )


# =============================================================================
# GET endpoints
# =============================================================================

@router.get("/active")
async def workflows_active() -> dict[str, Any]:
    """Runs arq en cours (status='running')."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT run_id, task_name, worker_name, started_at,
                   tries, trigger_kind
            FROM workflow_executions
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 100
            """,
        )
    return {
        "count": len(rows),
        "runs": [
            {
                "run_id": str(r["run_id"]),
                "task_name": r["task_name"],
                "worker_name": r["worker_name"],
                "started_at": r["started_at"].isoformat(),
                "tries": int(r["tries"]),
                "trigger_kind": r["trigger_kind"],
            } for r in rows
        ],
    }


@router.get("/scheduled")
async def workflows_scheduled() -> dict[str, Any]:
    """26 schedules (workflow_schedules)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT task_name, cron_expression, tier, enabled,
                   paused_at, last_run, next_run, description
            FROM workflow_schedules
            ORDER BY tier ASC, task_name ASC
            """,
        )
    return {
        "count": len(rows),
        "schedules": [
            {
                "task_name": r["task_name"],
                "cron_expression": r["cron_expression"],
                "tier": int(r["tier"]),
                "enabled": bool(r["enabled"]),
                "paused_at": r["paused_at"].isoformat() if r["paused_at"] else None,
                "last_run": r["last_run"].isoformat() if r["last_run"] else None,
                "next_run": r["next_run"].isoformat() if r["next_run"] else None,
                "description": r["description"],
            } for r in rows
        ],
    }


@router.get("/history")
async def workflows_history(limit: int = 100,
                             task_name: str | None = None) -> dict[str, Any]:
    """Historique executions (limit 500)."""
    limit = max(1, min(500, limit))
    pool = get_pool()
    async with pool.acquire() as conn:
        if task_name:
            rows = await conn.fetch(
                """
                SELECT run_id, task_name, status, started_at, finished_at,
                       duration_ms, tries, trigger_kind, error
                FROM workflow_executions
                WHERE task_name = $1
                ORDER BY started_at DESC
                LIMIT $2
                """, task_name, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT run_id, task_name, status, started_at, finished_at,
                       duration_ms, tries, trigger_kind, error
                FROM workflow_executions
                ORDER BY started_at DESC
                LIMIT $1
                """, limit,
            )
    return {
        "count": len(rows),
        "runs": [
            {
                "run_id": str(r["run_id"]),
                "task_name": r["task_name"],
                "status": r["status"],
                "started_at": r["started_at"].isoformat(),
                "finished_at": (r["finished_at"].isoformat()
                                if r["finished_at"] else None),
                "duration_ms": int(r["duration_ms"]) if r["duration_ms"] else None,
                "tries": int(r["tries"]),
                "trigger_kind": r["trigger_kind"],
                "error": r["error"],
            } for r in rows
        ],
    }


@router.get("/metrics")
async def workflows_metrics(days: int = 7) -> dict[str, Any]:
    """Agregation par task sur N jours."""
    days = max(1, min(90, days))
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT task_name,
                   SUM(success_count) AS succ,
                   SUM(failure_count) AS fail,
                   AVG(avg_duration_ms)::int AS avg_ms,
                   MAX(p99_duration_ms) AS p99_ms,
                   MAX(last_run) AS last_run
            FROM workflow_metrics
            WHERE day > CURRENT_DATE - $1::int
            GROUP BY task_name
            ORDER BY task_name ASC
            """, days,
        )
    payload = []
    total_succ = 0
    total_fail = 0
    for r in rows:
        s = int(r["succ"] or 0)
        f = int(r["fail"] or 0)
        total_succ += s
        total_fail += f
        payload.append({
            "task_name": r["task_name"],
            "success_count": s,
            "failure_count": f,
            "avg_duration_ms": int(r["avg_ms"] or 0),
            "p99_duration_ms": int(r["p99_ms"] or 0),
            "last_run": r["last_run"].isoformat() if r["last_run"] else None,
            "success_rate": (s / (s + f)) if (s + f) else 1.0,
        })
    total = total_succ + total_fail
    return {
        "days": days,
        "total_runs": total,
        "total_success": total_succ,
        "total_failure": total_fail,
        "global_success_rate": (total_succ / total) if total else 1.0,
        "per_task": payload,
    }


@router.get("/failures")
async def workflows_failures(limit: int = 50) -> dict[str, Any]:
    """Echecs recents + Dead Letter Queue non resolue."""
    limit = max(1, min(200, limit))
    pool = get_pool()
    async with pool.acquire() as conn:
        recent = await conn.fetch(
            """
            SELECT run_id, task_name, started_at, tries, error
            FROM workflow_executions
            WHERE status IN ('failed','timeout','dead_letter')
            ORDER BY started_at DESC
            LIMIT $1
            """, limit,
        )
        dlq = await conn.fetch(
            """
            SELECT id, task_name, tries, last_error, entered_dlq_at, resolved
            FROM dead_letter_queue
            WHERE resolved = FALSE
            ORDER BY entered_dlq_at DESC
            LIMIT $1
            """, limit,
        )
    return {
        "failures": [
            {
                "run_id": str(r["run_id"]),
                "task_name": r["task_name"],
                "started_at": r["started_at"].isoformat(),
                "tries": int(r["tries"]),
                "error": r["error"],
            } for r in recent
        ],
        "dlq": [
            {
                "id": int(r["id"]),
                "task_name": r["task_name"],
                "tries": int(r["tries"]),
                "last_error": r["last_error"],
                "entered_dlq_at": r["entered_dlq_at"].isoformat(),
                "resolved": bool(r["resolved"]),
            } for r in dlq
        ],
    }


@router.get("/dependencies")
async def workflows_dependencies() -> dict[str, Any]:
    """Mapping event_type -> list[task_name]."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_type, task_name, enabled, condition_json
            FROM event_triggers
            ORDER BY event_type ASC, task_name ASC
            """,
        )
    mapping: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        mapping.setdefault(r["event_type"], []).append({
            "task_name": r["task_name"],
            "enabled": bool(r["enabled"]),
            "condition": r["condition_json"],
        })
    return {"event_count": len(mapping), "triggers": mapping}


# =============================================================================
# POST endpoints
# =============================================================================

@router.post("/trigger/{task_name}")
async def workflows_trigger(task_name: str,
                              payload: dict[str, Any] | None = None
                              ) -> dict[str, Any]:
    """Enqueue manuel d'une task dans arq."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT task_name FROM workflow_schedules WHERE task_name = $1",
            task_name,
        )
    if not row:
        raise HTTPException(404, detail=f"task not in schedules: {task_name}")

    arq_pool = await create_pool(_redis_settings())
    try:
        job = await arq_pool.enqueue_job(
            task_name, _trigger_kind="manual", **(payload or {}),
        )
    finally:
        await arq_pool.close()
    return {
        "task_name": task_name,
        "enqueued": job is not None,
        "job_id": getattr(job, "job_id", None),
    }


@router.post("/pause/{task_name}")
async def workflows_pause(task_name: str) -> dict[str, Any]:
    """Desactive un schedule (enabled = FALSE, paused_at = NOW)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workflow_schedules
            SET enabled = FALSE, paused_at = NOW()
            WHERE task_name = $1
            RETURNING task_name, enabled, paused_at
            """, task_name,
        )
    if not row:
        raise HTTPException(404, detail=f"task not found: {task_name}")
    return {
        "task_name": row["task_name"],
        "enabled": bool(row["enabled"]),
        "paused_at": row["paused_at"].isoformat() if row["paused_at"] else None,
    }


@router.post("/resume/{task_name}")
async def workflows_resume(task_name: str) -> dict[str, Any]:
    """Reactive un schedule (enabled = TRUE, paused_at = NULL)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workflow_schedules
            SET enabled = TRUE, paused_at = NULL
            WHERE task_name = $1
            RETURNING task_name, enabled, paused_at
            """, task_name,
        )
    if not row:
        raise HTTPException(404, detail=f"task not found: {task_name}")
    return {
        "task_name": row["task_name"],
        "enabled": bool(row["enabled"]),
        "paused_at": None,
    }
