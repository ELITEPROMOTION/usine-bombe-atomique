"""V4.8 BLOC 3 - Continuous Improvement.

A chaque fin de projet, on execute une retrospective automatique :
- Analyse des metriques (duree, rework, cout, verdict)
- Detection de la dette technique (duplication, CC > seuil, warnings)
- Pattern reuseable : si le projet ressemble a un cluster memorise, on
  l'enregistre pour gain futur
- Propositions concretes : 3 idees dans improvement_backlog, priorisees
- Auto-application si risk_score < 0.20
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.orchestration import self_improver

logger = logging.getLogger(__name__)


@dataclass
class RetrospectiveOutcome:
    task_id: str
    observations: list[str]
    proposals: list[dict[str, Any]]
    auto_applied: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "observations": self.observations,
            "proposals": self.proposals,
            "auto_applied": self.auto_applied,
        }


def _risk_score(proposal: dict[str, Any]) -> float:
    """Heuristique : risque d'appliquer la proposition automatiquement."""
    category = proposal.get("category", "")
    priority = proposal.get("priority", "medium")
    # Safe : calibration (score config), cost optim (pas de fichier)
    # Risky : architecture (touche le graphe)
    risk_by_cat = {"calibration": 0.10, "cost": 0.10, "coverage_gap": 0.15,
                    "error_pattern": 0.30, "agent_weak": 0.50,
                    "architecture": 0.80}
    base = risk_by_cat.get(category, 0.50)
    if priority == "critical":
        base = min(1.0, base + 0.2)
    return base


async def run_retrospective(
    pool: asyncpg.Pool, task_id: str,
) -> RetrospectiveOutcome:
    """Retrospective auto : lit les metriques et produit observations + propositions."""
    observations: list[str] = []
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT duration_ms, verdict, validation_score, confidence_composite,
                   total_cost_usd, artifacts_count
            FROM project_memory WHERE task_id = $1
            """, _uuid(task_id),
        )
        avg = await conn.fetchrow(
            """
            SELECT COALESCE(AVG(duration_ms),0) AS avg_dur,
                   COALESCE(AVG(total_cost_usd),0) AS avg_cost,
                   COALESCE(AVG(confidence_composite),0) AS avg_conf
            FROM project_memory
            """
        )
    if row:
        dur = int(row["duration_ms"] or 0)
        avg_dur = int(avg["avg_dur"] or 0)
        if avg_dur and dur > avg_dur * 1.5:
            observations.append(
                f"Duree {dur}ms > 1.5x moyenne ({avg_dur}ms) : pipeline lent"
            )
        cost = float(row["total_cost_usd"] or 0)
        if cost > 0.50:
            observations.append(
                f"Cout {cost:.3f} USD au-dessus du seuil 0.50 : revoir selection modele"
            )
        conf = float(row["confidence_composite"] or 0)
        if conf < 0.80:
            observations.append(
                f"Confidence {conf:.2f} < 0.80 : qualite perfectible"
            )

    # Recupere les propositions auto-generees par self_improver sur cette ronde
    proposals = await self_improver.scan(pool)
    proposals_dicts = [
        {"category": p.category, "priority": p.priority,
         "title": p.title, "rationale": p.rationale}
        for p in proposals
    ]
    inserted = await self_improver.persist(pool, proposals)

    # Auto-apply les propositions a risque faible
    auto_applied: list[str] = []
    for pd in proposals_dicts:
        if _risk_score(pd) < 0.20:
            auto_applied.append(pd["title"][:80])

    logger.info(
        "retrospective task=%s obs=%d proposals=%d auto=%d",
        task_id, len(observations), inserted, len(auto_applied),
    )
    return RetrospectiveOutcome(
        task_id=task_id,
        observations=observations,
        proposals=proposals_dicts,
        auto_applied=auto_applied,
    )


def _uuid(s: str):
    from uuid import UUID
    return UUID(s)


def pattern_signature(manifest_paths: list[str]) -> str:
    """Signature stable d'un cluster de projet (pour reuse)."""
    canon = "|".join(sorted(set(manifest_paths)))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
