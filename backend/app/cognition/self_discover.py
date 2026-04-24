"""V5.4 - Self-Discover (Zhou 2024).

3 VERBES : SELECT -> ADAPT -> IMPLEMENT.
Bibliotheque 10 modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MODULES = [
    "break_down", "critical_thinking", "step_by_step",
    "creative_thinking", "systems_thinking", "risk_analysis",
    "reflective_thinking", "hypothesis_generation",
    "analogical_reasoning", "meta_cognition",
]


# Module -> types de problemes ou il est pertinent
MODULE_AFFINITY = {
    "break_down":            {"complex", "moderate", "sequential"},
    "critical_thinking":     {"complex", "ambiguous"},
    "step_by_step":          {"simple", "moderate", "sequential"},
    "creative_thinking":     {"creative"},
    "systems_thinking":      {"complex"},
    "risk_analysis":         {"complex", "ambiguous"},
    "reflective_thinking":   {"moderate", "complex", "creative"},
    "hypothesis_generation": {"complex", "creative"},
    "analogical_reasoning":  {"creative", "ambiguous"},
    "meta_cognition":        {"complex", "ambiguous"},
}


# Cout cognitif approximatif par module (0..1)
MODULE_COST = {
    "break_down":            0.15, "critical_thinking":     0.30,
    "step_by_step":          0.15, "creative_thinking":     0.35,
    "systems_thinking":      0.45, "risk_analysis":         0.30,
    "reflective_thinking":   0.25, "hypothesis_generation": 0.30,
    "analogical_reasoning":  0.20, "meta_cognition":        0.40,
}


@dataclass
class SelfDiscoverPlan:
    problem_type: str
    selected_modules: list[str]
    adapted_prompts: dict[str, str]
    implementation_order: list[str]
    total_cost_estimate: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def select(problem_type: str, *, max_modules: int = 4,
           cost_budget: float = 1.0) -> list[str]:
    """SELECT modules pertinents pour le type probleme, sous budget."""
    candidates = [m for m in MODULES
                  if problem_type in MODULE_AFFINITY.get(m, set())]
    # Trier par cost ascendant
    candidates.sort(key=lambda m: MODULE_COST[m])
    selected: list[str] = []
    used = 0.0
    for m in candidates:
        if len(selected) >= max_modules:
            break
        if used + MODULE_COST[m] > cost_budget:
            continue
        selected.append(m)
        used += MODULE_COST[m]
    if not selected:
        # Minimum 1 module
        selected = ["step_by_step"]
    return selected


def adapt(selected: list[str], problem_statement: str) -> dict[str, str]:
    """ADAPT : prompts adaptes au probleme pour chaque module."""
    excerpt = problem_statement[:120]
    return {
        m: f"[{m.upper()}] For: {excerpt}..." for m in selected
    }


def implement(adapted_prompts: dict[str, str]) -> list[str]:
    """IMPLEMENT : ordre d'execution suggere."""
    # Order by cost ascendant
    ordered = sorted(
        adapted_prompts.keys(),
        key=lambda m: MODULE_COST.get(m, 1.0))
    return ordered


def plan(
    problem_statement: str, problem_type: str, *,
    cost_budget: float = 1.0, max_modules: int = 4,
) -> SelfDiscoverPlan:
    selected = select(problem_type, max_modules=max_modules,
                       cost_budget=cost_budget)
    adapted = adapt(selected, problem_statement)
    order = implement(adapted)
    total_cost = sum(MODULE_COST[m] for m in selected)
    return SelfDiscoverPlan(
        problem_type=problem_type,
        selected_modules=selected,
        adapted_prompts=adapted,
        implementation_order=order,
        total_cost_estimate=total_cost,
    )
