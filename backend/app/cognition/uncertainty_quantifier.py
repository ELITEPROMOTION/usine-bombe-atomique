"""V5.4 - Uncertainty Quantifier.

Quantifie 4 sources d'incertitude + intervalles credibles 5%-95%.
INTERDICTION : plus de "probablement" / "il semble que".
"""
from __future__ import annotations

import math
import re

from app.cognition.reasoning_trace_models import UncertaintyReport

VAGUE_TERMS = [
    re.compile(r"\bprobablement\b", re.I),
    re.compile(r"\bil semble que\b", re.I),
    re.compile(r"\bpeut-etre\b", re.I),
    re.compile(r"\bpossibly\b", re.I),
    re.compile(r"\blikely\b", re.I),
    re.compile(r"\bperhaps\b", re.I),
    re.compile(r"\bmight be\b", re.I),
]


def detect_vague_rhetoric(text: str) -> list[str]:
    """Retourne les termes vagues trouves."""
    hits: list[str] = []
    for pat in VAGUE_TERMS:
        m = pat.search(text or "")
        if m:
            hits.append(m.group(0))
    return hits


def has_vague_rhetoric(text: str) -> bool:
    return bool(detect_vague_rhetoric(text))


def aleatory_from_variance(samples: list[float]) -> float:
    """Incertitude aleatoire a partir de la variance d'echantillons."""
    if len(samples) < 2:
        return 0.0
    mean = sum(samples) / len(samples)
    var = sum((x - mean) ** 2 for x in samples) / len(samples)
    # Normalize : sigma ~ max 0.5 considered as max aleatory
    sigma = math.sqrt(var)
    return min(1.0, sigma * 2)


def epistemic_from_sources(sources_count: int, min_required: int = 3) -> float:
    """Manque de sources -> epistemic high. 0 source = 1.0, 3+ = 0.0."""
    return max(0.0, min(1.0, 1.0 - sources_count / min_required))


def ontological_from_domain_fit(fit_score: float) -> float:
    """Si modele inadapte au domaine -> ontological high."""
    return max(0.0, min(1.0, 1.0 - fit_score))


def computational_from_budget(used: int, budget: int) -> float:
    if budget <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - used / budget))


def credible_interval(
    mean: float, total_uncertainty: float,
) -> tuple[float, float]:
    """Retourne [low, high] = [mean - 1.96*sigma, mean + 1.96*sigma] clampe."""
    sigma = total_uncertainty * 0.25  # approx
    lo = max(0.0, mean - 1.96 * sigma)
    hi = min(1.0, mean + 1.96 * sigma)
    return lo, hi


def build_report(
    *, samples: list[float] | None = None,
    sources_count: int = 0,
    domain_fit: float = 1.0,
    budget_used: int = 0,
    budget_total: int = 1,
    mean_confidence: float = 0.5,
) -> UncertaintyReport:
    a = aleatory_from_variance(samples or [])
    e = epistemic_from_sources(sources_count)
    o = ontological_from_domain_fit(domain_fit)
    c = computational_from_budget(budget_used, budget_total)
    total = (a + e + o + c) / 4
    lo, hi = credible_interval(mean_confidence, total)
    return UncertaintyReport(
        aleatory=a, epistemic=e, ontological=o, computational=c,
        credible_low=lo, credible_high=hi,
    )


def propagate(
    *, parent: UncertaintyReport, increment: UncertaintyReport,
) -> UncertaintyReport:
    """Propage l'incertitude : enveloppe maximale."""
    return UncertaintyReport(
        aleatory=max(parent.aleatory, increment.aleatory),
        epistemic=max(parent.epistemic, increment.epistemic),
        ontological=max(parent.ontological, increment.ontological),
        computational=max(parent.computational, increment.computational),
        credible_low=min(parent.credible_low, increment.credible_low),
        credible_high=max(parent.credible_high, increment.credible_high),
    )
