"""Memory Engine V3 - persistance apprenante.

Quatre domaines :
1. `project_memory` : un enregistrement par tache completee (spec, verdict, scores, cout).
2. `error_catalog`  : catalogue d'erreurs (agent + signature) avec comptage.
3. `agent_benchmarks` : stats rolling par agent (exec, succes, duree moyenne, cout, score).
4. `prompt_variants` : variantes de system prompt pour A/B testing (voir prompt_ab.py).

Le moteur est append-only et idempotent autant que possible : un meme task_id
ne cree qu'une entree project_memory (contrainte UNIQUE).
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


DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "paie":       ("paie", "salaire", "rh", "cnas", "irg", "g50"),
    "vefa":       ("vefa", "residence", "immobilier", "palier"),
    "crud":       ("crud",),
    "comptable":  ("comptable", "bilan", "ecriture", "journal"),
    "ecommerce":  ("produit", "catalogue", "panier", "commande"),
    "ticketing":  ("ticket", "sla", "support", "incident"),
    "dz":         ("algerie", "dzd", "dinar", "tva", "tap"),
    "security":   ("jwt", "oauth", "rbac", "audit"),
    "monitoring": ("datadog", "metrique", "alerting"),
}


@dataclass
class ProjectRecord:
    task_id: str
    spec_excerpt: str
    domain_tags: list[str]
    artifacts_count: int
    verdict: str
    validation_score: float
    confidence_composite: float
    confidence_label: str
    total_cost_usd: float
    duration_ms: int


def extract_domain_tags(spec: str) -> list[str]:
    """Extrait des tags de domaine par mots-cles. Deterministe."""
    low = (spec or "").lower()
    hits: list[str] = []
    for tag, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in low for kw in keywords):
            hits.append(tag)
    return sorted(hits)


def error_signature(agent_id: str, error_type: str, message: str) -> str:
    """Signature stable (64 car) pour deduplication : agent + type + 1re ligne du msg."""
    canon = (message or "").splitlines()[0].strip()[:200] if message else ""
    raw = f"{agent_id}|{error_type}|{canon}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


ERROR_PATTERNS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("syntax", "parseerror"), "SyntaxError"),
    (("timeout",), "Timeout"),
    (("permission", "denied"), "PermissionError"),
    (("connection", "connect"), "ConnectionError"),
    (("not found", "404"), "NotFound"),
    (("credit", "quota", "rate limit"), "QuotaError"),
    (("invalid",), "ValidationError"),
)


def classify_error(message: str) -> str:
    """Heuristique rapide : categorise un message d'erreur (table-driven)."""
    msg = (message or "").lower()
    for needles, label in ERROR_PATTERNS:
        if any(n in msg for n in needles):
            return label
    return "RuntimeError"


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

async def record_project(pool: asyncpg.Pool, rec: ProjectRecord) -> str:
    """Inserte ou met a jour une entree `project_memory` pour la tache."""
    row = await _fetchrow(pool, """
        INSERT INTO project_memory
          (task_id, spec_excerpt, domain_tags, artifacts_count, verdict,
           validation_score, confidence_composite, confidence_label,
           total_cost_usd, duration_ms)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        ON CONFLICT (task_id) DO UPDATE SET
          spec_excerpt = EXCLUDED.spec_excerpt,
          domain_tags = EXCLUDED.domain_tags,
          artifacts_count = EXCLUDED.artifacts_count,
          verdict = EXCLUDED.verdict,
          validation_score = EXCLUDED.validation_score,
          confidence_composite = EXCLUDED.confidence_composite,
          confidence_label = EXCLUDED.confidence_label,
          total_cost_usd = EXCLUDED.total_cost_usd,
          duration_ms = EXCLUDED.duration_ms
        RETURNING id
        """,
        UUID(rec.task_id), rec.spec_excerpt[:4000], rec.domain_tags,
        rec.artifacts_count, rec.verdict, rec.validation_score,
        rec.confidence_composite, rec.confidence_label,
        rec.total_cost_usd, rec.duration_ms,
    )
    return str(row["id"])


async def record_error(pool: asyncpg.Pool, agent_id: str,
                        error_type: str, message: str) -> None:
    """Consigne un incident agent dans `error_catalog` (upsert avec compteur)."""
    sig = error_signature(agent_id, error_type, message)
    await _execute(pool, """
        INSERT INTO error_catalog
          (agent_id, signature, error_type, sample_message, occurrences)
        VALUES ($1,$2,$3,$4,1)
        ON CONFLICT (agent_id, signature) DO UPDATE SET
          occurrences = error_catalog.occurrences + 1,
          last_seen_at = NOW()
        """, agent_id, sig, error_type, (message or "")[:1000])


