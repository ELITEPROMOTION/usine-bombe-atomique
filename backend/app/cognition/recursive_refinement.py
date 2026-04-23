"""V5.4 - Recursive Refinement (8 niveaux).

0=brute 1=fix_obvious 2=detail 3=perf 4=clarity 5=security
6=compliance 7=meta_review
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


LEVELS = [
    ("raw", "Solution brute"),
    ("fix_obvious", "Correction erreurs evidentes"),
    ("detail", "Affinage details techniques"),
    ("performance", "Optimisation performance"),
    ("clarity", "Clarity/maintainability"),
    ("security", "Security review"),
    ("compliance", "Compliance check"),
    ("meta_review", "Meta-review approche globale"),
]


@dataclass
class RefinementStep:
    level: int
    name: str
    description: str
    improvement_delta: float
    stopped_here: bool = False
    reason: str | None = None


@dataclass
class RefinementResult:
    steps: list[RefinementStep]
    final_level_reached: int
    final_solution: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.__dict__ for s in self.steps],
            "final_level": self.final_level_reached,
            "final_solution": self.final_solution[:1000],
        }


MARGINAL_DELTA = 0.01


def _default_refiner(
    solution: str, level_name: str,
) -> tuple[str, float]:
    """Deterministic refiner : ajoute un tag + delta simule."""
    suffix = f"\n# refined[{level_name}]"
    delta = {"raw": 0.0, "fix_obvious": 0.08, "detail": 0.04,
             "performance": 0.06, "clarity": 0.03, "security": 0.05,
             "compliance": 0.04, "meta_review": 0.02}.get(level_name, 0.01)
    return solution + suffix, delta


def refine(
    initial_solution: str, *,
    target_level: int = 7, budget_levels: int = 8,
    refiner: Callable[[str, str], tuple[str, float]] | None = None,
) -> RefinementResult:
    refiner = refiner or _default_refiner
    steps: list[RefinementStep] = []
    current = initial_solution
    final_level = 0
    for idx, (name, desc) in enumerate(LEVELS[:budget_levels]):
        if idx > target_level:
            steps.append(RefinementStep(
                level=idx, name=name, description=desc,
                improvement_delta=0.0,
                stopped_here=True, reason="target_level_reached"))
            break
        current, delta = refiner(current, name)
        stopped = False
        reason = None
        if delta < MARGINAL_DELTA and idx > 0:
            stopped = True
            reason = f"marginal_delta {delta:.3f} < {MARGINAL_DELTA}"
        steps.append(RefinementStep(
            level=idx, name=name, description=desc,
            improvement_delta=delta, stopped_here=stopped, reason=reason))
        final_level = idx
        if stopped:
            break
    return RefinementResult(
        steps=steps, final_level_reached=final_level,
        final_solution=current,
    )
