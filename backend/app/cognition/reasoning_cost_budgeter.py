"""V5.4 AJOUT CLAUDE 6 - Reasoning Cost Budgeter.

Allocation adaptative par criticite :
- P0 critical : illimite (dans kill-switch)
- P1 important : 50k tokens
- P2 secondaire : 20k tokens
- P3 accessoire : 5k tokens
"""
from __future__ import annotations

from dataclasses import dataclass


BUDGETS = {
    "P0": 10**9,     # "illimite" (borne par kill-switch)
    "P1": 50_000,
    "P2": 20_000,
    "P3":  5_000,
}


TOKEN_COST_PER_1M_IN = 3.0
TOKEN_COST_PER_1M_OUT = 15.0


@dataclass
class BudgetAllocation:
    tier: str
    tokens_max: int
    est_cost_max_usd: float


def allocate(tier: str = "P2") -> BudgetAllocation:
    t = tier.upper()
    if t not in BUDGETS:
        raise ValueError(f"unknown tier {tier}")
    tokens = BUDGETS[t]
    est_cost = (tokens / 1e6) * (TOKEN_COST_PER_1M_IN + TOKEN_COST_PER_1M_OUT) / 2
    return BudgetAllocation(tier=t, tokens_max=tokens, est_cost_max_usd=est_cost)


def consumed_ratio(tokens_used: int, tier: str) -> float:
    b = BUDGETS[tier.upper()]
    if b <= 0:
        return 1.0
    return min(1.0, tokens_used / b)


def classify_criticality(
    problem_type: str, criticality: str,
) -> str:
    """Mappe (problem_type, criticality) -> tier budget."""
    if criticality in ("critical", "P0"):
        return "P0"
    if problem_type == "complex":
        return "P1"
    if problem_type in ("moderate", "sequential", "creative", "ambiguous"):
        return "P2"
    return "P3"
