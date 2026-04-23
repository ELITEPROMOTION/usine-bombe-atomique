"""V5.5 Automation - runtime partage des tasks arq.

Fournit :
  - `workflow_task` : decorateur qui ouvre une run dans `workflow_executions`,
    logue JSON structure, capture erreurs dans `audit_events`, met a jour les
    metriques quotidiennes (`workflow_metrics`), respecte un timeout.
  - Initialisation/fermeture du pool BDD pour l'entry-point arq.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import traceback
from functools import wraps
from typing import Any, Awaitable, Callable
from uuid import UUID

import asyncpg

from app.database import close_pool, get_pool, init_pool
from app.orchestration import audit_events

logger = logging.getLogger("uba.automation")

TaskFunc = Callable[..., Awaitable[dict[str, Any]]]

WORKER_NAME = os.environ.get("WORKER_NAME") or f"worker-{socket.gethostname()}"


def _jlog(level: int, event: str, **fields: Any) -> None:
    """Log JSON structure sur stdout (clef: 'automation.event')."""
    payload = {"event": event, "worker": WORKER_NAME, **fields}
    try:
        msg = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        msg = str(payload)
    logger.log(level, msg)


async def _open_run(
    pool: asyncpg.Pool,
    task_name: str,
    trigger_kind: str,
) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO workflow_executions
                (task_name, worker_name, status, tries, trigger_kind)
            VALUES ($1, $2, 'running', 1, $3)
            RETURNING run_id
            """,
            task_name, WORKER_NAME, trigger_kind,
        )
    return row["run_id"]


async def _close_run(
    pool: asyncpg.Pool,
    run_id: UUID,
    status: str,
    duration_ms: int,
    result: dict[str, Any] | None,
    error: str | None,
    tries: int,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE workflow_executions
            SET finished_at = NOW(),
                duration_ms = $2,
                status      = $3,
                tries       = $4,
                error       = $5,
                result      = $6::jsonb
            WHERE run_id = $1
            """,
            run_id, duration_ms, status, tries, error,
            json.dumps(result or {}, default=str),
        )


async def _bump_metrics(
    pool: asyncpg.Pool,
    task_name: str,
    duration_ms: int,
    success: bool,
) -> None:
    """UPSERT workflow_metrics du jour (avg + max proxy p99)."""
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT success_count, failure_count, avg_duration_ms, p99_duration_ms
            FROM workflow_metrics
            WHERE task_name = $1 AND day = CURRENT_DATE
            FOR UPDATE
            """,
            task_name,
        )
        if row is None:
            sc = 1 if success else 0
            fc = 0 if success else 1
            await conn.execute(
                """
                INSERT INTO workflow_metrics
                    (task_name, day, success_count, failure_count,
                     avg_duration_ms, p99_duration_ms, last_run)
                VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, NOW())
                """,
                task_name, sc, fc, float(duration_ms), int(duration_ms),
            )
        else:
            old_total = int(row["success_count"]) + int(row["failure_count"])
            new_total = old_total + 1
            new_avg = (
                float(row["avg_duration_ms"]) * old_total + duration_ms
            ) / max(new_total, 1)
            new_p99 = max(int(row["p99_duration_ms"]), int(duration_ms))
            sc = int(row["success_count"]) + (1 if success else 0)
            fc = int(row["failure_count"]) + (0 if success else 1)
            await conn.execute(
                """
                UPDATE workflow_metrics
                SET success_count = $2,
                    failure_count = $3,
                    avg_duration_ms = $4,
                    p99_duration_ms = $5,
                    last_run = NOW()
                WHERE task_name = $1 AND day = CURRENT_DATE
                """,
                task_name, sc, fc, new_avg, new_p99,
            )


def workflow_task(
    name: str,
    *,
    timeout_s: float = 300.0,
    trigger_kind: str = "cron",
) -> Callable[[TaskFunc], TaskFunc]:
    """Decore un coroutine de task pour wrapping execution + observation."""

    def decorator(func: TaskFunc) -> TaskFunc:

        @wraps(func)
        async def wrapper(ctx: dict[str, Any] | None = None,
                          *args: Any, **kwargs: Any) -> dict[str, Any]:
            pool = get_pool()
            start = time.perf_counter()
            tries = (ctx or {}).get("job_try", 1)
            trig = (ctx or {}).get("_trigger_kind", trigger_kind)
            run_id = await _open_run(pool, name, trig)
            _jlog(
                logging.INFO, "task.start",
                task_name=name, run_id=str(run_id),
                tries=tries, trigger_kind=trig,
            )
            status = "succeeded"
            error: str | None = None
            result: dict[str, Any] = {}
            try:
                result = await asyncio.wait_for(
                    func(ctx, *args, **kwargs), timeout=timeout_s,
                )
                if not isinstance(result, dict):
                    result = {"value": result}
            except asyncio.TimeoutError:
                status = "timeout"
                error = f"timeout after {timeout_s}s"
                _jlog(logging.ERROR, "task.timeout",
                      task_name=name, run_id=str(run_id), timeout_s=timeout_s)
            except Exception as exc:
                status = "failed"
                error = f"{type(exc).__name__}: {exc}"
                tb = traceback.format_exc(limit=5)
                _jlog(logging.ERROR, "task.error",
                      task_name=name, run_id=str(run_id),
                      error=error, traceback=tb)
                try:
                    await audit_events.emit(
                        pool, action="workflow_task_failed",
                        actor=f"automation/{name}",
                        payload={
                            "task_name": name, "run_id": str(run_id),
                            "error": error, "tries": tries,
                        },
                    )
                except Exception as audit_exc:
                    _jlog(logging.WARNING, "audit.emit_failed",
                          task_name=name, error=str(audit_exc))

            duration_ms = int((time.perf_counter() - start) * 1000)
            await _close_run(
                pool, run_id, status, duration_ms, result, error, tries,
            )
            try:
                await _bump_metrics(
                    pool, name, duration_ms, success=(status == "succeeded"),
                )
            except Exception as metric_exc:
                _jlog(logging.WARNING, "metrics.update_failed",
                      task_name=name, error=str(metric_exc))

            _jlog(
                logging.INFO if status == "succeeded" else logging.WARNING,
                "task.end",
                task_name=name, run_id=str(run_id),
                duration_ms=duration_ms, status=status, error=error,
            )
            out: dict[str, Any] = {
                "task_name": name,
                "run_id": str(run_id),
                "status": status,
                "duration_ms": duration_ms,
                "result": result,
            }
            if error:
                out["error"] = error
            return out

        wrapper.__automation_task__ = name  # type: ignore[attr-defined]
        wrapper.__automation_timeout__ = timeout_s  # type: ignore[attr-defined]
        return wrapper

    return decorator


async def automation_startup(_ctx: dict[str, Any]) -> None:
    await init_pool()
    _jlog(logging.INFO, "worker.startup", worker=WORKER_NAME)


async def automation_shutdown(_ctx: dict[str, Any]) -> None:
    _jlog(logging.INFO, "worker.shutdown", worker=WORKER_NAME)
    await close_pool()
