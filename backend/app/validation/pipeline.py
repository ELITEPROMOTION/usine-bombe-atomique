"""Pipeline de validation 5 niveaux (CDC Ch.7 - condense V1).

Les 9 niveaux du CDC sont projetes sur 5 niveaux operationnels en V1 :

    1. Coherence logique     -> chaque fichier .py parse (ast)
    2. Conformite CDC        -> fichiers indispensables presents
                                (main, tests, requirements, README)
    3. Qualite (Lint+Sonar)  -> moyenne des scores agents #14 et #02
    4. Tests (Pytest)        -> score de l'agent #04
    5. Production ready      -> README non vide + taille min du projet

Verdict :
- HARD_FAIL : un niveau parmi {1,2} echoue
- SOFT_FAIL : niveau 3, 4 ou 5 echoue et score global < 0.70
- CONDITIONAL_PASS : tous passent mais score < 0.85
- PASS : tous passent et score >= 0.85
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any


class Level(IntEnum):
    LOGICAL_COHERENCE = 1
    CDC_CONFORMITY = 2
    QUALITY = 3
    TESTS = 4
    PRODUCTION_READY = 5


LEVEL_NAMES: dict[int, str] = {
    1: "Coherence Logique",
    2: "Conformite CDC",
    3: "Qualite (Lint + Sonar)",
    4: "Tests (Pytest)",
    5: "Production Ready",
}

LEVEL_WEIGHTS: dict[int, float] = {
    1: 0.20,
    2: 0.20,
    3: 0.20,
    4: 0.30,
    5: 0.10,
}

REQUIRED_PATTERNS = (
    ("main", lambda p: p.endswith("main.py")),
    ("tests", lambda p: p.startswith("tests/") or "/tests/" in p),
    ("requirements", lambda p: Path(p).name == "requirements.txt"),
    ("readme", lambda p: Path(p).name.lower() == "readme.md"),
)


@dataclass
class LevelResult:
    level: int
    name: str
    score: float
    passed: bool
    details: str = ""
    issues: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PipelineResult:
    levels: list[LevelResult]
    global_score: float
    verdict: str


def _verdict(
    levels: list[LevelResult],
    score: float,
    pass_min: float = 0.85,
    cpass_min: float = 0.70,
) -> str:
    by_level = {lr.level: lr for lr in levels}
    if not by_level[1].passed or not by_level[2].passed:
        return "HARD_FAIL"
    if not all(lr.passed for lr in levels):
        return "SOFT_FAIL" if score >= cpass_min else "HARD_FAIL"
    return "PASS" if score >= pass_min else "CONDITIONAL_PASS"


async def run_pipeline(artifacts: dict[str, Any]) -> PipelineResult:
    """V4 : 5 niveaux + seuils auto-tunes optionnels.

    `artifacts` attend (toutes optionnelles) :
      - workspace : app.agents.workspace.Workspace
      - agents    : dict[agent_id, AgentResult]
      - manifest  : liste de fichiers generee par l'agent #01
      - thresholds : {pass_min, cpass_min} depuis auto_tuner (V4)
    """
    workspace = artifacts.get("workspace")
    agents = artifacts.get("agents") or {}
    manifest = artifacts.get("manifest") or (workspace.manifest() if workspace else [])
    thresholds = artifacts.get("thresholds") or {}
    pass_min = float(thresholds.get("pass_min", 0.85))
    cpass_min = float(thresholds.get("cpass_min", 0.70))

    levels = [
        _level_coherence(workspace, manifest),
        _level_cdc_conformity(manifest),
        _level_quality(agents),
        _level_tests(agents),
        _level_production_ready(workspace, manifest),
    ]
    global_score = sum(lr.score * LEVEL_WEIGHTS[lr.level] for lr in levels)
    return PipelineResult(
        levels=levels,
        global_score=round(global_score, 4),
        verdict=_verdict(levels, global_score, pass_min, cpass_min),
    )


def _level_coherence(workspace: Any, manifest: list[dict[str, Any]]) -> LevelResult:
    py_files = [m for m in manifest if m.get("language") == "python"]
    if not py_files:
        return LevelResult(level=1, name=LEVEL_NAMES[1], score=0.0, passed=False,
                           details="Aucun fichier Python genere")
    errors: list[dict[str, Any]] = []
    for meta in py_files:
        try:
            if workspace is not None:
                content = workspace.read(meta["path"])
            else:
                continue
            ast.parse(content)
        except SyntaxError as exc:
            errors.append({"path": meta["path"], "error": str(exc)})
        except FileNotFoundError:
            errors.append({"path": meta["path"], "error": "file missing"})
    total = len(py_files)
    score = 1.0 - (len(errors) / total) if total else 0.0
    return LevelResult(
        level=1, name=LEVEL_NAMES[1],
        score=round(score, 3),
        passed=len(errors) == 0,
        details=f"{total - len(errors)}/{total} fichiers Python valides",
        issues=errors,
    )


def _level_cdc_conformity(manifest: list[dict[str, Any]]) -> LevelResult:
    paths = [m["path"] for m in manifest]
    missing: list[str] = []
    present: list[str] = []
    for label, predicate in REQUIRED_PATTERNS:
        if any(predicate(p) for p in paths):
            present.append(label)
        else:
            missing.append(label)
    score = len(present) / len(REQUIRED_PATTERNS)
    return LevelResult(
        level=2, name=LEVEL_NAMES[2],
        score=round(score, 3),
        passed=len(missing) == 0,
        details=f"presents={present}, manquants={missing}",
        issues=[{"missing": m} for m in missing],
    )


def _level_quality(agents: dict[str, Any]) -> LevelResult:
    lint = _score_of(agents, "agent-14-linter")
    sonar = _score_of(agents, "agent-02-sonarqube")
    available = [s for s in (lint, sonar) if s is not None]
    if not available:
        return LevelResult(level=3, name=LEVEL_NAMES[3], score=0.0, passed=False,
                           details="Aucun agent qualite execute")
    score = sum(available) / len(available)
    return LevelResult(
        level=3, name=LEVEL_NAMES[3],
        score=round(score, 3),
        passed=score >= 0.75,
        details=f"lint={lint}, sonar={sonar}",
    )


def _level_tests(agents: dict[str, Any]) -> LevelResult:
    score = _score_of(agents, "agent-04-pytest")
    if score is None:
        return LevelResult(level=4, name=LEVEL_NAMES[4], score=0.0, passed=False,
                           details="Pytest non execute")
    passed = _flag_of(agents, "agent-04-pytest", "passed")
    return LevelResult(
        level=4, name=LEVEL_NAMES[4],
        score=round(score, 3),
        passed=bool(passed),
        details=f"pytest passed={passed}",
    )


def _level_production_ready(workspace: Any, manifest: list[dict[str, Any]]) -> LevelResult:
    has_readme = any(Path(m["path"]).name.lower() == "readme.md" for m in manifest)
    readme_bytes = 0
    if has_readme and workspace is not None:
        try:
            readme_bytes = len(workspace.read("README.md").strip().encode("utf-8"))
        except FileNotFoundError:
            has_readme = False
    enough_files = len(manifest) >= 4
    readme_ok = has_readme and readme_bytes >= 120
    score = 0.0
    if enough_files:
        score += 0.5
    if readme_ok:
        score += 0.5
    return LevelResult(
        level=5, name=LEVEL_NAMES[5],
        score=round(score, 3),
        passed=score >= 1.0,
        details=f"readme_ok={readme_ok} ({readme_bytes} o), files={len(manifest)}",
    )


def _score_of(agents: dict[str, Any], agent_id: str) -> float | None:
    res = agents.get(agent_id)
    if not res:
        return None
    output = getattr(res, "output", None) or (res.get("output") if isinstance(res, dict) else None)
    if not output:
        return None
    val = output.get("score")
    return float(val) if isinstance(val, int | float) else None


def _flag_of(agents: dict[str, Any], agent_id: str, key: str) -> bool | None:
    res = agents.get(agent_id)
    if not res:
        return None
    output = getattr(res, "output", None) or (res.get("output") if isinstance(res, dict) else None)
    if not output:
        return None
    return bool(output.get(key))
