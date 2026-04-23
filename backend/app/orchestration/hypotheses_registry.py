"""Hypotheses Registry V4.1 - tracking des assumptions non resolues.

Chaque agent peut enregistrer une hypothese quand il prend une decision
basee sur une assumption (ex : "je suppose que la TVA cible est 19% sauf
mention contraire"). Tant que l'hypothese est `open`, elle doit etre
visible et resolue explicitement avant cloture de la tache.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    description: str
    source: str
    owner: str | None = None
    impact_si_faux: str = ""
    plan_b: str = ""
    severity: str = "medium"  # low | medium | high | critical


async def record(
    pool: asyncpg.Pool,
    task_id: str,
    hypothesis: Hypothesis,
) -> str:
    """Insere une hypothese non resolue et retourne son id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO hypotheses
              (task_id, description, source, owner, impact_si_faux, plan_b, severity)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            UUID(task_id), hypothesis.description[:4000], hypothesis.source,
            hypothesis.owner, hypothesis.impact_si_faux[:2000],
            hypothesis.plan_b[:2000], hypothesis.severity,
        )
    return str(row["id"])


async def resolve(
    pool: asyncpg.Pool,
    hypothesis_id: str,
    new_status: str,
    resolution_evidence_id: str | None = None,
) -> bool:
    """Resout une hypothese (verified | refuted | accepted_risk | dropped)."""
    if new_status not in {"verified", "refuted", "accepted_risk", "dropped"}:
        raise ValueError(f"Statut invalide: {new_status}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE hypotheses
            SET statut = $2, resolved_at = NOW(),
                resolution_evidence_id = $3
            WHERE id = $1 AND statut = 'open'
            RETURNING id
            """,
            UUID(hypothesis_id), new_status,
            UUID(resolution_evidence_id) if resolution_evidence_id else None,
        )
    return row is not None


async def list_open(pool: asyncpg.Pool, task_id: str | None = None,
                     limit: int = 50) -> list[dict[str, Any]]:
    """Retourne les hypotheses ouvertes (optionnellement filtrees par tache)."""
    async with pool.acquire() as conn:
        if task_id:
            rows = await conn.fetch(
                """
                SELECT id, task_id, description, source, owner, impact_si_faux,
                       plan_b, statut, severity, created_at
                FROM hypotheses WHERE statut = 'open' AND task_id = $1
                ORDER BY severity DESC, created_at DESC LIMIT $2
                """, UUID(task_id), limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, task_id, description, source, owner, impact_si_faux,
                       plan_b, statut, severity, created_at
                FROM hypotheses WHERE statut = 'open'
                ORDER BY severity DESC, created_at DESC LIMIT $1
                """, limit,
            )
    return [
        {
            "id": str(r["id"]),
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "description": r["description"],
            "source": r["source"],
            "owner": r["owner"],
            "impact_si_faux": r["impact_si_faux"],
            "plan_b": r["plan_b"],
            "statut": r["statut"],
            "severity": r["severity"],
            "created_at": r["created_at"].isoformat(),
        } for r in rows
    ]


async def count_open_critical(pool: asyncpg.Pool, task_id: str) -> int:
    """Compte les hypotheses critical/high ouvertes pour une tache (gate)."""
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            """
            SELECT COUNT(*) FROM hypotheses
            WHERE task_id = $1 AND statut = 'open'
              AND severity IN ('critical','high')
            """, UUID(task_id),
        )
    return int(n or 0)
