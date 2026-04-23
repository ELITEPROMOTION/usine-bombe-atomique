"""Self-Improver V4 - genere des items de backlog a partir des signaux reels.

Analyse des sources suivantes :
- error_catalog : patterns d'erreurs recurrents (>= 3 occurrences)
- agent_benchmarks : agents sous-performants (avg_score < 0.70 sur >= 5 runs)
- project_memory : dimensions faibles recurrentes (via les confidence stocks)
- api_usage : couts anormaux par projet (projets > $0.50 -> review ROI)

Chaque proposition a une `signature` (hash deterministe) : la meme
proposition ne cree qu'une entree, mais son `occurrences` est incremente et
`last_seen_at` mis a jour, ce qui permet de voir la recurrence.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


Category = str  # 'error_pattern' | 'agent_weak' | 'calibration' | 'coverage_gap' | 'cost' | 'architecture'
Priority = str  # 'low' | 'medium' | 'high' | 'critical'


@dataclass
class Proposal:
    category: Category
    priority: Priority
    title: str
    rationale: str
    evidence: dict[str, Any]

    def signature(self) -> str:
        canon = f"{self.category}|{self.title}"
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()


async def scan(pool: asyncpg.Pool) -> list[Proposal]:
    """Analyse la memoire et retourne la liste des propositions."""
    out: list[Proposal] = []
    out.extend(await _scan_errors(pool))
    out.extend(await _scan_weak_agents(pool))
    out.extend(await _scan_calibration(pool))
    out.extend(await _scan_cost(pool))
    return out


async def _scan_errors(pool: asyncpg.Pool) -> list[Proposal]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent_id, error_type, sample_message, occurrences
            FROM error_catalog WHERE occurrences >= 3
            ORDER BY occurrences DESC LIMIT 10
            """
        )
    proposals: list[Proposal] = []
    for r in rows:
        priority = "critical" if r["occurrences"] >= 10 \
            else "high" if r["occurrences"] >= 5 else "medium"
        proposals.append(Proposal(
            category="error_pattern",
            priority=priority,
            title=f"Ajouter un garde-fou pour {r['error_type']} dans {r['agent_id']}",
            rationale=f"{r['occurrences']} occurrences observees. "
                      "Ajouter une verification preventive ou un retry avec backoff.",
            evidence={
                "agent_id": r["agent_id"],
                "error_type": r["error_type"],
                "occurrences": r["occurrences"],
                "sample": (r["sample_message"] or "")[:200],
            },
        ))
    return proposals


async def _scan_weak_agents(pool: asyncpg.Pool) -> list[Proposal]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent_id, agent_name, executions, successes, failures, avg_score
            FROM agent_benchmarks
            WHERE executions >= 3 AND (avg_score < 0.70 OR failures > 0)
            ORDER BY avg_score ASC
            LIMIT 5
            """
        )
    proposals: list[Proposal] = []
    for r in rows:
        rate = r["successes"] / max(1, r["executions"])
        priority = "high" if rate < 0.70 else "medium"
        proposals.append(Proposal(
            category="agent_weak",
            priority=priority,
            title=f"Ameliorer ou remplacer {r['agent_name']} ({r['agent_id']})",
            rationale=f"avg_score={float(r['avg_score']):.2f} "
                      f"succes={rate:.0%} sur {r['executions']} runs. "
                      "Envisager une v2 du prompt ou un remplacement d'implementation.",
            evidence={
                "agent_id": r["agent_id"], "executions": r["executions"],
                "successes": r["successes"], "failures": r["failures"],
                "avg_score": float(r["avg_score"]),
            },
        ))
    return proposals


async def _scan_calibration(pool: asyncpg.Pool) -> list[Proposal]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n,
                   COALESCE(AVG(confidence_composite), 0) AS avg_conf,
                   COALESCE(AVG(validation_score), 0) AS avg_val
            FROM project_memory
            """
        )
    if not row or (row["n"] or 0) < 5:
        return []
    diff = float(row["avg_val"]) - float(row["avg_conf"])
    if abs(diff) < 0.12:
        return []
    direction = "optimistes" if diff > 0 else "pessimistes"
    return [Proposal(
        category="calibration",
        priority="medium",
        title=f"Recalibrer le confidence_scorer (ecart {diff:+.2f} avec validation)",
        rationale=f"Sur {row['n']} projets, validation={float(row['avg_val']):.2f} "
                  f"et confidence={float(row['avg_conf']):.2f}. "
                  f"Les scores de confiance sont {direction} par rapport au pipeline.",
        evidence={
            "samples": int(row["n"]),
            "avg_validation": float(row["avg_val"]),
            "avg_confidence": float(row["avg_conf"]),
            "gap": round(diff, 4),
        },
    )]


