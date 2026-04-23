"""Upgrade 22 - Test Manifest Loader & Enforcer.

Un fichier JSON par type de projet (api/frontend/workflow/docker) liste
les suites de tests obligatoires. Si une suite requise est absente,
la livraison est rejetee.
"""
from __future__ import annotations

import fnmatch
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path(__file__).resolve().parent.parent / "test_manifests"


@dataclass
class EnforcementResult:
    project_type: str
    missing_suites: list[str]
    missing_markers: list[str]
    satisfied: list[str]
    ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_type": self.project_type,
            "ok": self.ok,
            "missing_suites": self.missing_suites,
            "missing_markers": self.missing_markers,
            "satisfied": self.satisfied,
        }


def load_manifest(project_type: str) -> dict[str, Any] | None:
    f = MANIFESTS_DIR / f"{project_type}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def detect_project_type(files: dict[str, str]) -> str:
    """Heuristique : api > workflow > docker > frontend."""
    names = set(files.keys())
    has_fastapi = any("from fastapi import" in c for c in files.values())
    has_pytest = any(p.startswith("tests/") and p.endswith(".py") for p in names)
    has_ts = any(p.endswith((".ts", ".tsx")) for p in names)
    if has_ts and not has_pytest:
        return "frontend"
    if any("business" in p.lower() for p in names) and has_pytest:
        return "workflow"
    if has_fastapi and has_pytest:
        return "api"
    if any(p == "Dockerfile" for p in names):
        return "docker"
    return "api"


def _suite_present(pattern: str, min_cases: int, files: dict[str, str]) -> tuple[bool, int]:
    cases = 0
    for path, content in files.items():
        if fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path, "**/" + pattern):
            # Compte rapide de `def test_` dans le fichier
            cases += content.count("def test_")
    return cases >= min_cases, cases


def enforce(project_type: str, files: dict[str, str]) -> EnforcementResult:
    manifest = load_manifest(project_type)
    if not manifest:
        return EnforcementResult(project_type=project_type,
                                 missing_suites=[f"no manifest for {project_type}"],
                                 missing_markers=[], satisfied=[], ok=False)

    missing_suites: list[str] = []
    satisfied: list[str] = []
    for suite in manifest["required_suites"]:
        ok, cases = _suite_present(suite["pattern"], suite["min_cases"], files)
        if ok:
            satisfied.append(f"{suite['id']}({cases} cases)")
        else:
            missing_suites.append(
                f"{suite['id']} (need {suite['min_cases']}, found {cases})"
            )

    missing_markers = [m for m in manifest.get("mandatory_markers", [])
                       if not any(p == m or p.endswith("/" + m) for p in files)]

    return EnforcementResult(
        project_type=project_type,
        missing_suites=missing_suites,
        missing_markers=missing_markers,
        satisfied=satisfied,
        ok=not missing_suites and not missing_markers,
    )


def list_project_types() -> list[str]:
    return sorted(p.stem for p in MANIFESTS_DIR.glob("*.json"))
