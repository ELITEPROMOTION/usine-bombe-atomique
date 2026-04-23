"""Challenger V4.1 - contre-hypothese anti-tunnel vision sur decisions critiques.

Quand le Judge s'appret a statuer, le Challenger propose l'hypothese
opposee et compare. Deterministe, declenche uniquement sur decisions
critiques (PASS/FAIL haute confiance, budget > seuil, securite). Si la
contre-hypothese est plausible (score >= 0.70 du principal), le Judge
voit les deux options et choisit explicitement avec rationale enregistre.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    stance: str   # "primary" | "counter"
    claim: str
    score: float  # 0..1, confiance estimee
    evidence: list[str]


@dataclass
class ChallengerReport:
    primary: Hypothesis
    counter: Hypothesis
    verdict: str  # "primary_wins" | "review_needed" | "counter_preferred"
    rationale: str

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "rationale": self.rationale,
            "primary": {"claim": self.primary.claim,
                        "score": round(self.primary.score, 3),
                        "evidence": self.primary.evidence},
            "counter": {"claim": self.counter.claim,
                        "score": round(self.counter.score, 3),
                        "evidence": self.counter.evidence},
        }


def _counter_claim(claim: str) -> str:
    negations = {
        "PASS": "HARD_FAIL", "HARD_FAIL": "PASS",
        "approve": "reject", "reject": "approve",
        "safe": "unsafe", "unsafe": "safe",
        "ready": "not ready", "not ready": "ready",
    }
    for k, v in negations.items():
        if k in claim:
            return claim.replace(k, v)
    return f"NON ({claim})"


def challenge(
    primary_claim: str,
    primary_score: float,
    primary_evidence: list[str],
    counter_evidence: list[str] | None = None,
) -> ChallengerReport:
    """Construit la contre-hypothese et decide du verdict."""
    counter_evidence = counter_evidence or []
    # Score de la contre-hypothese = 1 - confiance principale, boosted par les
    # evidences opposees presentes.
    counter_score = max(0.0, min(1.0,
        (1.0 - primary_score) + 0.10 * len(counter_evidence)
    ))

    primary = Hypothesis("primary", primary_claim, primary_score, primary_evidence)
    counter = Hypothesis("counter", _counter_claim(primary_claim),
                         counter_score, counter_evidence)

    if counter.score >= primary.score:
        verdict = "counter_preferred"
        rationale = (f"Contre-hypothese plus solide ({counter.score:.2f} vs "
                     f"{primary.score:.2f}). Judge doit revoir.")
    elif counter.score >= 0.70 * primary.score:
        verdict = "review_needed"
        rationale = (f"Contre-hypothese plausible ({counter.score:.2f} "
                     f">= 70% de {primary.score:.2f}). Judge confirme explicitement.")
    else:
        verdict = "primary_wins"
        rationale = (f"Principale domine ({primary.score:.2f} vs "
                     f"{counter.score:.2f}). Pas de doute raisonnable.")
    return ChallengerReport(primary=primary, counter=counter,
                            verdict=verdict, rationale=rationale)
