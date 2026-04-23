"""Prompt A/B Testing V3 - variantes de system prompt par agent.

Chaque agent peut avoir plusieurs variantes de system prompt. On tire au
hasard ponderee une variante a chaque run, on enregistre son score au
retour (validation/confidence), et on met a jour l'`avg_score` rolling.
Le `weight` peut etre pilote manuellement ou recalcule periodiquement.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class PromptVariant:
    id: str
    agent_id: str
    variant_name: str
    system_prompt: str
    weight: float


async def list_variants(pool: asyncpg.Pool, agent_id: str) -> list[PromptVariant]:
    """Liste les variantes de prompt actives pour un agent."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, agent_id, variant_name, system_prompt, weight
            FROM prompt_variants
            WHERE agent_id = $1 AND is_active = TRUE
            ORDER BY variant_name
            """,
            agent_id,
        )
    return [
        PromptVariant(
            id=str(r["id"]), agent_id=r["agent_id"],
            variant_name=r["variant_name"], system_prompt=r["system_prompt"],
            weight=float(r["weight"]),
        )
        for r in rows
    ]


async def pick_variant(pool: asyncpg.Pool, agent_id: str,
                       default_prompt: str | None = None) -> tuple[PromptVariant | None, str]:
    """Tire au hasard une variante active pour `agent_id`. Si aucune n'existe,
    renvoie (None, default_prompt). Tirage ponder par la colonne `weight`."""
    variants = await list_variants(pool, agent_id)
    if not variants:
        return None, (default_prompt or "")
    weights = [max(0.001, v.weight) for v in variants]
    chosen = random.choices(variants, weights=weights, k=1)[0]
    return chosen, chosen.system_prompt


async def record_outcome(
    pool: asyncpg.Pool,
    variant_id: str,
    score: float,
    won: bool = False,
) -> None:
    """Met a jour exec counter + rolling avg score + wins."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT avg_score, score_samples FROM prompt_variants WHERE id=$1",
            UUID(variant_id),
        )
        if not row:
            return
        n = int(row["score_samples"])
        new_avg = (float(row["avg_score"]) * n + score) / (n + 1)
        await conn.execute(
            """
            UPDATE prompt_variants
            SET executions = executions + 1,
                wins = wins + $2,
                score_samples = score_samples + 1,
                avg_score = $3
            WHERE id = $1
            """,
            UUID(variant_id), 1 if won else 0, new_avg,
        )


async def variants_summary(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Resume tabulaire de toutes les variantes (win rate, avg score) pour UI."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent_id, variant_name, weight, executions, wins,
                   avg_score, is_active, created_at
            FROM prompt_variants ORDER BY agent_id, variant_name
            """
        )
    return [
        {
            "agent_id": r["agent_id"],
            "variant_name": r["variant_name"],
            "weight": float(r["weight"]),
            "executions": r["executions"],
            "wins": r["wins"],
            "win_rate": (r["wins"] / r["executions"]) if r["executions"] else 0.0,
            "avg_score": float(r["avg_score"]),
            "is_active": r["is_active"],
        }
        for r in rows
    ]
