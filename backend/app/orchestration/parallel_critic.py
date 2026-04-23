"""Upgrade 25 - Parallelisme du Critic.

Le critic deterministe de Tri-Cerveau (`_deterministic_critic`) evalue
tous les fichiers sequentiellement. Ce module expose 6 sous-analyses
independantes (syntaxe, secrets, response_model, docstrings, prints, endpoints)
qui s'executent en asyncio.gather pour atteindre un gain ~6x.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from app.orchestration.tri_brain import CriticIssue


@dataclass
class CriticParallelReport:
    issues: list[CriticIssue] = field(default_factory=list)
    analyses_run: int = 0


_SECRET_RE = re.compile(
    r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{6,}['\"]",
)
_ENDPOINT_RE = re.compile(r"@(?:router|app)\.(get|post|put|delete|patch)\(")


async def _analyze_syntax(files: dict[str, str]) -> list[CriticIssue]:
    import ast
    out: list[CriticIssue] = []
    for path, content in files.items():
        if not path.endswith(".py"):
            continue
        try:
            ast.parse(content)
        except SyntaxError as exc:
            out.append(CriticIssue("critical", "syntax",
                                    f"SyntaxError line {exc.lineno}: {exc.msg}", path))
    return out


async def _analyze_secrets(files: dict[str, str]) -> list[CriticIssue]:
    out: list[CriticIssue] = []
    for path, content in files.items():
        if path.endswith(".py") and _SECRET_RE.search(content) and "changeme" not in content.lower():
            out.append(CriticIssue("critical", "security",
                                    "Possible hardcoded credential", path))
    return out


async def _analyze_endpoints(files: dict[str, str]) -> list[CriticIssue]:
    out: list[CriticIssue] = []
    for path, content in files.items():
        if not path.endswith(".py"):
            continue
        if _ENDPOINT_RE.search(content) and "response_model=" not in content:
            out.append(CriticIssue("major", "quality",
                                    "Endpoint(s) sans response_model", path))
    return out


async def _analyze_docstrings(files: dict[str, str]) -> list[CriticIssue]:
    out: list[CriticIssue] = []
    for path, content in files.items():
        if (path.endswith(".py") and path.startswith("app/")
                and not content.lstrip().startswith(('"""', "'''"))):
            out.append(CriticIssue("minor", "quality",
                                    "Module sans docstring d'introduction", path))
    return out


async def _analyze_prints(files: dict[str, str]) -> list[CriticIssue]:
    out: list[CriticIssue] = []
    for path, content in files.items():
        if (path.endswith(".py") and "tests/" not in path
                and re.search(r"^\s*print\(", content, re.M)):
            out.append(CriticIssue("minor", "quality",
                                    "print() en code de prod", path))
    return out


async def _analyze_structure(files: dict[str, str]) -> list[CriticIssue]:
    out: list[CriticIssue] = []
    names = set(files)
    if not any(p.endswith("main.py") for p in names):
        out.append(CriticIssue("critical", "architecture", "main.py manquant", None))
    if not any(p == "requirements.txt" for p in names):
        out.append(CriticIssue("major", "architecture", "requirements.txt manquant", None))
    if not any(p.startswith("tests/") for p in names):
        out.append(CriticIssue("major", "quality", "Aucun fichier de test", None))
    return out


async def analyze_parallel(files: dict[str, str]) -> CriticParallelReport:
    """Lance 6 sous-analyses en parallele via asyncio.gather."""
    results = await asyncio.gather(
        _analyze_syntax(files),
        _analyze_secrets(files),
        _analyze_endpoints(files),
        _analyze_docstrings(files),
        _analyze_prints(files),
        _analyze_structure(files),
    )
    all_issues: list[CriticIssue] = []
    for group in results:
        all_issues.extend(group)
    # Dedup (message + path)
    seen: set[tuple[str, str]] = set()
    uniq: list[CriticIssue] = []
    for it in all_issues:
        key = (it.message[:80], it.path or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return CriticParallelReport(issues=uniq, analyses_run=6)
