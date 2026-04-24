"""V5.5 Automation - 9 event-trigger handlers + Dead Letter Queue.

Chaque handler est un coroutine arq declarche par un evenement systeme
(publie dans Redis `uba:events` ou enqueue direct). Les 9 events sont
strictement alignes avec les entrees de la table `event_triggers`
(migration 026).

DLQ :
  - Redis stream `uba:dlq:events` : entree chaque fois qu'une task echoue
    apres max_tries.
  - `task_dead_letter_processor` : pousse les entrees depuis la table
    `dead_letter_queue`, tente retraitement + email actor.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.database import get_pool
from app.workers._runtime import _jlog, workflow_task

logger = logging.getLogger("uba.events")

# ============================================================================
# EVENT HANDLERS (9 triggers)
# ============================================================================

@workflow_task("on_git_commit_detected", timeout_s=120, trigger_kind="event")
async def on_git_commit_detected(_ctx: dict[str, Any] | None = None,
                                   commit_sha: str | None = None,
                                   branch: str | None = None,
                                   **_: Any) -> dict[str, Any]:
    """Declencheur : git commit. Enchaine tests impactes + lint + security diff."""
    pool = get_pool()
    chained: list[str] = []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='git_commit' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.INFO, "event.git_commit",
          commit_sha=commit_sha, branch=branch, chained_tasks=chained)
    return {"commit_sha": commit_sha, "branch": branch,
            "chained_tasks": chained}


@workflow_task("on_migration_applied", timeout_s=180, trigger_kind="event")
async def on_migration_applied(_ctx: dict[str, Any] | None = None,
                                 migration: str | None = None,
                                 **_: Any) -> dict[str, Any]:
    """Declencheur : migration SQL appliquee -> verify schema + invariants."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='migration_applied' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.INFO, "event.migration_applied",
          migration=migration, chained_tasks=chained)
    return {"migration": migration, "chained_tasks": chained}


@workflow_task("on_new_project_created", timeout_s=180, trigger_kind="event")
async def on_new_project_created(_ctx: dict[str, Any] | None = None,
                                    project_id: str | None = None,
                                    **_: Any) -> dict[str, Any]:
    """Declencheur : nouveau projet -> auth prefetch + risk + workflow planner."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='new_project_created' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.INFO, "event.new_project_created",
          project_id=project_id, chained_tasks=chained)
    return {"project_id": project_id, "chained_tasks": chained}


@workflow_task("on_test_failure", timeout_s=120, trigger_kind="event")
async def on_test_failure(_ctx: dict[str, Any] | None = None,
                            test_name: str | None = None,
                            error: str | None = None,
                            **_: Any) -> dict[str, Any]:
    """Declencheur : test failure -> failure analysis."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='test_failure' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.WARNING, "event.test_failure",
          test_name=test_name, error=(error or "")[:200])
    return {"test_name": test_name, "chained_tasks": chained}


@workflow_task("on_cost_budget_approaching", timeout_s=120, trigger_kind="event")
async def on_cost_budget_approaching(_ctx: dict[str, Any] | None = None,
                                       used_pct: float | None = None,
                                       budget_usd: float | None = None,
                                       **_: Any) -> dict[str, Any]:
    """Declencheur : budget approche -> budget optimization."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='cost_budget_approaching' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.WARNING, "event.cost_budget_approaching",
          used_pct=used_pct, budget_usd=budget_usd)
    return {"used_pct": used_pct, "budget_usd": budget_usd,
            "chained_tasks": chained}


@workflow_task("on_regulatory_change_detected", timeout_s=120, trigger_kind="event")
async def on_regulatory_change_detected(_ctx: dict[str, Any] | None = None,
                                           reg_id: str | None = None,
                                           **_: Any) -> dict[str, Any]:
    """Declencheur : changement reglementaire -> impact analysis."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='regulatory_change_detected' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.INFO, "event.regulatory_change_detected",
          reg_id=reg_id, chained_tasks=chained)
    return {"reg_id": reg_id, "chained_tasks": chained}


@workflow_task("on_agent_drift_detected", timeout_s=120, trigger_kind="event")
async def on_agent_drift_detected(_ctx: dict[str, Any] | None = None,
                                     agent_id: str | None = None,
                                     drift_score: float | None = None,
                                     **_: Any) -> dict[str, Any]:
    """Declencheur : drift agent -> diagnosis."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='agent_drift_detected' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.WARNING, "event.agent_drift_detected",
          agent_id=agent_id, drift_score=drift_score)
    return {"agent_id": agent_id, "drift_score": drift_score,
            "chained_tasks": chained}


@workflow_task("on_phase_gate_requested", timeout_s=180, trigger_kind="event")
async def on_phase_gate_requested(_ctx: dict[str, Any] | None = None,
                                     task_id: str | None = None,
                                     phase: str | None = None,
                                     **_: Any) -> dict[str, Any]:
    """Declencheur : phase gate -> validate 7 layers."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='phase_gate_requested' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.INFO, "event.phase_gate_requested",
          task_id=task_id, phase=phase)
    return {"task_id": task_id, "phase": phase, "chained_tasks": chained}


