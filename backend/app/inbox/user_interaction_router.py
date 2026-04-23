"""V4.8 BLOC 1 - User Interaction Router.

Gate ABSOLU : seules 3 categories d'interactions utilisateur sont
autorisees. Toute tentative d'une autre nature est bloquee, loggee dans
`blocked_user_asks`, et une resolution automatique est proposee.

Categories :
- CASE_A_ACCOUNT       : ouverture de compte tiers (email + password)
- CASE_B_PAYMENT       : paiement abonnement (lien direct)
- CASE_C_CLARIFICATION : question metier / decision

Usage cote agents :
    async def some_agent_step(pool, task_id):
        ok = await user_interaction_router.request_user(
            pool, task_id, InteractionRequest(case=Case.ACCOUNT, ...)
        )
        if not ok.allowed:
            # re-orientation automatique par autonomous_executor
            ...
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class Case(str, Enum):
    ACCOUNT = "A"         # ouverture de compte
    PAYMENT = "B"         # paiement abonnement
    CLARIFICATION = "C"   # question metier


@dataclass
class AccountAsk:
    service_name: str
    why: str                # 1 phrase
    org_optional: bool = False


@dataclass
class PaymentAsk:
    service_name: str
    why: str
    cost_amount: str        # ex: "20.00"
    cost_currency: str      # ex: "USD"
    duration_months: int    # 1, 12, ...
    free_alternative: bool
    payment_url: str        # Stripe / PayPal / billing page


@dataclass
class ClarificationAsk:
    question_id: str        # "Q-001"
    question: str           # texte clair
    why: str                # impact projet
    suggested_answer: str   # proposition systeme
    options: list[str] = field(default_factory=list)
    criticality: str = "medium"


@dataclass
class InteractionRequest:
    case: Case
    task_id: str
    actor: str              # nom du module qui demande
    payload: AccountAsk | PaymentAsk | ClarificationAsk
    context: str = ""       # pourquoi maintenant


@dataclass
class RouterDecision:
    allowed: bool
    case: Case | None
    form_type: str | None       # 'A' | 'B' | 'C'
    pending_request_id: str | None
    reason: str


# ------------------------------------------------------------------ validate

def _validate(req: InteractionRequest) -> str | None:
    """Retourne None si OK, un message d'erreur sinon."""
    if not isinstance(req.case, Case):
        return f"case invalide : {req.case}"
    p = req.payload
    if req.case == Case.ACCOUNT:
        if not isinstance(p, AccountAsk):
            return "case A exige AccountAsk"
        if not p.service_name or not p.why:
            return "case A exige service_name + why"
    elif req.case == Case.PAYMENT:
        if not isinstance(p, PaymentAsk):
            return "case B exige PaymentAsk"
        if not p.payment_url.startswith(("http://", "https://")):
            return "case B exige payment_url valide"
        if not p.cost_amount or not p.cost_currency:
            return "case B exige cost_amount + cost_currency"
    elif req.case == Case.CLARIFICATION:
        if not isinstance(p, ClarificationAsk):
            return "case C exige ClarificationAsk"
        if not p.question_id.startswith("Q-"):
            return "question_id doit commencer par Q-"
        if not p.suggested_answer:
            return ("case C exige une suggested_answer : le systeme doit proposer "
                    "une reponse, pas juste poser une question vide (principe MIT Senior)")
    return None


# ------------------------------------------------------------------ persist

