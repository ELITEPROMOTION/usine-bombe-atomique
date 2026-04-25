"""V5.3 BLOC 11 - Phase Gate Enforcer.

5 gates nommes. Validation automatique et blocage bloquant.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.ctc import evidence_chain, seven_layer_validator

logger = logging.getLogger(__name__)


GATE_DEFINITIONS = {
    "design_to_build":    ("design", "build"),
    "build_to_validate":  ("build", "validate"),
    "validate_to_release": ("validate", "release"),
    "release_to_operate":  ("release", "operate"),
    "operate_to_rework":   ("operate", "rework"),
}


@dataclass
class GateDecision:
    gate_id: str
    name: str
    status: str                    # open | closed | pending | rework
    validation_verdict: str | None
    reasons: list[str]
    evidence_chain_ref: str | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


async def validate(
    pool: asyncpg.Pool, *,
    name: str, task_id: str, actor: str = "ctc.phase_gate",
    context: dict[str, Any] | None = None,
) -> GateDecision:
    """Valide un gate. Cree la ligne phase_gates, execute 7 couches, decide."""
    if name not in GATE_DEFINITIONS:
        raise ValueError(f"gate inconnu : {name}")
    phase_from, phase_to = GATE_DEFINITIONS[name]
    ctx = dict(context or {})
    report = await seven_layer_validator.validate(pool, ctx)
    open_now = report.verdict in ("PASS", "CONDITIONAL_PASS")
    status = "open" if open_now else "closed"

    # Evidence chain event
    chain_event = await evidence_chain.append(
        pool, actor_type="system", actor_id=f"phase_gate:{name}",
        input_payload={"gate": name, "context": ctx},
        output_payload=report.to_dict(),
        verdict=report.verdict,
        task_id=task_id,
        justification=f"Phase gate {name} {phase_from}→{phase_to}",
    )

    # Persist gate
    now_opened = status == "open"
    now_closed = status == "closed"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO phase_gates(task_id, phase_from, phase_to, status,
                validation_result, evidence_chain_ref, actor, opened_at, closed_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7,
                    CASE WHEN $8 THEN NOW() ELSE NULL END,
                    CASE WHEN $9 THEN NOW() ELSE NULL END)
            RETURNING gate_id
            """,
            UUID(task_id), phase_from, phase_to, status,
            json.dumps(report.to_dict()),
            UUID(chain_event.event_id),
            actor[:120],
            now_opened, now_closed,
        )
        gate_id = str(row["gate_id"])
        if status == "closed":
            reasons_summary = (f"verdict={report.verdict} first_fail={report.first_fail}")
            await conn.execute(
                """
                INSERT INTO phase_gate_failures(
                    gate_id, reason_code, reason_text, layers_failed)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                UUID(gate_id), (report.first_fail or "unknown")[:40],
                reasons_summary,
                json.dumps([layer.name for layer in report.layers if not layer.passed]),
            )

    return GateDecision(
        gate_id=gate_id, name=name, status=status,
        validation_verdict=report.verdict,
        reasons=[layer.name for layer in report.layers if not layer.passed],
        evidence_chain_ref=chain_event.event_id,
    )


async def can_promote(
    pool: asyncpg.Pool, task_id: str, from_phase: str, to_phase: str,
) -> dict[str, Any]:
    """Check si un gate ouvert existe pour cette transition."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT gate_id, status, closed_at, opened_at
            FROM phase_gates
            WHERE task_id = $1 AND phase_from = $2 AND phase_to = $3
              AND status = 'open'
            ORDER BY created_at DESC LIMIT 1
            """, UUID(task_id), from_phase, to_phase,
        )
    return {
        "can_promote": row is not None,
        "gate_id": str(row["gate_id"]) if row else None,
    }


async def list_for_task(
    pool: asyncpg.Pool, task_id: str,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT gate_id, phase_from, phase_to, status, opened_at,
                   closed_at, created_at
            FROM phase_gates WHERE task_id = $1 ORDER BY created_at ASC
            """, UUID(task_id),
        )
    return [{
        "gate_id": str(r["gate_id"]),
        "phase_from": r["phase_from"], "phase_to": r["phase_to"],
        "status": r["status"],
        "opened_at": r["opened_at"].isoformat() if r["opened_at"] else None,
        "closed_at": r["closed_at"].isoformat() if r["closed_at"] else None,
        "created_at": r["created_at"].isoformat(),
    } for r in rows]


async def distribution(pool: asyncpg.Pool) -> dict[str, int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM phase_gates GROUP BY status"
        )
    return {r["status"]: int(r["n"]) for r in rows}
