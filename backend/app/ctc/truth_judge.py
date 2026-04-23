"""V5.3 BLOC 7 - Truth Judge (extension).

Judge objectif base sur des metriques uniquement (pas d'intuition LLM).
Respecte separation Builder / Critic / Judge.

Verdict : PASS | CONDITIONAL_PASS | SOFT_FAIL | HARD_FAIL
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TruthJudgeInput:
    # Seuils minimums
    triangulation_score: float              # 0..100
    critical_contradictions_open: int
    stale_primary_sources: int
    chain_integrity_ok: bool
    all_dims_above_threshold: bool
    critical_assertions_proven: bool
    # Dims scoring
    dimensions: dict[str, float]            # {"security": 0.9, ...}
    required_dims: list[str]
    threshold_by_dim: dict[str, float]


@dataclass
class TruthJudgeVerdict:
    verdict: str
    reasons: list[str]
    blockers: list[str]
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict, "score": round(self.score, 4),
            "reasons": self.reasons, "blockers": self.blockers,
        }


def decide(inp: TruthJudgeInput) -> TruthJudgeVerdict:
    reasons: list[str] = []
    blockers: list[str] = []

    # Blockers critiques -> HARD_FAIL
    if not inp.chain_integrity_ok:
        blockers.append("evidence_chain_broken")
    if inp.critical_contradictions_open > 0:
        blockers.append(f"critical_contradictions={inp.critical_contradictions_open}")
    if inp.stale_primary_sources > 0:
        blockers.append(f"stale_primary_sources={inp.stale_primary_sources}")
    if not inp.critical_assertions_proven:
        blockers.append("critical_assertions_not_proven")

    if blockers:
        return TruthJudgeVerdict(
            verdict="HARD_FAIL", reasons=[], blockers=blockers,
            score=0.0,
        )

    # Dimensions sous seuil
    failed_dims: list[str] = []
    for d in inp.required_dims:
        val = inp.dimensions.get(d, 0.0)
        th = inp.threshold_by_dim.get(d, 0.70)
        if val < th:
            failed_dims.append(f"{d}<{th}")
    if not inp.all_dims_above_threshold or failed_dims:
        reasons.extend(failed_dims)
        return TruthJudgeVerdict(
            verdict="SOFT_FAIL", reasons=reasons, blockers=[],
            score=sum(inp.dimensions.values()) / max(1, len(inp.dimensions)),
        )

    # Triangulation score
    if inp.triangulation_score >= 85:
        reasons.append(f"triangulation_score={inp.triangulation_score:.1f}>=85")
        return TruthJudgeVerdict(
            verdict="PASS", reasons=reasons, blockers=[],
            score=inp.triangulation_score / 100,
        )
    if inp.triangulation_score >= 70:
        reasons.append(f"triangulation_score={inp.triangulation_score:.1f}")
        return TruthJudgeVerdict(
            verdict="CONDITIONAL_PASS", reasons=reasons, blockers=[],
            score=inp.triangulation_score / 100,
        )
    reasons.append(f"triangulation_score={inp.triangulation_score:.1f}<70")
    return TruthJudgeVerdict(
        verdict="SOFT_FAIL", reasons=reasons, blockers=[],
        score=inp.triangulation_score / 100,
    )


# Default dims / thresholds
DEFAULT_DIMS = ["functional", "security", "performance",
                 "maintainability", "conformity", "prod_readiness"]
DEFAULT_THRESHOLDS = {
    "functional": 0.85, "security": 0.90,
    "performance": 0.75, "maintainability": 0.70,
    "conformity": 0.95, "prod_readiness": 0.80,
}


def decide_simple(
    triangulation_score: float,
    dimensions: dict[str, float],
    chain_integrity_ok: bool = True,
    contradictions: int = 0,
    stale_sources: int = 0,
    critical_assertions_proven: bool = True,
) -> TruthJudgeVerdict:
    all_ok = all(
        dimensions.get(d, 0) >= DEFAULT_THRESHOLDS.get(d, 0.7)
        for d in DEFAULT_DIMS
    )
    return decide(TruthJudgeInput(
        triangulation_score=triangulation_score,
        critical_contradictions_open=contradictions,
        stale_primary_sources=stale_sources,
        chain_integrity_ok=chain_integrity_ok,
        all_dims_above_threshold=all_ok,
        critical_assertions_proven=critical_assertions_proven,
        dimensions=dimensions,
        required_dims=DEFAULT_DIMS,
        threshold_by_dim=DEFAULT_THRESHOLDS,
    ))
