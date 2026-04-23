"""V4.4 - Decision Router deterministe.

Apres chaque run du pipeline, classifie le resultat en 4 routes :
- robust_success     : PASS + confidence >= 0.95 + 0 invariant viole
- partial_success    : CONDITIONAL_PASS ou confidence 0.80-0.95
- correctable_fail   : SOFT_FAIL + defauts classes local/contract/behavior
- critical_fail      : HARD_FAIL, invariant viole, ou security breach

Aucun LLM implique : purement regle sur les donnees Quality Kernel + pipeline.
Chaque decision est journalisee dans `decision_router_log` + `evidence_ledger`.
Le routeur declenche l'action correspondante (promotion ou rollback) mais
delegue l'execution au Promotion Engine / auto_repair.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

import asyncpg

from app.orchestration import evidence_ledger

logger = logging.getLogger(__name__)


class Route(str, Enum):
    ROBUST_SUCCESS   = "robust_success"
    PARTIAL_SUCCESS  = "partial_success"
    CORRECTABLE_FAIL = "correctable_fail"
    CRITICAL_FAIL    = "critical_fail"


CORRECTABLE_CLASSES = {"local_fix", "contract_fix", "behavior_fix"}
CRITICAL_CLASSES    = {"security_fix", "schema_fix", "vitale"}


@dataclass
class RouterInput:
    task_id: str
    verdict: str                 # PASS | CONDITIONAL_PASS | SOFT_FAIL | HARD_FAIL
    confidence: float            # 0..1 confidence_composite
    invariants_violated: list[str] = field(default_factory=list)
    defect_classes: list[str] = field(default_factory=list)
    has_security_breach: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "verdict": self.verdict,
            "confidence": round(self.confidence, 4),
            "invariants_violated": self.invariants_violated,
            "defect_classes": self.defect_classes,
            "has_security_breach": self.has_security_breach,
        }


@dataclass
class RouterDecision:
    route: Route
    actions: list[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "actions": self.actions,
            "rationale": self.rationale,
        }


def _is_critical(inp: RouterInput) -> bool:
    return (
        inp.verdict == "HARD_FAIL"
        or inp.has_security_breach
        or bool(inp.invariants_violated)
        or any(c in CRITICAL_CLASSES for c in inp.defect_classes)
    )


def _is_correctable(inp: RouterInput) -> bool:
    if inp.verdict != "SOFT_FAIL":
        return False
    if not inp.defect_classes:
        return False
    return all(c in CORRECTABLE_CLASSES for c in inp.defect_classes)


def _is_robust(inp: RouterInput) -> bool:
    return (
        inp.verdict == "PASS"
        and inp.confidence >= 0.95
        and not inp.invariants_violated
        and not inp.has_security_breach
    )


def _is_partial(inp: RouterInput) -> bool:
    if inp.verdict == "CONDITIONAL_PASS":
        return True
    return bool(inp.verdict == "PASS" and 0.8 <= inp.confidence < 0.95)


def classify(inp: RouterInput) -> RouterDecision:
    """Applique la matrice de routage deterministe."""
    if _is_critical(inp):
        return RouterDecision(
            route=Route.CRITICAL_FAIL,
            actions=["rollback_immediate", "isolate_artifact",
                      "create_incident", "escalate_human"],
            rationale=(f"verdict={inp.verdict} security={inp.has_security_breach} "
                       f"invariants={inp.invariants_violated} "
                       f"defects={inp.defect_classes}"),
        )
    if _is_robust(inp):
        return RouterDecision(
            route=Route.ROBUST_SUCCESS,
            actions=["promote_to_staging", "smoke_test", "canary_deploy",
                      "promote_to_production"],
            rationale=f"PASS + confidence {inp.confidence:.3f} >= 0.95, 0 invariant",
        )
    if _is_partial(inp):
        return RouterDecision(
            route=Route.PARTIAL_SUCCESS,
            actions=["add_supplementary_tests", "lower_displayed_confidence",
                      "notify_ceo"],
            rationale=(f"verdict={inp.verdict} confidence={inp.confidence:.3f} "
                       "dans la zone partielle"),
        )
    if _is_correctable(inp):
        return RouterDecision(
            route=Route.CORRECTABLE_FAIL,
            actions=["tri_brain_remediation", "replay_impacted_layers"],
            rationale=(f"SOFT_FAIL corrigeable (classes="
                       f"{inp.defect_classes})"),
        )
    # Cas residuel : SOFT_FAIL sans classe connue = prudence -> critical
    return RouterDecision(
        route=Route.CRITICAL_FAIL,
        actions=["rollback_immediate", "escalate_human"],
        rationale=(f"verdict={inp.verdict} sans classe corrigeable identifiee, "
                    "principe de prudence"),
    )


async def route_and_log(
    pool: asyncpg.Pool, inp: RouterInput,
) -> RouterDecision:
    """Classifie + persiste dans decision_router_log + evidence_ledger."""
    decision = classify(inp)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO decision_router_log
              (task_id, route, verdict, confidence,
               invariants_violated, defect_classes, actions_taken, rationale)
            VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,$8)
            """,
            UUID(inp.task_id), decision.route.value, inp.verdict,
            inp.confidence,
            json.dumps(inp.invariants_violated),
            json.dumps(inp.defect_classes),
            json.dumps(decision.actions),
            decision.rationale,
        )
    await evidence_ledger.record(
        pool, kind="decision", actor="decision_router",
        payload={"input": inp.to_dict(), "decision": decision.to_dict()},
        task_id=inp.task_id,
    )
    logger.info("decision_router task=%s route=%s",
                inp.task_id, decision.route.value)
    return decision


async def history(
    pool: asyncpg.Pool, limit: int = 50,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, task_id, route, verdict, confidence,
                   actions_taken, rationale, created_at
            FROM decision_router_log
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    out = []
    for r in rows:
        actions = r["actions_taken"]
        if isinstance(actions, str):
            actions = json.loads(actions)
        out.append({
            "id": str(r["id"]),
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "route": r["route"], "verdict": r["verdict"],
            "confidence": float(r["confidence"] or 0),
            "actions": actions or [],
            "rationale": r["rationale"],
            "created_at": r["created_at"].isoformat(),
        })
    return out


async def route_distribution(pool: asyncpg.Pool) -> dict[str, int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT route, COUNT(*) AS n FROM decision_router_log GROUP BY route"
        )
    return {r["route"]: int(r["n"]) for r in rows}
