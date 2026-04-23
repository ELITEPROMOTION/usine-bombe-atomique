"""Escalade intelligente V4 - UNE question parfaite plutot que bloquer.

Au moment de la creation d'une tache (ou post-echec pour retrying), le
systeme detecte les specs ambigues ou incompletes et genere UNE seule
question cible. La tache entre en statut `waiting_input`, puis est
re-enqueuee automatiquement apres reception de la reponse.

Regles, par ordre de priorite (premiere match wins) :
1. Spec trop courte (< 80 chars) -> "Quel est le domaine et l'objectif principal ?"
2. Aucun domaine detecte mais mots-cles flous -> demander le domaine
3. DZ detecte mais sans chiffres de conformite -> demander les constantes
4. Priorite critical mais pas de contraintes de livraison -> demander SLA
5. Multi-domaines mais conflits potentiels -> question de clarification
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.orchestration.memory_engine import extract_domain_tags

logger = logging.getLogger(__name__)


@dataclass
class Question:
    category: str
    question: str
    evidence: dict[str, Any]


def _dz_missing_constants(spec: str) -> bool:
    low = spec.lower()
    return "dz" in low or "algerie" in low or "algerien" in low \
        and not re.search(r"(0\.19|19\s*%|0\.02|2\s*%|0\.09|9\s*%)", spec)


def detect_question(spec: str, priority: str = "high") -> Question | None:
    """Genere UNE question d'escalade si la spec est ambigue, sinon None."""
    spec = (spec or "").strip()
    domains = extract_domain_tags(spec)

    # 1. Spec trop courte
    if len(spec) < 80:
        return Question(
            category="spec_too_short",
            question=(
                "La specification est tres courte. Pouvez-vous preciser : "
                "1) le domaine (CRUD, paie, VEFA, comptabilite, ...), "
                "2) l'objectif principal, et 3) si des contraintes reglementaires "
                "algeriennes s'appliquent ?"
            ),
            evidence={"spec_length": len(spec)},
        )

    # 2. Aucun domaine identifie
    if not domains:
        return Question(
            category="domain_undetected",
            question=(
                "Aucun domaine metier evident n'a ete detecte dans la specification. "
                "De quel domaine parle-t-il (paie RH, gestion clients VEFA, comptabilite, "
                "catalogue produits, ticketing support, autre) et quelle est la principale "
                "regle metier a implementer ?"
            ),
            evidence={"domains_found": []},
        )

    # 3. DZ mentionne mais constantes manquantes
    if "dz" in domains and not re.search(r"(0\.19|19\s*%|0\.02|2\s*%|0\.09|9\s*%|cnas|irg|tap|tva)",
                                          spec, re.IGNORECASE):
        return Question(
            category="dz_constants_missing",
            question=(
                "La specification cible l'Algerie mais ne mentionne aucune constante "
                "fiscale (TVA 19%, TAP 2%, CNAS 9/26%, IRG, NIN). Lesquelles doivent "
                "etre implementees et sur quelles bases (brut, net, HT) ?"
            ),
            evidence={"domains": domains},
        )

    # 4. Critical sans SLA explicite
    if priority == "critical" and not re.search(r"(sla|latence|qps|rps|throughput|uptime|99\.)",
                                                  spec, re.IGNORECASE):
        return Question(
            category="critical_missing_sla",
            question=(
                "Priorite critical mais aucun SLA n'est precise. Quels objectifs de "
                "performance (latence p95, debit) et de disponibilite (uptime 99.%, RTO/RPO) "
                "doivent cadrer le livrable ?"
            ),
            evidence={"priority": priority},
        )

    # 5. Multi-domaines metiers (>= 3 hors tags techniques transverses)
    TECH_TAGS = {"crud", "dz", "security", "monitoring"}
    business_domains = [d for d in domains if d not in TECH_TAGS]
    if len(business_domains) >= 3:
        return Question(
            category="multi_domain_overlap",
            question=(
                f"Trois domaines metiers distincts ont ete detectes ({', '.join(business_domains)})."
                " S'agit-il d'un systeme unifie ou faut-il livrer des modules separes ?"
                " Quelle est la frontiere de bounded context entre eux ?"
            ),
            evidence={"domains": domains, "business_domains": business_domains},
        )

    return None


async def record_question(pool: asyncpg.Pool, task_id: str, q: Question) -> str:
    """Consigne une question ouverte et passe la tache en `waiting_input`."""
    import json
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pending_questions (task_id, question, category, evidence, status)
            VALUES ($1, $2, $3, $4::jsonb, 'open')
            ON CONFLICT (task_id) DO UPDATE SET
              question = EXCLUDED.question,
              category = EXCLUDED.category,
              evidence = EXCLUDED.evidence,
              status = 'open',
              created_at = NOW(),
              answered_at = NULL,
              answer = NULL
            RETURNING id
            """,
            UUID(task_id), q.question, q.category, json.dumps(q.evidence),
        )
        await conn.execute(
            "UPDATE tasks SET status = 'waiting_input' WHERE id = $1",
            UUID(task_id),
        )
    return str(row["id"])


async def resolve_question(pool: asyncpg.Pool, task_id: str, answer: str) -> bool:
    """Ferme une question ouverte, enrichit le prompt et repasse la tache en `pending`."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE pending_questions
            SET answer = $2, status = 'answered', answered_at = NOW()
            WHERE task_id = $1 AND status = 'open'
            RETURNING id
            """,
            UUID(task_id), answer,
        )
        if not row:
            return False
        # Enrichit le prompt avec la reponse + repasse la tache en pending
        await conn.execute(
            """
            UPDATE tasks
            SET prompt = prompt || E'\n\n[Clarification operateur]\n' || $2,
                status = 'pending'
            WHERE id = $1
            """,
            UUID(task_id), answer,
        )
    return True


async def list_pending(pool: asyncpg.Pool, limit: int = 20) -> list[dict[str, Any]]:
    """Retourne les questions d'escalade encore ouvertes pour le dashboard."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pq.id, pq.task_id, pq.question, pq.category, pq.evidence,
                   pq.created_at, t.prompt, t.priority
            FROM pending_questions pq
            JOIN tasks t ON t.id = pq.task_id
            WHERE pq.status = 'open'
            ORDER BY pq.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [
        {
            "id": str(r["id"]),
            "task_id": str(r["task_id"]),
            "question": r["question"],
            "category": r["category"],
            "evidence": r["evidence"],
            "prompt_excerpt": (r["prompt"] or "")[:180],
            "priority": r["priority"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