async def update_agent_benchmark(
    pool: asyncpg.Pool,
    agent_id: str,
    agent_name: str,
    status: str,
    duration_ms: float,
    score: float | None,
    cost_usd: float = 0.0,
) -> None:
    """Met a jour les stats rolling d'un agent dans `agent_benchmarks`."""
    success = 1 if status == "success" else 0
    failure = 1 if status == "failed" else 0
    row = await _fetchrow(pool,
        "SELECT avg_score, score_samples FROM agent_benchmarks WHERE agent_id=$1",
        agent_id,
    )
    if row and score is not None:
        prev_avg = float(row["avg_score"])
        n = int(row["score_samples"])
        new_avg = (prev_avg * n + score) / (n + 1)
        new_samples = n + 1
    elif row:
        new_avg = float(row["avg_score"])
        new_samples = int(row["score_samples"])
    else:
        new_avg = score if score is not None else 0.0
        new_samples = 1 if score is not None else 0

    await _execute(pool, """
        INSERT INTO agent_benchmarks
          (agent_id, agent_name, executions, successes, failures,
           total_duration_ms, total_cost_usd, avg_score, score_samples)
        VALUES ($1,$2,1,$3,$4,$5,$6,$7,$8)
        ON CONFLICT (agent_id) DO UPDATE SET
          executions = agent_benchmarks.executions + 1,
          successes  = agent_benchmarks.successes + EXCLUDED.successes,
          failures   = agent_benchmarks.failures  + EXCLUDED.failures,
          total_duration_ms = agent_benchmarks.total_duration_ms + EXCLUDED.total_duration_ms,
          total_cost_usd    = agent_benchmarks.total_cost_usd + EXCLUDED.total_cost_usd,
          avg_score         = $7,
          score_samples     = $8,
          last_update       = NOW()
        """,
        agent_id, agent_name, success, failure,
        int(duration_ms), cost_usd, new_avg, new_samples,
    )


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

async def recall_similar(pool: asyncpg.Pool, spec: str, limit: int = 5) -> list[dict[str, Any]]:
    """Trouve les projets passes les plus proches (intersection de tags de domaine)."""
    tags = extract_domain_tags(spec)
    if not tags:
        rows = await _fetch(pool, """
            SELECT task_id, spec_excerpt, domain_tags, verdict, confidence_composite,
                   confidence_label, created_at
            FROM project_memory ORDER BY created_at DESC LIMIT $1
            """, limit)
    else:
        rows = await _fetch(pool, """
            SELECT task_id, spec_excerpt, domain_tags, verdict, confidence_composite,
                   confidence_label, created_at,
                   cardinality(ARRAY(SELECT unnest(domain_tags) INTERSECT SELECT unnest($1::text[]))) AS overlap
            FROM project_memory
            ORDER BY overlap DESC, created_at DESC
            LIMIT $2
            """, tags, limit)
    return [dict(r) for r in rows]


