"""Pipeline Niveau 0 (V4.1) - validation structurelle AVANT LLM.

Objectif : bloquer sans aucun token LLM consomme toute entree malformee.
- Python : ast.parse sur chaque fichier .py
- JSON : json.loads sur chaque .json
- YAML : yaml.safe_load sur chaque .yaml/.yml (si PyYAML dispo, sinon skip)
- Imports Python : tous les imports app.* doivent se resoudre

Retourne un `LevelZeroResult` ; s'il echoue, la suite du pipeline est
court-circuitee avec verdict HARD_FAIL et aucun appel LLM n'a lieu.
"""
from __future__ import annotations

import ast
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LevelZeroResult:
    passed: bool
    score: float
    issues: list[dict[str, Any]] = field(default_factory=list)
    files_scanned: int = 0
    python_ok: int = 0
    json_ok: int = 0
    yaml_ok: int = 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.score, 3),
            "files_scanned": self.files_scanned,
            "python_ok": self.python_ok,
            "json_ok": self.json_ok,
            "yaml_ok": self.yaml_ok,
            "issues": self.issues[:20],
        }


def _check_python(path: str, content: str, imports_resolvable: Callable[[str], bool]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        issues.append({"path": path, "kind": "python_syntax",
                       "msg": f"SyntaxError line {exc.lineno}: {exc.msg}"})
        return issues
    # Imports app.*
    for node in ast.walk(tree):
        mod = None
        if isinstance(node, ast.Import):
            mod = node.names[0].name if node.names else None
        elif isinstance(node, ast.ImportFrom):
            mod = node.module
        if mod and mod.startswith("app.") and not imports_resolvable(mod):
            issues.append({"path": path, "kind": "import_unresolved",
                           "module": mod, "line": getattr(node, "lineno", 0)})
    return issues


def _check_json(path: str, content: str) -> list[dict[str, Any]]:
    if not content.strip():
        return []
    try:
        json.loads(content)
        return []
    except json.JSONDecodeError as exc:
        return [{"path": path, "kind": "json_syntax",
                 "msg": f"line {exc.lineno}: {exc.msg}"}]


def _check_yaml(path: str, content: str) -> tuple[list[dict[str, Any]], bool]:
    """Retourne (issues, parsed_ok). Skip si PyYAML absent."""
    try:
        import yaml  # type: ignore
    except ImportError:
        logger.info("pyyaml absent, yaml parsing skipped")
        return [], False
    try:
        yaml.safe_load(content)
        return [], True
    except Exception as exc:
        return [{"path": path, "kind": "yaml_syntax", "msg": str(exc)[:200]}], False


def validate(
    files: dict[str, str],
    known_module_resolver: Callable[[str], bool] = lambda m: True,
) -> LevelZeroResult:
    """Valide syntaxiquement tous les fichiers du dict {path: content}."""
    issues: list[dict[str, Any]] = []
    py_ok = json_ok = yaml_ok = 0
    scanned = 0

    for path, content in files.items():
        scanned += 1
        if path.endswith(".py"):
            file_issues = _check_python(path, content, known_module_resolver)
            if not file_issues:
                py_ok += 1
            issues.extend(file_issues)
        elif path.endswith(".json"):
            file_issues = _check_json(path, content)
            if not file_issues:
                json_ok += 1
            issues.extend(file_issues)
        elif path.endswith((".yaml", ".yml")):
            file_issues, parsed = _check_yaml(path, content)
            if not file_issues and parsed:
                yaml_ok += 1
            issues.extend(file_issues)

    passed = len(issues) == 0
    score = 1.0 if passed else max(0.0, 1.0 - 0.1 * min(10, len(issues)))
    return LevelZeroResult(
        passed=passed, score=score, issues=issues,
        files_scanned=scanned, python_ok=py_ok, json_ok=json_ok, yaml_ok=yaml_ok,
    )


def default_resolver(backend_root: str) -> Callable[[str], bool]:
    """Resolveur base sur l'existence des fichiers sur disque pour app.X.Y."""
    from pathlib import Path

    root = Path(backend_root)

    def resolver(module: str) -> bool:
        parts = module.split(".")
        rel = Path(*parts)
        return ((root / rel / "__init__.py").exists()
                or (root / f"{rel}.py").exists())

    return resolver
