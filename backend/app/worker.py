"""Worker Arq - traitement async des taches de generation."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings

from app.agents.registry import AgentRegistry
from app.config import get_settings
from app.database import init_pool, close_pool, get_pool

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_task(ctx: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Pipeline minimal V0: passe la tache en 'executing' puis 'completed'.

    L'orchestrateur reel sera implemente dans les iterations suivantes
    (Ch.4.3 orchestrator.py). Ce stub garantit que le worker tourne.
    """
    logger.info("run_task %s", task_id)
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tasks SET status = 'executing', started_at = NOW() WHERE id = $1",
            UUID(task_id),
        )
        registry = AgentRegistry.get_instance()
        agents_info = registry.list_all()
        await conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = NOW(), validation_score = 0 WHERE id = $1",
            UUID(task_id),
        )
    return {"task_id": task_id, "agents_registered": len(agents_info)}


async def startup(ctx: dict[str, Any]) -> None:
    await init_pool()
    registry = AgentRegistry.get_instance()
    await registry.initialize_all()
    logger.info("Worker started, %d agents ready", len(registry.list_all()))


async def shutdown(ctx: dict[str, Any]) -> None:
    await close_pool()


class WorkerSettings:
    functions = [run_task]
    cron_jobs = [
        cron(lambda ctx: None, minute=0, hour=3, run_at_startup=False),  # placeholder nightly
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        database=settings.REDIS_DB,
    )
    max_jobs = 10
    job_timeout = 900