async def _scan_cost(pool: asyncpg.Pool) -> list[Proposal]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n, COALESCE(MAX(total_cost_usd), 0) AS max_cost,
                   COALESCE(AVG(total_cost_usd), 0) AS avg_cost
            FROM project_memory
            """
        )
    if not row or (row["n"] or 0) < 3 or float(row["max_cost"]) < 0.50:
        return []
    return [Proposal(
        category="cost",
        priority="medium",
        title="Optimiser les couts LLM (projet > $0.50 detecte)",
        rationale=f"Cout max observe ${float(row['max_cost']):.3f} sur {row['n']} projets "
                  f"(moyenne ${float(row['avg_cost']):.3f}). Envisager Haiku pour les specs < 2k ou "
                  "re-utiliser des resultats similaires via `recall_similar`.",
        evidence={
            "projects": int(row["n"]),
            "max_cost_usd": float(row["max_cost"]),
            "avg_cost_usd": float(row["avg_cost"]),
        },
    )]


async def persist(pool: asyncpg.Pool, proposals: list[Proposal]) -> int:
    """Upserte les propositions dans `improvement_backlog` (dedup par signature)."""
    if not proposals:
        return 0
    inserted = 0
    async with pool.acquire() as conn, conn.transaction():
        for p in proposals:
            await conn.execute(
                """
                    INSERT INTO improvement_backlog
                      (signature, category, priority, title, rationale, evidence, status)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,'open')
                    ON CONFLICT (signature) DO UPDATE SET
                      priority = EXCLUDED.priority,
                      rationale = EXCLUDED.rationale,
                      evidence = EXCLUDED.evidence,
                      occurrences = improvement_backlog.occurrences + 1,
                      last_seen_at = NOW()
                    """,
                p.signature(), p.category, p.priority,
                p.title[:240], p.rationale, json.dumps(p.evidence),
            )
            inserted += 1
    return inserted


async def run_cycle(pool: asyncpg.Pool) -> dict[str, Any]:
    """Scan + persist en une etape. Appele apres chaque tache par le worker."""
    proposals = await scan(pool)
    inserted = await persist(pool, proposals)
    return {"proposals": [
        {"category": p.category, "priority": p.priority, "title": p.title}
        for p in proposals
    ], "persisted": inserted}


async def list_backlog(pool: asyncpg.Pool, status: str | None = None,
                        limit: int = 50) -> list[dict[str, Any]]:
    """Retourne les items du backlog, optionnellement filtres par statut."""
    sql = """
        SELECT id, signature, category, priority, title, rationale,
               evidence, status, occurrences, first_seen_at, last_seen_at
        FROM improvement_backlog
    """
    args: list[Any] = []
    if status:
        sql += " WHERE status = $1"
        args.append(status)
    sql += " ORDER BY priority DESC, occurrences DESC, last_seen_at DESC LIMIT %d" % int(limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [
        {
            "id": str(r["id"]),
            "signature": r["signature"],
            "category": r["category"],
            "priority": r["priority"],
            "title": r["title"],
            "rationale": r["rationale"],
            "evidence": r["evidence"],
            "status": r["status"],
            "occurrences": r["occurrences"],
            "first_seen_at": r["first_seen_at"].isoformat(),
            "last_seen_at": r["last_seen_at"].isoformat(),
        }
        for r in rows
    ]
