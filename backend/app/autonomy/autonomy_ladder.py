"""V5.1 BLOC 4 - Autonomy Ladder.

5 modes pour operer en cas de doute sans interrompre Ahmed :

  CONTINUE  : confiance forte, aucune contrainte -> on avance normalement.
  CONSTRAIN : on reduit le scope (feature flag off, 1 seul shard, read-only)
              mais on AVANCE.
  PROBE     : on lance une action reversible qui teste l'hypothese,
              on mesure, et on decide apres (pas d'escalation).
  DEFER     : on met la decision en attente courte (1-24h) + alerte passive.
  ESCALATE  : vrai appel Ahmed (A/B/C) avec Human Necessity Proof valide.

Selection par rule-based :
  - hard_boundary -> ESCALATE direct
  - score_confidence > 0.92 -> CONTINUE
  - 0.75..0.92 et action reversible -> PROBE
  - 0.6..0.75 et scope reductible -> CONSTRAIN
  - 0.4..0.6 -> DEFER
  - < 0.4 ET proof_of_necessity valid -> ESCALATE
  - < 0.4 sans proof -> DEFER par defaut
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Mode(str, Enum):
    CONTINUE = "CONTINUE"
    CONSTRAIN = "CONSTRAIN"
    PROBE = "PROBE"
    DEFER = "DEFER"
    ESCALATE = "ESCALATE"


@dataclass
class LadderInput:
    confidence: float              # 0..1
    reversible: bool               # l'action peut etre annulee ?
    scope_reducible: bool          # peut-on shrink le scope ?
    hard_boundary: bool            # scope force l'escalation ?
    proof_valid: bool              # human_necessity_proof.proved == True ?
    ambiguity_resolved: bool       # l'ambiguity_resolver a resolu ?
    sub_type: str | None = None    # C1..C6
    criticality: str = "medium"    # low|medium|high|critical


@dataclass
class LadderDecision:
    mode: Mode
    reason: str
    constraints: list[str]         # ex: ["scope=1_shard", "read_only"]

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode.value, "reason": self.reason,
                "constraints": self.constraints}


def decide(inp: LadderInput) -> LadderDecision:
    if inp.hard_boundary:
        return LadderDecision(
            mode=Mode.ESCALATE, constraints=[],
            reason="hard_boundary hit -> legitimate escalation")

    if inp.ambiguity_resolved:
        return LadderDecision(
            mode=Mode.CONTINUE, constraints=[],
            reason="ambiguity resolved via cascade")

    c = inp.confidence
    if c > 0.92:
        return LadderDecision(
            mode=Mode.CONTINUE, constraints=[],
            reason=f"confidence {c:.2f} > 0.92")

    if 0.75 < c <= 0.92 and inp.reversible:
        return LadderDecision(
            mode=Mode.PROBE, reason=f"confidence {c:.2f}, reversible action",
            constraints=["action_is_reversible", "measure_after"])

    if 0.6 < c <= 0.75 and inp.scope_reducible:
        return LadderDecision(
            mode=Mode.CONSTRAIN,
            reason=f"confidence {c:.2f}, scope reducible",
            constraints=["feature_flag_off", "1_shard_only", "read_only_first"])

    if 0.4 < c <= 0.6:
        return LadderDecision(
            mode=Mode.DEFER, constraints=["retry_in_24h"],
            reason=f"confidence {c:.2f} mid-low, defer short")

    if c <= 0.4 and inp.proof_valid:
        return LadderDecision(
            mode=Mode.ESCALATE, constraints=[],
            reason=f"confidence {c:.2f} + proof valid -> ahmed")

    return LadderDecision(
        mode=Mode.DEFER, constraints=["retry_in_24h", "need_more_data"],
        reason=f"confidence {c:.2f} low but no proof -> defer")


def upgrade_for_criticality(
    decision: LadderDecision, criticality: str,
) -> LadderDecision:
    """Si critical, un DEFER devient ESCALATE si proof presente."""
    if criticality == "critical" and decision.mode == Mode.DEFER:
        # Promouvoir en escalade SEULEMENT si critique ; sinon on garde DEFER.
        return LadderDecision(
            mode=Mode.ESCALATE, constraints=decision.constraints,
            reason=f"{decision.reason} + critical criticality")
    return decision
