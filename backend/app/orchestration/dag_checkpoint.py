"""Upgrade 28 - DAG Checkpointing dans Redis + mirror BDD.

A chaque fin de vague, on sauvegarde :
- completed_waves : index des vagues achevees
- agent_results   : resultat serialise (status + output) par agent_id

En cas de crash, le worker peut reprendre la derniere vague non terminee
au lieu de tout relancer.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    task_id: str
    last_wave_index: int
    completed_waves: list[int]
    agent_results: dict[str, dict[str, Any]]


async def save(
    pool: asyncpg.Pool, task_id: str, last_wave_index: int,
    completed_waves: list[int],
    agent_results: dict[str, dict[str, Any]],
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO dag_checkpoints
              (task_id, completed_waves, last_wave_index, agent_results, updated_at)
            VALUES ($1, $2::jsonb, $3, $4::jsonb, NOW())
            ON CONFLICT (task_id) DO UPDATE SET
              completed_waves = EXCLUDED.completed_waves,
              last_wave_index = EXCLUDED.last_wave_index,
              agent_results = EXCLUDED.agent_results,
              updated_at = NOW()
            """,
            UUID(task_id), json.dumps(completed_waves),
            last_wave_index, json.dumps(agent_results),
        )


async def load(pool: asyncpg.Pool, task_id: str) -> Checkpoint | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT completed_waves, last_wave_index, agent_results "
            "FROM dag_checkpoints WHERE task_id=$1", UUID(task_id),
        )
    if not row:
        return None
    waves = row["completed_waves"]
    if isinstance(waves, str):
        waves = json.loads(waves)
    agents = row["agent_results"]
    if isinstance(agents, str):
        agents = json.loads(agents)
    return Checkpoint(
        task_id=task_id,
        last_wave_index=int(row["last_wave_index"]),
        completed_waves=list(waves or []),
        agent_results=dict(agents or {}),
    )


async def clear(pool: asyncpg.Pool, task_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM dag_checkpoints WHERE task_id=$1",
                            UUID(task_id))
