"""V8.5 — Endpoints d'audit des quality gates et validation_score.

GET /api/v1/projects/{id}/quality_gates  - historique des gates pour ce projet
GET /api/v1/projects/{id}/validation     - breakdown detaille du validation_score
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_pool

router = APIRouter()


def _coerce_jsonb(value: Any) -> Any:
    """asyncpg renvoie JSONB en str par defaut — decode si besoin."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


class GateRow(BaseModel):
    attempt_number: int
    gate_name: str
    status: str
    score: float | None
    duration_ms: int
    details: dict[str, Any]
    checked_at: str


class GatesHistoryResponse(BaseModel):
    project_id: str
    total_attempts: int
    gates: list[GateRow]


class ValidationBreakdownResponse(BaseModel):
    project_id: str
    decision: str | None
    total: int | None
    scale: int | None
    components: dict[str, Any]
    rationale: list[str]
    attempts: int
    thresholds: dict[str, int]


@router.get("/{project_id}/quality_gates", response_model=GatesHistoryResponse)
async def get_quality_gates_history(project_id: UUID) -> GatesHistoryResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchval("SELECT id FROM tasks WHERE id = $1", project_id)
        if not task:
            raise HTTPException(404, "Project not found")
        rows = await conn.fetch(
            """
            SELECT attempt_number, gate_name, status, score, duration_ms,
                   details_json AS details, checked_at
              FROM delivery_quality_gates
             WHERE project_id = $1
             ORDER BY attempt_number ASC, checked_at ASC
            """,
            project_id,
        )

    attempts = max((r["attempt_number"] for r in rows), default=0)
    gates = [
        GateRow(
            attempt_number=r["attempt_number"],
            gate_name=r["gate_name"],
            status=r["status"],
            score=float(r["score"]) if r["score"] is not None else None,
            duration_ms=r["duration_ms"],
            details=_coerce_jsonb(r["details"]) or {},
            checked_at=r["checked_at"].isoformat(),
        )
        for r in rows
    ]
    return GatesHistoryResponse(
        project_id=str(project_id),
        total_attempts=attempts,
        gates=gates,
    )


@router.get("/{project_id}/validation", response_model=ValidationBreakdownResponse)
async def get_validation_breakdown(project_id: UUID) -> ValidationBreakdownResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT validation_breakdown_json, validation_attempts,
                   validation_decision
              FROM tasks
             WHERE id = $1
            """,
            project_id,
        )
    if not row:
        raise HTTPException(404, "Project not found")

    breakdown = _coerce_jsonb(row["validation_breakdown_json"]) or {}
    return ValidationBreakdownResponse(
        project_id=str(project_id),
        decision=row["validation_decision"],
        total=breakdown.get("total"),
        scale=breakdown.get("scale"),
        components=breakdown.get("components", {}),
        rationale=breakdown.get("rationale", []),
        attempts=row["validation_attempts"] or 0,
        thresholds=breakdown.get("thresholds", {}),
    )
