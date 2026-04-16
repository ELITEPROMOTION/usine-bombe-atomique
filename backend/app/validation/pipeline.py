"""Pipeline de validation 9 niveaux (Ch.7 du CDC).

Squelette V0 : chaque niveau renvoie un score et passed=True par defaut.
Les verificateurs reels sont implementes progressivement (agents
Ruff, SonarQube, OWASP, pytest, Playwright, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class Level(IntEnum):
    LOGICAL_COHERENCE = 1
    CDC_CONFORMITY = 2
    OWASP_SECURITY = 3
    PERFORMANCE = 4
    DZ_COMPLIANCE = 5
    QUALITY_GATE = 6
    E2E_TESTS = 7
    USER_ACCEPTANCE = 8
    PRODUCTION_READY = 9


LEVEL_NAMES: dict[int, str] = {
    1: "Coherence Logique",
    2: "Conformite CDC",
    3: "Securite OWASP",
    4: "Performance",
    5: "Conformite DZ",
    6: "Quality Gate SonarQube",
    7: "Tests E2E Playwright",
    8: "Acceptation Utilisateur",
    9: "Production Ready",
}

LEVEL_WEIGHTS: dict[int, float] = {
    1: 0.15, 2: 0.15, 3: 0.15, 4: 0.10, 5: 0.10,
    6: 0.10, 7: 0.10, 8: 0.10, 9: 0.05,
}


@dataclass
class LevelResult:
    level: int
    name: str
    score: float
    passed: bool
    details: str = ""
    issues: list[dict[str, Any]] | None = None


@dataclass
class PipelineResult:
    levels: list[LevelResult]
    global_score: float
    verdict: str  # PASS | CONDITIONAL_PASS | SOFT_FAIL | HARD_FAIL


def _verdict(levels: list[LevelResult], score: float) -> str:
    if any(not lr.passed for lr in levels if lr.level in (1, 2, 3)):
        return "HARD_FAIL"
    if any(not lr.passed for lr in levels):
        return "SOFT_FAIL" if score >= 0.70 else "HARD_FAIL"
    if score >= 0.85:
        return "PASS"
    return "CONDITIONAL_PASS"


async def run_pipeline(artifacts: dict[str, Any]) -> PipelineResult:
    """V0: tous les niveaux PASS avec score constant 1.0.

    Remplace progressivement chaque niveau par un verificateur reel.
    """
    levels: list[LevelResult] = []
    for lvl, name in LEVEL_NAMES.items():
        levels.append(LevelResult(level=lvl, name=name, score=1.0, passed=True, issues=[]))

    global_score = sum(lr.score * LEVEL_WEIGHTS[lr.level] for lr in levels)
    return PipelineResult(
        levels=levels,
        global_score=global_score,
        verdict=_verdict(levels, global_score),
    )
