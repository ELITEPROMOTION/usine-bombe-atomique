"""V5.4 - Reflexion Engine (Shinn 2023).

Max 3 cycles. Questions premortem obligatoires.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.cognition.reasoning_trace_models import ReflectionCycle, ReflectionTrace


PREMORTEM_QUESTIONS = [
    "Qu'est-ce qui peut etre faux ?",
    "Quelle hypothese n'a pas ete verifiee ?",
    "Quels cas limites ont ete ignores ?",
    "Une approche plus simple ou plus robuste existe-t-elle ?",
    "Si cette solution echoue, ou echouera-t-elle en premier ?",
]

MIN_IMPROVEMENT_DELTA = 0.02   # 2% amelioration minimum pour continuer
MAX_CYCLES = 3


@dataclass
class RawRefinement:
    v2: str
    improvements: list[str]
    premortem_findings: list[str]
    score: float


def _default_refiner(v1: str, findings: list[str]) -> RawRefinement:
    """Refiner deterministe : ajoute les findings en commentaire."""
    improvements = [f"addressed: {f[:80]}" for f in findings[:3]]
    v2 = f"{v1}\n# Improved by premortem: {len(findings)} findings"
    return RawRefinement(
        v2=v2, improvements=improvements,
        premortem_findings=findings,
        score=min(1.0, 0.75 + 0.05 * len(findings)),
    )


def default_premortem(solution: str) -> list[str]:
    """Premortem deterministe : pour chaque question, genere une finding."""
    return [
        f"[{q}] -> Analysis of: {solution[:80]}" for q in PREMORTEM_QUESTIONS
    ]


def run(
    initial_solution: str, *,
    max_cycles: int = MAX_CYCLES,
    min_delta: float = MIN_IMPROVEMENT_DELTA,
    premortem_fn: Callable[[str], list[str]] | None = None,
    refiner_fn: Callable[[str, list[str]], RawRefinement] | None = None,
) -> ReflectionTrace:
    if premortem_fn is None:
        premortem_fn = default_premortem
    if refiner_fn is None:
        refiner_fn = _default_refiner

    cycles: list[ReflectionCycle] = []
    current = initial_solution
    previous_score = 0.70   # baseline initiale

    for i in range(max_cycles):
        findings = premortem_fn(current)
        refined = refiner_fn(current, findings)
        delta = refined.score - previous_score
        converged = delta < min_delta
        cycles.append(ReflectionCycle(
            cycle=i + 1,
            v1_solution=current[:2000],
            v2_solution=refined.v2[:2000],
            premortem_findings=findings,
            improvements=refined.improvements,
            improvement_delta=delta,
            converged=converged,
        ))
        if converged:
            break
        current = refined.v2
        previous_score = refined.score

    return ReflectionTrace(
        cycles=cycles,
        final_solution=current,
        max_cycles=max_cycles,
    )
