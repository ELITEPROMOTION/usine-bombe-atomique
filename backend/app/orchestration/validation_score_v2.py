"""V8.5 — Validation score v2 (echelle 0..100 avec breakdown reel).

Refonte du calcul `validation_score` pour qu'il reflete la VRAIE qualite
livrable, pas un score cosmetique 5-niveaux pondere.

Bareme strict (total = 100 pts) :

    30 pts - Pytest PASS              (binaire)
    20 pts - Docker build + health    (binaire)
    15 pts - Coverage                 (proportionnel par paliers)
    15 pts - Lint clean               (proportionnel par paliers)
    10 pts - README complete          (proportionnel)
    10 pts - Smoke test post-deploy   (binaire)

Decisions :
    >= 80    -> ACCEPTED         livrable accepte
    60..79   -> PARTIAL          livrable warning, pas refund
    < 60     -> REJECTED         re-generation auto (max 3 tentatives)

Le breakdown est persiste dans la table `tasks.validation_breakdown_json`
(migration 036) pour audit + dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.orchestration.quality_gates import (
    GATE_COVERAGE,
    GATE_DOCKER_BUILD,
    GATE_DOCKER_RUN,
    GATE_LINT,
    GATE_PYTEST,
    GATE_README,
    GatesResult,
)

ACCEPTED_MIN = 80
PARTIAL_MIN = 60

MAX_PYTEST = 30
MAX_DOCKER = 20
MAX_COVERAGE = 15
MAX_LINT = 15
MAX_README = 10
MAX_SMOKE = 10
MAX_TOTAL = MAX_PYTEST + MAX_DOCKER + MAX_COVERAGE + MAX_LINT + MAX_README + MAX_SMOKE


@dataclass
class ScoreBreakdown:
    pytest_pass: int = 0
    docker_build: int = 0
    coverage: int = 0
    lint_clean: int = 0
    readme: int = 0
    smoke_test: int = 0
    total: int = 0
    decision: str = "REJECTED"
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scale": MAX_TOTAL,
            "decision": self.decision,
            "total": self.total,
            "components": {
                "pytest_pass":  {"score": self.pytest_pass,  "max": MAX_PYTEST},
                "docker_build": {"score": self.docker_build, "max": MAX_DOCKER},
                "coverage":     {"score": self.coverage,     "max": MAX_COVERAGE},
                "lint_clean":   {"score": self.lint_clean,   "max": MAX_LINT},
                "readme":       {"score": self.readme,       "max": MAX_README},
                "smoke_test":   {"score": self.smoke_test,   "max": MAX_SMOKE},
            },
            "rationale": self.rationale,
            "thresholds": {"accepted": ACCEPTED_MIN, "partial": PARTIAL_MIN},
        }


def compute_breakdown(gates_result: GatesResult) -> ScoreBreakdown:
    """Calcule un ScoreBreakdown a partir des 6 GateResult.

    Les gates SKIP (ex: docker indisponible) n'enlevent pas de points :
    le composant est neutralise au prorata de son max — on ne penalise pas
    l'absence d'environnement Docker dans un dev box. Si TOUS les gates
    Docker sont SKIP, max_total est ajuste pour que la decision reste juste.
    """
    by_name = {g.name: g for g in gates_result.gates}
    breakdown = ScoreBreakdown()
    rationale: list[str] = []

    # Pytest (30 pts binaire)
    g = by_name.get(GATE_PYTEST)
    if g and g.status == "PASS":
        breakdown.pytest_pass = MAX_PYTEST
        rationale.append("pytest: ALL PASS")
    else:
        reason = (g.details.get("reason", "fail") if g else "missing")
        rationale.append(f"pytest: {reason}")

    # Coverage (15 pts par paliers)
    g = by_name.get(GATE_COVERAGE)
    if g and g.status in ("PASS", "FAIL"):
        pct = float(g.details.get("percent_covered", 0.0))
        if pct >= 0.90:
            breakdown.coverage = MAX_COVERAGE
            rationale.append(f"coverage: {pct:.1%} >= 90%")
        elif pct >= 0.80:
            breakdown.coverage = 12
            rationale.append(f"coverage: {pct:.1%} >= 80%")
        elif pct >= 0.70:
            breakdown.coverage = 9
            rationale.append(f"coverage: {pct:.1%} >= 70%")
        else:
            breakdown.coverage = 0
            rationale.append(f"coverage: {pct:.1%} < 70% (FAIL)")
    elif g and g.status == "SKIP":
        breakdown.coverage = 0
        rationale.append("coverage: SKIP (pytest-cov absent)")
    else:
        rationale.append("coverage: not measured")

    # Lint (15 pts par paliers selon nombre d'erreurs)
    g = by_name.get(GATE_LINT)
    if g and g.status == "SKIP":
        rationale.append("lint: SKIP (ruff binary absent)")
    elif g and g.status == "PASS":
        errors = int(g.details.get("errors", 0))
        breakdown.lint_clean = MAX_LINT if errors == 0 else 10
        rationale.append(f"lint: {errors} errors (PASS)")
    elif g and g.status == "FAIL":
        errors = int(g.details.get("errors", 0))
        if 1 <= errors <= 5:
            breakdown.lint_clean = 10
            rationale.append(f"lint: {errors} warnings (<=5)")
        elif 6 <= errors <= 20:
            breakdown.lint_clean = 5
            rationale.append(f"lint: {errors} warnings (<=20)")
        else:
            breakdown.lint_clean = 0
            rationale.append(f"lint: FAIL ({errors} errors)")
    elif g and g.status == "ERROR":
        rationale.append(f"lint: ERROR ({g.details.get('reason', 'unknown')})")

    # Docker build (20 pts binaire avec passage SKIP)
    gb = by_name.get(GATE_DOCKER_BUILD)
    gr = by_name.get(GATE_DOCKER_RUN)
    if gb and gb.status == "PASS" and gr and gr.status == "PASS":
        breakdown.docker_build = MAX_DOCKER
        rationale.append("docker: build + health 200 OK")
    elif gb and gb.status == "SKIP" and gr and gr.status == "SKIP":
        # Pas de docker dans l'env -> neutraliser au prorata
        breakdown.docker_build = 0
        rationale.append("docker: SKIP (no docker binary; not penalized in summary)")
    else:
        breakdown.docker_build = 0
        if gb and gb.status == "FAIL":
            rationale.append("docker: build FAIL")
        elif gr and gr.status == "FAIL":
            rationale.append("docker: build OK, run/health FAIL")

    # Smoke test : prend le run docker comme proxy si dispo, sinon health route via tests
    if gr and gr.status == "PASS":
        breakdown.smoke_test = MAX_SMOKE
        rationale.append("smoke: docker /health 200")
    elif gr and gr.status == "SKIP":
        breakdown.smoke_test = 0
        rationale.append("smoke: SKIP (docker absent)")
    else:
        rationale.append("smoke: KO")

    # README (10 pts proportionnel)
    g = by_name.get(GATE_README)
    if g:
        present_count = len(g.details.get("present", []))
        total_required = present_count + len(g.details.get("missing", []))
        if total_required == 0:
            breakdown.readme = 0
        else:
            ratio = present_count / total_required
            if ratio == 1.0:
                breakdown.readme = MAX_README
                rationale.append("readme: all sections")
            elif ratio >= 0.66:
                breakdown.readme = 5
                rationale.append(f"readme: {present_count}/{total_required} sections")
            else:
                breakdown.readme = 0
                rationale.append(f"readme: {present_count}/{total_required} sections (FAIL)")

    breakdown.total = (
        breakdown.pytest_pass
        + breakdown.docker_build
        + breakdown.coverage
        + breakdown.lint_clean
        + breakdown.readme
        + breakdown.smoke_test
    )

    docker_skipped = (
        gb and gb.status == "SKIP" and gr and gr.status == "SKIP"
    )
    accepted_min = ACCEPTED_MIN - (MAX_DOCKER + MAX_SMOKE) if docker_skipped else ACCEPTED_MIN
    partial_min = PARTIAL_MIN - (MAX_DOCKER + MAX_SMOKE) if docker_skipped else PARTIAL_MIN

    if breakdown.total >= accepted_min:
        breakdown.decision = "ACCEPTED"
    elif breakdown.total >= partial_min:
        breakdown.decision = "PARTIAL"
    else:
        breakdown.decision = "REJECTED"

    breakdown.rationale = rationale
    return breakdown


def decision_for(score: int, *, docker_skipped: bool = False) -> str:
    """Decision strict pour un total deja calcule (utilitaire)."""
    accepted = ACCEPTED_MIN - (MAX_DOCKER + MAX_SMOKE) if docker_skipped else ACCEPTED_MIN
    partial = PARTIAL_MIN - (MAX_DOCKER + MAX_SMOKE) if docker_skipped else PARTIAL_MIN
    if score >= accepted:
        return "ACCEPTED"
    if score >= partial:
        return "PARTIAL"
    return "REJECTED"
