"""V5.4 - Meta-Cognition (command center).

Raisonne sur la MANIERE dont le systeme raisonne (cognition 2e ordre).
Pas de raisonnement metier ici ; strategie + allocation ressources + monitoring.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.cognition.reasoning_trace_models import MetaCognitiveReport, ProblemType

# Patterns de classification probleme
PATTERNS: dict[ProblemType, list[re.Pattern[str]]] = {
    "simple":     [re.compile(r"\b(what is|qu'est-ce que|combien|when|quand)\b", re.I)],
    "moderate":   [re.compile(r"\b(compare|analyse|explain|calculate)\b", re.I)],
    "complex":    [re.compile(r"\b(design|architect|plan|strategy|multi-step|critical)\b", re.I)],
    "creative":   [re.compile(r"\b(creative|brainstorm|invent|generate|imagine)\b", re.I)],
    "sequential": [re.compile(r"\b(schedule|allocate|sequence|step-by-step|plan)\b", re.I)],
    "ambiguous":  [re.compile(r"\b(ambiguous|unclear|should we|faut-il|maybe)\b", re.I)],
}


# Strategie → ensemble de techniques a appliquer
STRATEGY_MAP: dict[ProblemType, dict[str, Any]] = {
    "simple": {
        "techniques": ["zero_shot_cot"],
        "max_tokens": 5_000, "max_iterations": 3,
        "can_shortcut": True,
    },
    "moderate": {
        "techniques": ["structured_cot", "self_consistent", "reflexion"],
        "max_tokens": 20_000, "max_iterations": 8,
        "can_shortcut": False,
    },
    "complex": {
        "techniques": ["self_discover", "tree_of_thoughts",
                        "graph_of_thoughts", "debate", "constitutional"],
        "max_tokens": 50_000, "max_iterations": 30,
        "can_shortcut": False,
    },
    "creative": {
        "techniques": ["tree_of_thoughts", "reflexion",
                        "bias_detection", "recursive_refinement"],
        "max_tokens": 40_000, "max_iterations": 20,
        "can_shortcut": False,
    },
    "sequential": {
        "techniques": ["mcts", "react", "meta_cognition"],
        "max_tokens": 30_000, "max_iterations": 15,
        "can_shortcut": False,
    },
    "ambiguous": {
        "techniques": ["debate", "multi_perspective", "uncertainty"],
        "max_tokens": 30_000, "max_iterations": 12,
        "can_shortcut": False,
    },
}


@dataclass
class MetaDecision:
    problem_type: ProblemType
    strategy_techniques: list[str]
    budget_tokens: int
    budget_iterations: int
    can_shortcut: bool
    reasoning: str


def classify_problem(statement: str) -> ProblemType:
    """Classifie le type de probleme par heuristique."""
    lowered = (statement or "").lower()
    scores: dict[ProblemType, int] = {}
    for ptype, patterns in PATTERNS.items():
        n = sum(1 for p in patterns if p.search(lowered))
        if n:
            scores[ptype] = n
    if not scores:
        # Fallback sur longueur
        if len(statement) > 500:
            return "complex"
        if len(statement) > 150:
            return "moderate"
        return "simple"
    # Priorite aux plus complexes si egalite
    order = ["complex", "creative", "sequential", "ambiguous",
             "moderate", "simple"]
    best = max(scores.items(), key=lambda kv: (kv[1], -order.index(kv[0])))
    return best[0]


def decide_strategy(
    statement: str, *, criticality: str = "medium",
) -> MetaDecision:
    ptype = classify_problem(statement)
    strat = STRATEGY_MAP[ptype].copy()
    # Boost budget si critical
    if criticality == "critical":
        strat["max_tokens"] = int(strat["max_tokens"] * 2)
        strat["max_iterations"] = int(strat["max_iterations"] * 1.5)
        strat["can_shortcut"] = False
    return MetaDecision(
        problem_type=ptype,
        strategy_techniques=list(strat["techniques"]),
        budget_tokens=strat["max_tokens"],
        budget_iterations=strat["max_iterations"],
        can_shortcut=strat["can_shortcut"],
        reasoning=f"classified as {ptype}, criticality={criticality}",
    )


def detect_stuck(
    last_states: list[str], new_state: str, threshold: int = 3,
) -> bool:
    """Detecte si on est dans un stuck state (repeat identique)."""
    if not last_states:
        return False
    occurrences = sum(1 for s in last_states[-threshold:] if s == new_state)
    return occurrences >= threshold


def detect_loop(trajectory: list[str], window: int = 6) -> bool:
    """Detecte une boucle (sequence repetee dans la trajectoire)."""
    if len(trajectory) < window * 2:
        return False
    recent = tuple(trajectory[-window:])
    prior = tuple(trajectory[-2 * window:-window])
    return recent == prior


def build_report(
    decision: MetaDecision, *,
    stuck_states: int = 0, loops: int = 0, stop_reason: str | None = None,
) -> MetaCognitiveReport:
    return MetaCognitiveReport(
        problem_class=decision.problem_type,
        strategy_selected=",".join(decision.strategy_techniques),
        resources_allocated={
            "tokens": decision.budget_tokens,
            "iterations": decision.budget_iterations,
            "can_shortcut": decision.can_shortcut,
        },
        stuck_states_detected=stuck_states,
        loops_detected=loops,
        stop_reason=stop_reason,
    )
