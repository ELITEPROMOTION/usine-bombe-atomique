"""Confidence Scorer - scoring multi-dimensionnel 6 dimensions (CDC Ch.9 V2).

Dimensions pondereees (somme = 1.0) :

  1. Correctness        0.25  -> tests pytest passent (agent #04)
  2. Quality            0.15  -> lint + sonar moyen (agents #14 + #02)
  3. Coverage           0.10  -> ratio fichiers testes / fichiers code
  4. Security           0.20  -> agent #11 (fallback #02 bandit)
  5. Conformity         0.20  -> niveau 2 pipeline + agent #18 DZ
  6. Maintainability    0.10  -> complexite radon + docstrings presents

La sortie est un `ConfidenceReport` avec :
- breakdown par dimension (score, poids, details)
- composite (somme ponderee)
- verdict label : very_low (<0.30) / low / medium / high / very_high (>=0.90)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

WEIGHTS: dict[str, float] = {
    "correctness": 0.25,
    "quality": 0.15,
    "coverage": 0.10,
    "security": 0.20,
    "conformity": 0.20,
    "maintainability": 0.10,
}


@dataclass
class DimensionScore:
    name: str
    weight: float
    score: float
    details: str = ""


@dataclass
class ConfidenceReport:
    dimensions: list[DimensionScore] = field(default_factory=list)
    composite: float = 0.0
    label: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite": round(self.composite, 4),
            "label": self.label,
            "dimensions": [
                {"name": d.name, "weight": d.weight,
                 "score": round(d.score, 3), "details": d.details}
                for d in self.dimensions
            ],
        }


def score_confidence(
    manifest: list[dict[str, Any]],
    agent_results: dict[str, Any],
    validation_levels: list[dict[str, Any]] | list[Any],
) -> ConfidenceReport:
    """Calcule les 6 dimensions a partir des sorties agents + pipeline + manifest."""
    dims = [
        _correctness(agent_results),
        _quality(agent_results),
        _coverage(manifest),
        _security(agent_results),
        _conformity(agent_results, validation_levels),
        _maintainability(agent_results, manifest),
    ]
    composite = sum(d.score * d.weight for d in dims)
    return ConfidenceReport(
        dimensions=dims,
        composite=round(composite, 4),
        label=_label(composite),
    )


_LABELS: tuple[tuple[float, str], ...] = (
    (0.90, "very_high"),
    (0.75, "high"),
    (0.55, "medium"),
    (0.30, "low"),
)


def _label(score: float) -> str:
    for threshold, label in _LABELS:
        if score >= threshold:
            return label
    return "very_low"


def _score_of(agent_results: dict[str, Any], agent_id: str) -> float | None:
    res = agent_results.get(agent_id)
    if not res:
        return None
    output = getattr(res, "output", None) or (res.get("output") if isinstance(res, dict) else None)
    if not output:
        return None
    val = output.get("score")
    return float(val) if isinstance(val, int | float) else None


def _correctness(agent_results: dict[str, Any]) -> DimensionScore:
    pytest_score = _score_of(agent_results, "agent-04-pytest")
    if pytest_score is None:
        return DimensionScore("correctness", WEIGHTS["correctness"], 0.0,
                              "Pytest non execute")
    return DimensionScore("correctness", WEIGHTS["correctness"],
                          pytest_score, f"pytest score={pytest_score:.2f}")


def _quality(agent_results: dict[str, Any]) -> DimensionScore:
    lint = _score_of(agent_results, "agent-14-linter")
    sonar = _score_of(agent_results, "agent-02-sonarqube")
    available = [s for s in (lint, sonar) if s is not None]
    if not available:
        return DimensionScore("quality", WEIGHTS["quality"], 0.0, "Aucun agent qualite")
    score = sum(available) / len(available)
    return DimensionScore("quality", WEIGHTS["quality"],
                          score, f"lint={lint} sonar={sonar}")


def _coverage(manifest: list[dict[str, Any]]) -> DimensionScore:
    tests = [m for m in manifest if str(m.get("type", "")) == "test"
             or str(m.get("path", "")).startswith("tests/")]
    code = [m for m in manifest if str(m.get("type", "")) == "source_code"
            and str(m.get("path", "")).startswith("app/")]
    if not code:
        return DimensionScore("coverage", WEIGHTS["coverage"], 0.0, "Pas de code app/")
    # Heuristique : ratio tests/code plafonne a 1.0 (1 test pour 1 fichier)
    ratio = min(1.0, len(tests) / max(1, len(code)))
    return DimensionScore("coverage", WEIGHTS["coverage"], ratio,
                          f"{len(tests)} tests / {len(code)} sources")


def _security(agent_results: dict[str, Any]) -> DimensionScore:
    sec = _score_of(agent_results, "agent-11-security")
    sonar = _score_of(agent_results, "agent-02-sonarqube")
    if sec is not None:
        return DimensionScore("security", WEIGHTS["security"], sec,
                              f"security-agent score={sec:.2f}")
    if sonar is not None:
        return DimensionScore("security", WEIGHTS["security"], sonar,
                              f"fallback bandit score={sonar:.2f}")
    return DimensionScore("security", WEIGHTS["security"], 0.0,
                          "Aucune sonde securite")


def _conformity(
    agent_results: dict[str, Any],
    levels: list[dict[str, Any]] | list[Any],
) -> DimensionScore:
    dz = _score_of(agent_results, "agent-18-conformite-dz")
    # Pipeline level 2 (CDC conformity)
    cdc_score = 0.0
    for lv in levels:
        lvnum = getattr(lv, "level", None) if not isinstance(lv, dict) else lv.get("level")
        if lvnum == 2:
            raw = getattr(lv, "score", None) if not isinstance(lv, dict) else lv.get("score")
            cdc_score = float(raw or 0.0)
            break
    components = [cdc_score]
    if dz is not None:
        components.append(dz)
    score = sum(components) / len(components)
    return DimensionScore("conformity", WEIGHTS["conformity"], score,
                          f"cdc={cdc_score:.2f} dz={dz if dz is not None else 'n/a'}")


def _maintainability(
    agent_results: dict[str, Any],
    manifest: list[dict[str, Any]],
) -> DimensionScore:
    sonar_res = agent_results.get("agent-02-sonarqube")
    cc_avg = 0.0
    if sonar_res:
        output = getattr(sonar_res, "output", None) \
            or (sonar_res.get("output") if isinstance(sonar_res, dict) else None)
        if output:
            cc_avg = float(output.get("complexity", {}).get("average_complexity", 0.0))
    # Complexite cible ~2-5 ; on penalise au-dela
    if cc_avg == 0:
        complexity_score = 0.8  # pas de donnee -> hypothese neutre
    elif cc_avg <= 5:
        complexity_score = 1.0
    elif cc_avg <= 10:
        complexity_score = 0.8
    elif cc_avg <= 15:
        complexity_score = 0.5
    else:
        complexity_score = 0.2

    # Presence README non vide
    has_readme = any(str(m.get("path", "")).lower().endswith("readme.md")
                     and int(m.get("size_bytes", 0)) >= 200 for m in manifest)
    docs_score = 1.0 if has_readme else 0.4

    score = 0.6 * complexity_score + 0.4 * docs_score
    return DimensionScore("maintainability", WEIGHTS["maintainability"], score,
                          f"cc_avg={cc_avg:.1f} readme={'ok' if has_readme else 'faible'}")
