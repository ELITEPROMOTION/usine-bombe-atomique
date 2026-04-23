"""V5.3 BLOC 12 - Assertion Risk Detector (anti-hallucination operationnelle).

Extrait assertions des sorties agent -> classifie / bloque / force regen.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class AssertionRisk:
    text: str
    kind: str                  # function|file|table|endpoint|version|number|date|rule|behavior
    status: str                # proven|probable|unproven|conflicting|stale|blocked
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


# Patterns d'extraction
FN_PATTERN = re.compile(r"\bfunction\s+[`']?(\w+)[`']?|\bdef\s+(\w+)\b")
FILE_PATTERN = re.compile(r"(?:^|[\s'`\"])((?:\.\.?/|[a-zA-Z0-9_\-]+/)?[\w\-]+\.(?:py|md|yml|yaml|json|sql|txt|env|ini|toml))")
TABLE_PATTERN = re.compile(r"\b(?:table|FROM|INTO|UPDATE)\s+[`'\"]?([\w]+)[`'\"]?", re.IGNORECASE)
ENDPOINT_PATTERN = re.compile(r"(?:GET|POST|PUT|DELETE|PATCH)\s+(/[\w\-/{}]+)")
VERSION_PATTERN = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")
DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _exists_function_in_src(src_root: Path, fn_name: str) -> bool:
    for p in src_root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == fn_name:
                    return True
    return False


def _file_exists(path_hint: str, src_root: Path) -> bool:
    # Try multiple plausible locations
    candidates = [Path(path_hint), src_root / path_hint,
                  src_root.parent / path_hint]
    return any(p.exists() for p in candidates)


async def _table_exists(pool: asyncpg.Pool, name: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = $1 LIMIT 1", name.lower(),
        )
    return row is not None


def _endpoint_exists(openapi: dict[str, Any], path: str) -> bool:
    paths = openapi.get("paths") or {}
    if path in paths:
        return True
    # Accept trailing/leading segment mismatches
    for p in paths:
        if p.split("{")[0].rstrip("/") == path.split("{")[0].rstrip("/"):
            return True
    return False


def extract_risks(text: str) -> list[tuple[str, str]]:
    """Extrait (kind, token) candidats."""
    out: list[tuple[str, str]] = []
    for m in FN_PATTERN.finditer(text):
        name = m.group(1) or m.group(2)
        if name:
            out.append(("function", name))
    for m in FILE_PATTERN.finditer(text):
        out.append(("file", m.group(1)))
    for m in TABLE_PATTERN.finditer(text):
        out.append(("table", m.group(1)))
    for m in ENDPOINT_PATTERN.finditer(text):
        out.append(("endpoint", m.group(1)))
    for m in VERSION_PATTERN.finditer(text):
        out.append(("version", m.group(1)))
    for m in DATE_PATTERN.finditer(text):
        out.append(("date", m.group(1)))
    # Dedup
    seen: set[tuple[str, str]] = set()
    uniq: list[tuple[str, str]] = []
    for kind, tok in out:
        k = (kind, tok)
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


async def analyze(
    text: str, *, pool: asyncpg.Pool | None = None,
    src_root: Path | None = None, openapi: dict[str, Any] | None = None,
) -> list[AssertionRisk]:
    """Analyse un texte et retourne les risques."""
    src_root = src_root or Path(__file__).resolve().parents[2]
    risks: list[AssertionRisk] = []
    for kind, tok in extract_risks(text):
        if kind == "function":
            ok = _exists_function_in_src(src_root, tok)
            risks.append(AssertionRisk(
                text=tok, kind=kind,
                status="proven" if ok else "unproven",
                evidence=f"ast_scan: found={ok}"))
        elif kind == "file":
            ok = _file_exists(tok, src_root)
            risks.append(AssertionRisk(
                text=tok, kind=kind,
                status="proven" if ok else "unproven",
                evidence=f"fs_check: found={ok}"))
        elif kind == "table" and pool is not None:
            ok = await _table_exists(pool, tok)
            risks.append(AssertionRisk(
                text=tok, kind=kind,
                status="proven" if ok else "unproven",
                evidence=f"information_schema: found={ok}"))
        elif kind == "endpoint" and openapi is not None:
            ok = _endpoint_exists(openapi, tok)
            risks.append(AssertionRisk(
                text=tok, kind=kind,
                status="proven" if ok else "unproven",
                evidence=f"openapi: found={ok}"))
        else:
            risks.append(AssertionRisk(
                text=tok, kind=kind, status="probable",
                evidence="no_check_available"))
    return risks


def hallucination_score(risks: list[AssertionRisk]) -> float:
    """Retourne ratio 0..1 d'assertions unproven/conflicting/stale/blocked."""
    if not risks:
        return 0.0
    bad = sum(1 for r in risks if r.status in ("unproven", "conflicting",
                                                  "stale", "blocked"))
    return bad / len(risks)


def should_block(score: float, threshold: float = 0.05) -> bool:
    return score > threshold
