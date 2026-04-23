"""Upgrade 32 - Impact Analyzer : calcule le rayon d'impact sur 6 dimensions
avant tout patch. Pilote automatiquement le niveau de test exige et le
type de correction autorise (voir patch_types).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DIMENSIONS = ("structure", "metier", "securite", "runtime", "conformite", "confiance")


@dataclass
class ImpactReport:
    scores: dict[str, float]
    composite: float
    recommended_revalidation: list[str]
    blast_radius: str  # small | medium | large | critical
    test_depth: str    # smoke | standard | full | regen

    def to_dict(self) -> dict[str, Any]:
        return {
            "scores": {k: round(v, 3) for k, v in self.scores.items()},
            "composite": round(self.composite, 3),
            "recommended_revalidation": self.recommended_revalidation,
            "blast_radius": self.blast_radius,
            "test_depth": self.test_depth,
        }


@dataclass
class _ChangeSignals:
    n: int
    has_schema: bool
    has_contract: bool
    has_security: bool
    has_runtime: bool
    has_conformite: bool


def _signals(files_changed: list[str], spec: str) -> _ChangeSignals:
    return _ChangeSignals(
        n=len(files_changed),
        has_schema=any("migrations/" in p or p.endswith(".sql") for p in files_changed),
        has_contract=any("agent_contracts/" in p or "schemas.py" in p
                           or "openapi.json" in p for p in files_changed),
        has_security=any(re.search(r"(auth|jwt|rate_limit|middleware|password)",
                                      p, re.IGNORECASE) for p in files_changed),
        has_runtime=any(p.endswith(("worker.py", "orchestrator.py"))
                         for p in files_changed),
        has_conformite=bool(re.search(r"(?i)tva|tap|cnas|irg|dz|conformite|compliance",
                                         spec)),
    )


def _scores(sig: _ChangeSignals, diff_loc: int) -> dict[str, float]:
    conformite = (0.8 if sig.has_conformite and (sig.has_contract or sig.has_schema)
                   else 0.3 if sig.has_conformite else 0.0)
    return {
        "structure":  min(1.0, sig.n / 8.0),
        "metier":     min(1.0, diff_loc / 200.0),
        "securite":   1.0 if sig.has_security else 0.0,
        "runtime":    1.0 if sig.has_runtime else 0.0,
        "conformite": conformite,
        "confiance":  min(1.0, sig.n / 6.0),
    }


def _layers(sig: _ChangeSignals, composite: float) -> list[str]:
    layers = {"structure"}
    if sig.has_contract:
        layers.add("contract")
    if sig.has_schema:
        layers.add("data")
    if sig.has_security:
        layers.add("security")
    if sig.has_runtime or composite >= 0.50:
        layers.add("behavior")
    return sorted(layers)


def _radius_depth(composite: float) -> tuple[str, str]:
    if composite < 0.20:
        return "small", "smoke"
    if composite < 0.45:
        return "medium", "standard"
    if composite < 0.75:
        return "large", "full"
    return "critical", "regen"


def analyze(
    files_changed: list[str],
    spec: str = "",
    diff_loc: int = 0,
) -> ImpactReport:
    """Scores 0..1 par dimension, composite pondere, plan de test adapte."""
    sig = _signals(files_changed, spec)
    scores = _scores(sig, diff_loc)
    composite = sum(scores.values()) / len(scores)
    layers = _layers(sig, composite)
    radius, depth = _radius_depth(composite)
    return ImpactReport(
        scores=scores, composite=composite,
        recommended_revalidation=layers,
        blast_radius=radius, test_depth=depth,
    )
