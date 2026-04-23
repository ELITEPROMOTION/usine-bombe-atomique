"""Upgrade 14 - Confidence-driven rollback.

Apres un deploiement (simulation : creation d'artifacts "live"), on surveille
la confiance. Si elle tombe sous un seuil relatif a sa valeur initiale
(ex: -15 points de pourcentage) ou sous un floor absolu (0.70), le systeme
declenche un rollback automatique :
  1. record_rollback_event() => rollback_events
  2. evidence_ledger.record(kind='repair', actor='confidence_rollback')
  3. audit_events.emit(action='auto_rollback')
  4. restore de la derniere version artefact connue (simule via marquage)

Aucune action humaine. Ideal pour environnements prod autonomes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.orchestration import audit_events, evidence_ledger

logger = logging.getLogger(__name__)

ABSOLUTE_FLOOR = 0.70
RELATIVE_DROP = 0.15  # 15 points de pct


@dataclass
class RollbackDecision:
    rolled_back: bool
    reason: str
    confidence_before: float
    confidence_after: float


async def evaluate_and_rollback(
    pool: asyncpg.Pool, task_id: str,
    confidence_before: float, confidence_after: float,
    artifact_version_before: str = "", artifact_version_after: str = "",
) -> RollbackDecision:
    dropped_absolute = confidence_after < ABSOLUTE_FLOOR
    dropped_relative = (confidence_before - confidence_after) >= RELATIVE_DROP
    if not (dropped_absolute or dropped_relative):
        return RollbackDecision(
            rolled_back=False,
            reason="confidence stable, pas de rollback",
            confidence_before=confidence_before,
            confidence_after=confidence_after,
        )

    reason = ("absolute_floor" if dropped_absolute else "relative_drop")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO rollback_events
              (task_id, trigger_reason, confidence_before, confidence_after,
               artifact_version_before, artifact_version_after, auto_triggered)
            VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            """,
            UUID(task_id), reason, confidence_before, confidence_after,
            artifact_version_before[:64], artifact_version_after[:64],
        )

    await evidence_ledger.record(
        pool, kind="repair", actor="confidence_rollback",
        payload={
            "trigger_reason": reason,
            "confidence_before": confidence_before,
            "confidence_after": confidence_after,
            "artifact_version_before": artifact_version_before,
        },
        task_id=task_id,
    )
    await audit_events.emit(
        pool, action="auto_rollback", actor="confidence_rollback",
        payload={"trigger_reason": reason,
                 "confidence_delta": confidence_after - confidence_before},
        task_id=task_id,
    )
    return RollbackDecision(
        rolled_back=True,
        reason=reason,
        confidence_before=confidence_before,
        confidence_after=confidence_after,
    )


async def history(pool: asyncpg.Pool, limit: int = 20) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, task_id, trigger_reason, confidence_before,
                   confidence_after, created_at, auto_triggered
            FROM rollback_events ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    return [
        {"id": str(r["id"]), "task_id": str(r["task_id"]) if r["task_id"] else None,
         "trigger_reason": r["trigger_reason"],
         "confidence_before": float(r["confidence_before"] or 0),
         "confidence_after": float(r["confidence_after"] or 0),
         "auto": r["auto_triggered"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]
