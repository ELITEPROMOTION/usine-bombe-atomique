"""V5.3 BLOC 3 - Assertion Normalizer.

Convertit texte source -> assertions atomiques typees (10 types).
Utilise heuristiques + patterns (pas de LLM ici, deterministe).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


ASSERTION_TYPES = [
    "fact", "rule", "constraint", "warning", "vulnerability",
    "deprecation", "assumption", "contradiction", "benchmark", "requirement",
]


# Heuristiques de classification
CLASSIFIERS: list[tuple[str, re.Pattern[str]]] = [
    ("vulnerability",
     re.compile(r"\bCVE-\d{4}-\d{4,}|vulnerability|exploit\b", re.IGNORECASE)),
    ("deprecation",
     re.compile(r"\b(deprecated|obsolete|will\s+be\s+removed)\b", re.IGNORECASE)),
    ("warning",
     re.compile(r"\b(warning|caution|attention)\b", re.IGNORECASE)),
    ("requirement",
     re.compile(r"\b(MUST|SHALL|REQUIRED|obligatoire)\b", re.IGNORECASE)),
    ("constraint",
     re.compile(r"\b(limit|max|min|constraint|limited to)\b", re.IGNORECASE)),
    ("rule",
     re.compile(r"\b(rule|loi|article|RFC|RGPD|GDPR)\b", re.IGNORECASE)),
    ("benchmark",
     re.compile(r"\b(benchmark|throughput|latency|qps|tps)\b", re.IGNORECASE)),
    ("assumption",
     re.compile(r"\b(assume|suppose|hypothese|expected)\b", re.IGNORECASE)),
    ("contradiction",
     re.compile(r"\b(however|but|contradict|opposite)\b", re.IGNORECASE)),
]


def classify(text: str) -> str:
    for name, pat in CLASSIFIERS:
        if pat.search(text or ""):
            return name
    return "fact"


def severity_for(text: str, kind: str) -> str:
    low = (text or "").lower()
    if kind == "vulnerability":
        if "critical" in low or "kev" in low:
            return "critical"
        if "high" in low:
            return "high"
        return "medium"
    if any(w in low for w in ("critical", "urgent", "must")):
        return "high"
    if any(w in low for w in ("warning", "may", "optional")):
        return "low"
    return "medium"


@dataclass
class NormalizedAssertion:
    source_id: str
    content_hash: str
    normalized_text: str
    assertion_type: str
    domain: str
    severity: str
    confidence: int


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_sentences(text: str, max_len: int = 500) -> list[str]:
    """Split en phrases (simple heuristique)."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if 15 <= len(p) <= max_len:
            out.append(p)
    return out


def normalize(
    source_id: str, text: str, domain: str,
    source_version: str | None = None,
) -> list[NormalizedAssertion]:
    """Extraire les assertions d'un texte."""
    sentences = split_sentences(text)
    out: list[NormalizedAssertion] = []
    seen: set[str] = set()
    for s in sentences:
        h = _hash(s)
        if h in seen:
            continue
        seen.add(h)
        kind = classify(s)
        sev = severity_for(s, kind)
        out.append(NormalizedAssertion(
            source_id=source_id, content_hash=h,
            normalized_text=s, assertion_type=kind,
            domain=domain, severity=sev, confidence=80,
        ))
    return out


async def persist(
    pool: asyncpg.Pool, assertions: list[NormalizedAssertion],
) -> list[str]:
    """Insere + retourne les assertion_ids."""
    ids: list[str] = []
    if not assertions:
        return ids
    async with pool.acquire() as conn:
        for a in assertions:
            row = await conn.fetchrow(
                """
                INSERT INTO truth_assertions(
                    source_id, content_hash, normalized_text,
                    assertion_type, domain, severity, confidence,
                    status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'unproven')
                ON CONFLICT DO NOTHING
                RETURNING assertion_id
                """,
                UUID(a.source_id) if a.source_id else None,
                a.content_hash, a.normalized_text[:2000],
                a.assertion_type, a.domain[:60],
                a.severity, a.confidence,
            )
            if row:
                ids.append(str(row["assertion_id"]))
    return ids


async def list_by_source(
    pool: asyncpg.Pool, source_id: str, limit: int = 50,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT assertion_id, assertion_type, domain, severity,
                   confidence, status, normalized_text
            FROM truth_assertions WHERE source_id = $1
            ORDER BY extracted_at DESC LIMIT $2
            """, UUID(source_id), limit,
        )
    return [{
        "assertion_id": str(r["assertion_id"]),
        "type": r["assertion_type"], "domain": r["domain"],
        "severity": r["severity"], "confidence": r["confidence"],
        "status": r["status"], "text": r["normalized_text"],
    } for r in rows]
