"""Upgrade 35 - Defect Taxonomy.

Chaque ecart detecte est enregistre avec :
- nature : structure / logique / securite / conformite / performance
- gravite : info / mineure / bloquante / vitale
- rayon_impact : local / module / service / system
- signature : hash stable pour dedup
- correction_patch_id : lien vers le patch de remediation

Le module expose classify() + record() + list_by_task() pour alimenter
le Quality Kernel et les KPIs truth_kpis.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

NATURE_RULES: dict[str, tuple[str, ...]] = {
    "structure":   ("syntax", "ast_parse", "missing_file", "broken_import"),
    "logique":     ("test_fail", "assertion", "logic_error", "wrong_result"),
    "securite":    ("bandit", "secret", "hardcoded", "injection", "cve"),
    "conformite":  ("dz_rule", "gdpr", "tva", "tap", "cnas", "irg"),
    "performance": ("timeout", "slow", "complexity", "memory", "n_plus_1"),
}

GRAVITY_LEVELS = ("info", "mineure", "bloquante", "vitale")


@dataclass
class Defect:
    title: str
    nature: str
    gravite: str
    rayon_impact: str = "local"
    details: str = ""


def classify(title: str, details: str = "") -> tuple[str, str]:
    """Determine nature + gravite a partir du titre et des details."""
    corpus = (title + " " + details).lower()
    nature = "logique"
    for n, patterns in NATURE_RULES.items():
        if any(p in corpus for p in patterns):
            nature = n
            break
    if any(k in corpus for k in ("critical", "fatal", "breach", "data loss")):
        gravite = "vitale"
    elif any(k in corpus for k in ("fail", "error", "block", "security",
                                     "secret", "hardcoded", "injection",
                                     "vulnerab", "cve")):
        gravite = "bloquante"
    elif any(k in corpus for k in ("warn", "minor", "improve")):
        gravite = "mineure"
    else:
        gravite = "info"
    return nature, gravite


def signature(defect: Defect) -> str:
    canon = f"{defect.nature}|{defect.title[:120]}"
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


async def record(
    pool: asyncpg.Pool, task_id: str, defect: Defect,
) -> str:
    sig = signature(defect)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO defect_taxonomy
              (task_id, nature, gravite, rayon_impact, signature, title, details)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (task_id, signature) DO UPDATE SET
              recurrence = defect_taxonomy.recurrence + 1,
              gravite = EXCLUDED.gravite
            RETURNING id
            """,
            UUID(task_id), defect.nature, defect.gravite, defect.rayon_impact,
            sig, defect.title[:240], defect.details[:2000],
        )
    return str(row["id"])


async def list_by_task(pool: asyncpg.Pool, task_id: str) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, nature, gravite, rayon_impact, recurrence, title, details, created_at
            FROM defect_taxonomy WHERE task_id = $1
            ORDER BY gravite DESC, recurrence DESC
            """,
            UUID(task_id),
        )
    return [
        {
            "id": str(r["id"]),
            "nature": r["nature"], "gravite": r["gravite"],
            "rayon_impact": r["rayon_impact"], "recurrence": r["recurrence"],
            "title": r["title"], "details": r["details"],
            "created_at": r["created_at"].isoformat(),
        } for r in rows
    ]


async def summary(pool: asyncpg.Pool) -> dict[str, Any]:
    """Distribution globale par nature x gravite."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT nature, gravite, COUNT(*) AS n FROM defect_taxonomy "
            "GROUP BY nature, gravite ORDER BY n DESC"
        )
    matrix: dict[str, dict[str, int]] = {}
    for r in rows:
        matrix.setdefault(r["nature"], {})[r["gravite"]] = int(r["n"])
    total = sum(v for n in matrix.values() for v in n.values())
    return {"total": total, "matrix": matrix}
