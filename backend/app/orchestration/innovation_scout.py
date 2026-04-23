"""Upgrade 37 - Innovation Pipeline.

Toute nouveaute (modele LLM, librairie, outil, strategie) passe par un
cycle de 8 etapes. Aucune integration directe.

Etapes (`stage`):
  scout -> qualification -> benchmark -> risk_review -> pending_approval
        -> staged -> active -> (rollback possible)
Rejet possible a tout moment (rejected).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

STAGES = ("scout", "qualification", "benchmark", "risk_review",
          "pending_approval", "staged", "active", "rollback", "rejected")

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "scout":            ("qualification", "rejected"),
    "qualification":    ("benchmark", "rejected"),
    "benchmark":        ("risk_review", "rejected"),
    "risk_review":      ("pending_approval", "rejected"),
    "pending_approval": ("staged", "rejected"),
    "staged":           ("active", "rollback", "rejected"),
    "active":           ("rollback",),
    "rollback":         (),
    "rejected":         (),
}


@dataclass
class InnovationItem:
    id: str
    kind: str
    name: str
    summary: str
    stage: str
    benchmark_score: float | None
    approved_by: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "name": self.name,
            "summary": self.summary, "stage": self.stage,
            "benchmark_score": self.benchmark_score,
            "approved_by": self.approved_by,
        }


async def submit(
    pool: asyncpg.Pool, *, kind: str, name: str, summary: str,
) -> str:
    if kind not in ("model", "library", "tool", "strategy"):
        raise ValueError(f"kind inconnu: {kind}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO innovation_items (kind, name, summary, stage)
            VALUES ($1, $2, $3, 'scout')
            ON CONFLICT (kind, name) DO UPDATE SET summary = EXCLUDED.summary
            RETURNING id
            """,
            kind, name[:200], summary,
        )
    return str(row["id"])


async def advance(
    pool: asyncpg.Pool, item_id: str, to_stage: str,
    actor: str | None = None, benchmark_score: float | None = None,
    risk_notes: str | None = None,
) -> bool:
    """Avance l'item au `to_stage` si la transition est valide."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT stage FROM innovation_items WHERE id=$1", UUID(item_id),
        )
        if not row:
            return False
        current = row["stage"]
        allowed = TRANSITIONS.get(current, ())
        if to_stage not in allowed:
            raise ValueError(
                f"Transition interdite : {current} -> {to_stage}. "
                f"Autorise : {allowed}"
            )
        fields_sql = ["stage = $2"]
        params: list[Any] = [UUID(item_id), to_stage]
        if benchmark_score is not None:
            fields_sql.append(f"benchmark_score = ${len(params) + 1}")
            params.append(benchmark_score)
        if risk_notes is not None:
            fields_sql.append(f"risk_notes = ${len(params) + 1}")
            params.append(risk_notes)
        if to_stage == "staged" and actor:
            fields_sql.append(f"approved_by = ${len(params) + 1}")
            params.append(actor)
            fields_sql.append("approved_at = NOW()")
        if to_stage == "active":
            fields_sql.append("activated_at = NOW()")
        if to_stage == "rollback":
            fields_sql.append("rolled_back_at = NOW()")
        sql = f"UPDATE innovation_items SET {', '.join(fields_sql)} WHERE id = $1"
        await conn.execute(sql, *params)
    return True


async def list_all(pool: asyncpg.Pool, stage: str | None = None) -> list[dict[str, Any]]:
    q = """
    SELECT id, kind, name, summary, stage, benchmark_score, approved_by
    FROM innovation_items
    """
    args: list[Any] = []
    if stage:
        q += " WHERE stage = $1"
        args.append(stage)
    q += " ORDER BY created_at DESC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *args)
    return [
        {"id": str(r["id"]), "kind": r["kind"], "name": r["name"],
         "summary": r["summary"], "stage": r["stage"],
         "benchmark_score": float(r["benchmark_score"]) if r["benchmark_score"] else None,
         "approved_by": r["approved_by"]}
        for r in rows
    ]