async def agents_benchmarks(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Retourne les stats par agent pour l'exposition analytics."""
    rows = await _fetch(pool, """
        SELECT agent_id, agent_name, executions, successes, failures,
               total_duration_ms, total_cost_usd, avg_score, last_update
        FROM agent_benchmarks
        ORDER BY executions DESC
        """)
    return [
        {
            "agent_id": r["agent_id"],
            "agent_name": r["agent_name"],
            "executions": r["executions"],
            "successes": r["successes"],
            "failures": r["failures"],
            "success_rate": round(r["successes"] / max(1, r["executions"]), 4),
            "avg_duration_ms": round(r["total_duration_ms"] / max(1, r["executions"]), 1),
            "total_cost_usd": float(r["total_cost_usd"]),
            "avg_score": float(r["avg_score"]),
            "last_update": r["last_update"].isoformat() if r["last_update"] else None,
        }
        for r in rows
    ]


async def top_errors(pool: asyncpg.Pool, limit: int = 10) -> list[dict[str, Any]]:
    """Top N des erreurs les plus frequentes, tous agents confondus."""
    rows = await _fetch(pool, """
        SELECT agent_id, error_type, sample_message, occurrences,
               first_seen_at, last_seen_at
        FROM error_catalog ORDER BY occurrences DESC, last_seen_at DESC LIMIT $1
        """, limit)
    return [
        {
            "agent_id": r["agent_id"],
            "error_type": r["error_type"],
            "sample_message": r["sample_message"],
            "occurrences": r["occurrences"],
            "first_seen_at": r["first_seen_at"].isoformat(),
            "last_seen_at": r["last_seen_at"].isoformat(),
        }
        for r in rows
    ]


async def overview(pool: asyncpg.Pool) -> dict[str, Any]:
    """Agregat global des projets memorises : volumes, scores moyens, couts."""
    row = await _fetchrow(pool, """
        SELECT
          COUNT(*) AS projects,
          COUNT(*) FILTER (WHERE verdict = 'PASS') AS pass_count,
          COUNT(*) FILTER (WHERE verdict = 'CONDITIONAL_PASS') AS cpass_count,
          COUNT(*) FILTER (WHERE verdict IN ('SOFT_FAIL','HARD_FAIL')) AS fail_count,
          COALESCE(AVG(confidence_composite), 0) AS avg_confidence,
          COALESCE(AVG(validation_score), 0) AS avg_validation,
          COALESCE(SUM(total_cost_usd), 0) AS total_cost_usd,
          COALESCE(AVG(duration_ms), 0) AS avg_duration_ms
        FROM project_memory
        """)
    return {
        "projects": int(row["projects"] or 0),
        "pass_count": int(row["pass_count"] or 0),
        "cpass_count": int(row["cpass_count"] or 0),
        "fail_count": int(row["fail_count"] or 0),
        "avg_confidence": float(row["avg_confidence"] or 0),
        "avg_validation": float(row["avg_validation"] or 0),
        "total_cost_usd": float(row["total_cost_usd"] or 0),
        "avg_duration_ms": float(row["avg_duration_ms"] or 0),
    }


async def recent_trend(pool: asyncpg.Pool, limit: int = 30) -> list[dict[str, Any]]:
    """Derniere fenetre de projets, trie par date pour charts de tendance."""
    rows = await _fetch(pool, """
        SELECT task_id, verdict, validation_score, confidence_composite,
               confidence_label, total_cost_usd, created_at, spec_excerpt,
               domain_tags
        FROM project_memory
        ORDER BY created_at DESC
        LIMIT $1
        """, limit)
    return [
        {
            "task_id": str(r["task_id"]),
            "verdict": r["verdict"],
            "validation_score": float(r["validation_score"]),
            "confidence": float(r["confidence_composite"]),
            "label": r["confidence_label"],
            "cost_usd": float(r["total_cost_usd"]),
            "created_at": r["created_at"].isoformat(),
            "spec_excerpt": (r["spec_excerpt"] or "")[:160],
            "domain_tags": list(r["domain_tags"] or []),
        }
        for r in rows
    ]


async def pending_decisions(pool: asyncpg.Pool, limit: int = 20) -> list[dict[str, Any]]:
    """Taches en attente de decision operateur (fails + scores faibles)."""
    rows = await _fetch(pool, """
        SELECT t.id, t.prompt, t.status, t.validation_score, t.rework_count,
               t.created_at, t.updated_at
        FROM tasks t
        WHERE t.status IN ('failed','reworking') OR (t.status = 'completed' AND t.validation_score < 0.85)
        ORDER BY t.updated_at DESC
        LIMIT $1
        """, limit)
    return [
        {
            "task_id": str(r["id"]),
            "prompt_excerpt": (r["prompt"] or "")[:140],
            "status": r["status"],
            "validation_score": float(r["validation_score"]),
            "rework_count": r["rework_count"],
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# asyncpg helpers - accept pool or single connection
# ---------------------------------------------------------------------------

async def _fetchrow(pool: asyncpg.Pool, sql: str, *args: Any):
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, *args)


async def _fetch(pool: asyncpg.Pool, sql: str, *args: Any):
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


async def _execute(pool: asyncpg.Pool, sql: str, *args: Any) -> str:
    async with pool.acquire() as conn:
        return await conn.execute(sql, *args)


def sanitize_spec(spec: str, length: int = 400) -> str:
    """Normalise un prompt (whitespace collapse + tronque) pour l'affichage."""
    cleaned = re.sub(r"\s+", " ", (spec or "").strip())
    return cleaned[:length]
