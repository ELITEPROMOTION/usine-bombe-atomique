"""V5.1 BLOC 4 - Autonomy Governor.

Orchestrateur : recoit un "point de decision" et decide autonomie vs
escalation, en combinant :
  - ambiguity_resolver (4 niveaux)
  - hard_boundary_registry
  - permission_lease_manager
  - human_necessity_proof
  - autonomy_ladder (5 modes)

Usage cote agent :
    gov = await governor.decide_next(pool, DecisionPoint(...))
    if gov.mode == Mode.CONTINUE:
        ...execute plan...
    elif gov.mode == Mode.ESCALATE:
        await user_interaction_router.request_user(...)
    elif gov.mode in (PROBE, CONSTRAIN, DEFER):
        ...execute with constraints...
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg

from app.autonomy import (
    autonomy_ladder,
    human_necessity_proof,
    permission_lease_manager,
)
from app.autonomy.autonomy_ladder import LadderDecision, LadderInput, Mode
from app.autonomy.human_necessity_proof import NecessityEvidence

logger = logging.getLogger(__name__)


@dataclass
class DecisionPoint:
    scope: str                       # ex: "payment.datadog"
    form_type: str                   # 'A'|'B'|'C'
    c_sub_type: str | None           # C1..C6
    question_or_reason: str
    context: str = ""
    confidence: float = 0.75         # 0..1
    reversible: bool = True
    scope_reducible: bool = True
    criticality: str = "medium"
    task_id: str | None = None
    correlation_id: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class GovernorDecision:
    mode: Mode
    reason: str
    constraints: list[str]
    proof_hash: str | None
    proved: bool
    ladder_reason: str
    used_lease_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value, "reason": self.reason,
            "constraints": self.constraints,
            "proof_hash": self.proof_hash, "proved": self.proved,
            "ladder_reason": self.ladder_reason,
            "used_lease_id": self.used_lease_id,
        }


async def decide_next(
    pool: asyncpg.Pool, dp: DecisionPoint,
) -> GovernorDecision:
    # Step 1 : construct evidence and try to prove necessity
    ev = NecessityEvidence(
        form_type=dp.form_type, c_sub_type=dp.c_sub_type,
        scope=dp.scope, task_id=dp.task_id,
        correlation_id=dp.correlation_id,
        question_or_reason=dp.question_or_reason,
        context=dp.context,
    )
    verdict = await human_necessity_proof.prove(pool, ev)

    # Fast path : lease already covers -> CONTINUE without ask
    if ev.lease_covers:
        lease = await permission_lease_manager.find_active(pool, dp.scope)
        if lease:
            await permission_lease_manager.consume(pool, lease.id)
            await human_necessity_proof.persist(pool, verdict)
            return GovernorDecision(
                mode=Mode.CONTINUE, reason="lease actif consomme",
                constraints=[], proof_hash=verdict.proof_hash, proved=False,
                ladder_reason="lease path", used_lease_id=lease.id,
            )

    ladder_in = LadderInput(
        confidence=dp.confidence,
        reversible=dp.reversible,
        scope_reducible=dp.scope_reducible,
        hard_boundary=bool(ev.hard_boundary_hit),
        proof_valid=verdict.proved,
        ambiguity_resolved=(not verdict.proved
                             and any(L.get("resolved")
                                     for L in ev.levels_tried)),
        sub_type=dp.c_sub_type,
        criticality=dp.criticality,
    )
    ladder = autonomy_ladder.decide(ladder_in)
    ladder = autonomy_ladder.upgrade_for_criticality(ladder, dp.criticality)

    # Log proof and decision
    await human_necessity_proof.persist(pool, verdict)
    await _log_decision(pool, dp, verdict.proof_hash, ladder)

    return GovernorDecision(
        mode=ladder.mode, reason=verdict.reason,
        constraints=ladder.constraints,
        proof_hash=verdict.proof_hash, proved=verdict.proved,
        ladder_reason=ladder.reason,
    )


async def _log_decision(
    pool: asyncpg.Pool, dp: DecisionPoint, proof_hash: str, ladder: LadderDecision,
) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_events(
                    task_id, action, actor, payload_hash, payload_json)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                UUID(dp.task_id) if dp.task_id else None,
                "autonomy_decision", "governor",
                hashlib.sha256((proof_hash or "").encode()).hexdigest(),
                json.dumps({
                    "scope": dp.scope, "form_type": dp.form_type,
                    "sub_type": dp.c_sub_type,
                    "confidence": dp.confidence,
                    "proof_hash": proof_hash[:16],
                    "mode": ladder.mode.value,
                    "constraints": ladder.constraints,
                    "correlation_id": dp.correlation_id,
                }),
            )
    except Exception as exc:
        logger.debug("governor log failed: %s", exc)
