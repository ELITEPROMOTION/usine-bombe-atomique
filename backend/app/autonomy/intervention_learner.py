"""V5.1 BLOC 5 - Intervention Learner.

Post-mortem automatique apres chaque intervention Ahmed :
  - Etait-elle necessaire ? (evaluation retrospective)
  - Y avait-il un chemin autonome viable ?
  - Y a-t-il une signature recurrente ? -> negative_escalation_registry

Si une intervention est jugee NON necessaire (ex: la reponse etait dans
le CDC), on enregistre la signature pour eviter la meme escalation la
prochaine fois.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg


def _as_uuid(v: str | UUID) -> UUID:
    return v if isinstance(v, UUID) else UUID(str(v))

logger = logging.getLogger(__name__)


@dataclass
class InterventionAssessment:
    pending_request_id: str
    was_necessary: bool
    autonomy_alternative: str
    signature: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pending_request_id": self.pending_request_id,
            "was_necessary": self.was_necessary,
            "autonomy_alternative": self.autonomy_alternative,
            "signature": self.signature, "reason": self.reason,
        }


def _signature(form_type: str, sub_type: str | None,
                 service: str, question: str) -> str:
    basis = f"{form_type}|{sub_type or ''}|{service.lower()}|{question[:120].lower()}"
    return hashlib.sha256(basis.encode()).hexdigest()[:40]


def _assess_type_c(
    row: asyncpg.Record, question: str,
) -> tuple[bool, str, str]:
    sub_type = row["c_sub_type"]
    if any(k in (question or "").lower()
           for k in ["daily 02:00", "bcrypt cost 12", "exponential backoff",
                     "jour", "standard", "defaut"]):
        return (False,
                "suggested_answer etait un industry default -> "
                "le systeme aurait pu auto-appliquer",
                "apply_industry_default + monitor_drift")
    if sub_type == "C6":
        return True, "C6 contractuel : legitime", ""
    if row["criticality"] == "low":
        return (False, "criticality=low -> CONSTRAIN mode aurait suffi",
                "CONSTRAIN mode (feature flag)")
    return True, "intervention legitime par defaut", ""


def _assess_type_a(service: str) -> tuple[bool, str, str]:
    from app.autonomy import fallback_chain
    fb = fallback_chain.find(service)
    if not fb.should_still_ask and fb.recommended:
        name = fb.recommended["name"]
        return False, f"fallback {name} disponible", f"use {name}"
    return True, "intervention legitime par defaut", ""


async def assess(
    pool: asyncpg.Pool, pending_request_id: str,
) -> InterventionAssessment | None:
    """Analyse l'intervention et retourne le verdict."""
    try:
        pid = _as_uuid(pending_request_id)
    except (ValueError, AttributeError):
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, form_type, c_sub_type, service_name, question_id,
                   suggested_answer, criticality, fields, created_at,
                   status, task_id
            FROM pending_user_inputs WHERE id = $1
            """, pid,
        )
    if row is None:
        return None

    form_type = row["form_type"] or "C"
    sub_type = row["c_sub_type"]
    service = row["service_name"] or ""
    question = row["suggested_answer"] or row["question_id"] or ""

    if form_type == "C":
        was_necessary, reason, autonomy_alt = _assess_type_c(row, question)
    elif form_type == "A":
        was_necessary, reason, autonomy_alt = _assess_type_a(service)
    else:
        # B : paiement = hard boundary legitime
        was_necessary, reason, autonomy_alt = True, "paiement = hard boundary legitime", ""

    sig = _signature(form_type, sub_type, service, question)
    assessment = InterventionAssessment(
        pending_request_id=str(pid),
        was_necessary=was_necessary,
        autonomy_alternative=autonomy_alt, signature=sig, reason=reason,
    )
    await _persist(pool, row, assessment)
    if not was_necessary:
        await _register_negative(pool, form_type, sub_type, service,
                                   question, autonomy_alt, sig)
    return assessment


async def _persist(
    pool: asyncpg.Pool, row: asyncpg.Record, a: InterventionAssessment,
) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO intervention_outcomes
                  (pending_request_id, form_type, c_sub_type, was_necessary,
                   autonomy_alternative)
                VALUES ($1, $2, $3, $4, $5)
                """,
                _as_uuid(a.pending_request_id), row["form_type"] or "C",
                row["c_sub_type"], a.was_necessary, a.autonomy_alternative,
            )
    except Exception as exc:
        logger.warning("persist intervention_outcome failed: %s", exc)


async def _register_negative(
    pool: asyncpg.Pool, form_type: str, sub_type: str | None,
    service: str, question: str, hint: str, sig: str,
) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO negative_escalation_registry
                  (signature, description, example_request, resolution_hint)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT (signature) DO UPDATE SET
                  occurrences = negative_escalation_registry.occurrences + 1
                """,
                sig,
                f"{form_type}/{sub_type or '-'} sur {service}",
                json.dumps({"form_type": form_type, "sub_type": sub_type,
                             "service": service, "question": question[:300]}),
                hint or "see autonomy_alternative",
            )
    except Exception as exc:
        logger.warning("register negative failed: %s", exc)


async def matches_negative(
    pool: asyncpg.Pool, form_type: str, sub_type: str | None,
    service: str, question: str,
) -> dict[str, Any] | None:
    sig = _signature(form_type, sub_type, service, question)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT description, resolution_hint, occurrences "
            "FROM negative_escalation_registry WHERE signature = $1", sig,
        )
    return dict(row) if row else None


async def learn_from_recent(
    pool: asyncpg.Pool, limit: int = 50,
) -> dict[str, Any]:
    """Traite en batch les interventions traitees pas encore evaluees."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.id FROM pending_user_inputs p
            LEFT JOIN intervention_outcomes o
              ON o.pending_request_id = p.id
            WHERE p.status IN ('answered', 'canceled') AND o.id IS NULL
            ORDER BY p.created_at DESC LIMIT $1
            """, limit,
        )
    assessed, unnecessary = 0, 0
    for r in rows:
        a = await assess(pool, int(r["id"]))
        if a:
            assessed += 1
            if not a.was_necessary:
                unnecessary += 1
    return {"assessed": assessed, "unnecessary": unnecessary,
            "avoidable_rate": round(unnecessary / max(1, assessed), 4)}