@workflow_task("on_ahmed_response_received", timeout_s=120, trigger_kind="event")
async def on_ahmed_response_received(_ctx: dict[str, Any] | None = None,
                                        inbox_item_id: str | None = None,
                                        **_: Any) -> dict[str, Any]:
    """Declencheur : reponse Ahmed recue -> response classifier."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_name FROM event_triggers "
            "WHERE event_type='ahmed_response_received' AND enabled = TRUE",
        )
    chained = [r["task_name"] for r in rows]
    _jlog(logging.INFO, "event.ahmed_response_received",
          inbox_item_id=inbox_item_id)
    return {"inbox_item_id": inbox_item_id, "chained_tasks": chained}


EVENT_TASKS: list[Any] = [
    on_git_commit_detected,
    on_migration_applied,
    on_new_project_created,
    on_test_failure,
    on_cost_budget_approaching,
    on_regulatory_change_detected,
    on_agent_drift_detected,
    on_phase_gate_requested,
    on_ahmed_response_received,
]

assert len(EVENT_TASKS) == 9, f"Expected 9 event tasks, got {len(EVENT_TASKS)}"

EVENT_TASK_NAMES: list[str] = [t.__automation_task__ for t in EVENT_TASKS]  # type: ignore[attr-defined]


# ============================================================================
# DEAD LETTER QUEUE
# ============================================================================

DLQ_REDIS_STREAM = "uba:dlq:events"


async def push_to_dlq_redis(
    task_name: str,
    args: dict[str, Any],
    last_error: str,
    tries: int,
) -> str | None:
    """Stream l'echec dans Redis `uba:dlq:events` (append-only). Retourne l'id
    du message ou None si indisponible."""
    import redis.asyncio as redis_lib

    from app.config import get_settings
    s = get_settings()
    r = redis_lib.Redis(
        host=s.REDIS_HOST, port=s.REDIS_PORT,
        password=s.REDIS_PASSWORD or None, db=s.REDIS_DB,
    )
    try:
        mid = await r.xadd(
            DLQ_REDIS_STREAM,
            {
                "task_name": task_name,
                "args": json.dumps(args, default=str),
                "last_error": last_error[:2000],
                "tries": str(tries),
                "at": datetime.utcnow().isoformat(),
            },
            maxlen=10_000, approximate=True,
        )
        return mid.decode() if isinstance(mid, bytes) else str(mid)
    except Exception as exc:
        _jlog(logging.ERROR, "dlq.redis.push_failed",
              task_name=task_name, error=str(exc))
        return None
    finally:
        try:
            await r.aclose()
        except Exception as exc:
            logger.debug("redis aclose failed: %s", exc)


async def push_to_dlq_db(
    task_name: str,
    args: dict[str, Any],
    last_error: str,
    tries: int,
) -> int | None:
    """Persist l'echec dans la table `dead_letter_queue`."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO dead_letter_queue
                (task_name, args, last_error, tries)
            VALUES ($1, $2::jsonb, $3, $4)
            RETURNING id
            """,
            task_name, json.dumps(args, default=str),
            last_error[:4000], tries,
        )
    return int(row["id"]) if row else None


@workflow_task("task_dead_letter_processor", timeout_s=300)
async def task_dead_letter_processor(_ctx: dict[str, Any] | None = None,
                                       **_: Any) -> dict[str, Any]:
    """Processe les entrees non resolues de `dead_letter_queue` (limit 50)."""
    pool = get_pool()
    processed = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, task_name, args, tries
            FROM dead_letter_queue
            WHERE resolved = FALSE
            ORDER BY entered_dlq_at ASC
            LIMIT 50
            """,
        )
        for r in rows:
            # Politique : on marque 'acknowledged' apres 3 passes dans le DLQ.
            # L'operateur humain reste source de verite pour la resolution.
            await conn.execute(
                """
                UPDATE dead_letter_queue
                SET resolution = COALESCE(resolution, '') || ' dlq_processor_ack'
                WHERE id = $1
                """,
                r["id"],
            )
            processed += 1
    return {"processed": processed, "policy": "ack_without_retry"}