async def request_user(
    pool: asyncpg.Pool, req: InteractionRequest,
) -> RouterDecision:
    """Valide + persiste dans pending_user_inputs avec form_type=A/B/C."""
    err = _validate(req)
    if err:
        await _log_blocked(pool, req, err)
        return RouterDecision(
            allowed=False, case=req.case, form_type=None,
            pending_request_id=None, reason=err,
        )

    # Construit le payload fields selon le case
    fields, request_kind, extras = _build_form(req)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pending_user_inputs
              (task_id, tool_id, request_kind, fields, context, form_type,
               service_name, why, cost_amount, cost_currency, payment_url,
               free_alternative, question_id, suggested_answer, criticality)
            VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            RETURNING id
            """,
            UUID(req.task_id),
            extras.get("tool_id"),
            request_kind,
            json.dumps(fields),
            req.context or extras.get("why", ""),
            req.case.value,
            extras.get("service_name"), extras.get("why"),
            extras.get("cost_amount"), extras.get("cost_currency"),
            extras.get("payment_url"), extras.get("free_alternative"),
            extras.get("question_id"), extras.get("suggested_answer"),
            extras.get("criticality", "medium"),
        )
    return RouterDecision(
        allowed=True, case=req.case, form_type=req.case.value,
        pending_request_id=str(row["id"]),
        reason=f"demande {req.case.value} acceptee",
    )


def _build_form(req: InteractionRequest) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Retourne (fields, request_kind, extras) selon le case."""
    p = req.payload
    if req.case == Case.ACCOUNT and isinstance(p, AccountAsk):
        fields = [
            {"id": "email",    "label": "Email a utiliser",
             "type": "email", "required": True},
            {"id": "password", "label": "Mot de passe a utiliser",
             "type": "password", "required": True, "mask": True},
        ]
        if p.org_optional:
            fields.append({"id": "organization",
                           "label": "Nom organisation (optionnel)",
                           "type": "text", "required": False})
        extras = {
            "tool_id": p.service_name.lower().replace(" ", "_"),
            "service_name": p.service_name, "why": p.why,
        }
        return fields, "email", extras

    if req.case == Case.PAYMENT and isinstance(p, PaymentAsk):
        fields = [
            {"id": "payment_confirmation",
             "label": f"Payer {p.cost_amount} {p.cost_currency} / {p.duration_months} mois",
             "type": "url", "required": False,
             "prefilled": p.payment_url},
            {"id": "payment_status", "label": "Statut apres paiement",
             "type": "select",
             "options": ["Paye OK", "Echec", "Abandon"],
             "required": True},
        ]
        extras = {
            "tool_id": p.service_name.lower().replace(" ", "_"),
            "service_name": p.service_name, "why": p.why,
            "cost_amount": p.cost_amount, "cost_currency": p.cost_currency,
            "payment_url": p.payment_url,
            "free_alternative": p.free_alternative,
        }
        return fields, "payment", extras

    # CLARIFICATION (C)
    assert isinstance(p, ClarificationAsk)
    fields = [
        {"id": "suggested_acceptance",
         "label": f"Valider la suggestion du systeme ? ({p.suggested_answer})",
         "type": "select",
         "options": ["Oui, accepter la suggestion", "Non, autre reponse ci-dessous"],
         "required": True},
    ]
    if p.options:
        fields.append({"id": "option_choice", "label": "Options",
                       "type": "select", "options": p.options, "required": False})
    fields.append({"id": "free_answer", "label": "Autre reponse (optionnel)",
                   "type": "text", "required": False})
    fields.append({"id": "attachment", "label": "Piece jointe (optionnel)",
                   "type": "file", "required": False})
    extras = {
        "question_id": p.question_id,
        "suggested_answer": p.suggested_answer,
        "why": p.why, "criticality": p.criticality,
    }
    return fields, "custom", extras


async def _log_blocked(
    pool: asyncpg.Pool, req: InteractionRequest, reason: str,
) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO blocked_user_asks
                  (task_id, actor, rejected_request, reason)
                VALUES ($1, $2, $3::jsonb, $4)
                """,
                UUID(req.task_id) if req.task_id else None, req.actor,
                json.dumps({"case": getattr(req.case, "value", None),
                             "payload_type": type(req.payload).__name__}),
                reason,
            )
    except Exception as exc:
        logger.warning("log_blocked failed: %s", exc)


# ------------------------------------------------------------------ enforce

async def enforce_no_stray_asks(
    pool: asyncpg.Pool, task_id: str, request_kind: str, actor: str = "unknown",
) -> bool:
    """Gate d'urgence : refuse tout request_kind != A/B/C deguise.

    Retourne True si accepte (A/B/C classifiable), False sinon (bloquer + log).
    """
    allowed_kinds = {"email", "password", "payment", "custom"}
    if request_kind not in allowed_kinds:
        await _log_blocked(pool, InteractionRequest(
            case=Case.CLARIFICATION, task_id=task_id, actor=actor,
            payload=ClarificationAsk(question_id="Q-BLOCKED",
                                      question=f"Request_kind interdit : {request_kind}",
                                      why="doctrine V4.8", suggested_answer="resoudre_auto"),
        ), f"request_kind '{request_kind}' hors categories A/B/C")
        return False
    return True
