"""V4.8 BLOC 1 - Forms Generator strict : 3 formulaires exclusifs A/B/C.

Renvoie des dictionnaires prets pour le frontend /ahmed_inbox. Aucune
variation hors des 3 templates :
- A : Ouverture de compte [Service]
- B : Paiement abonnement [Service]
- C : Clarification necessaire
"""
from __future__ import annotations

from typing import Any

from app.inbox.user_interaction_router import (
    AccountAsk,
    Case,
    ClarificationAsk,
    InteractionRequest,
    PaymentAsk,
)


def form_account(ask: AccountAsk) -> dict[str, Any]:
    return {
        "type": Case.ACCOUNT.value,
        "title": f"Ouverture de compte {ask.service_name}",
        "why": ask.why,
        "fields": [
            {"id": "email", "label": "Email a utiliser", "type": "email",
             "required": True, "placeholder": "vous@exemple.com"},
            {"id": "password", "label": "Mot de passe a utiliser",
             "type": "password", "required": True, "mask": True},
        ] + ([{"id": "organization", "label": "Nom organisation (optionnel)",
               "type": "text", "required": False}] if ask.org_optional else []),
        "instruction": (
            "Remplissez et validez. Le systeme se connectera automatiquement, "
            "configurera tout, recuperera les cles API et continuera."
        ),
    }


def form_payment(ask: PaymentAsk) -> dict[str, Any]:
    return {
        "type": Case.PAYMENT.value,
        "title": f"Paiement abonnement {ask.service_name}",
        "why": ask.why,
        "cost": f"{ask.cost_amount} {ask.cost_currency}",
        "duration_months": ask.duration_months,
        "free_alternative": ask.free_alternative,
        "payment_url": ask.payment_url,
        "fields": [
            {"id": "payment_status", "label": "Statut apres paiement",
             "type": "select",
             "options": ["Paye OK", "Echec", "Abandon"], "required": True},
        ],
        "instruction": (
            "Cliquez sur le lien, payez avec votre carte, appuyez OK quand "
            "c'est fait. Le systeme detecte l'activation et continue."
        ),
    }


def form_clarification(ask: ClarificationAsk) -> dict[str, Any]:
    return {
        "type": Case.CLARIFICATION.value,
        "title": "Clarification necessaire",
        "question_id": ask.question_id,
        "question": ask.question,
        "why": ask.why,
        "suggested_answer": ask.suggested_answer,
        "options": ask.options,
        "criticality": ask.criticality,
        "fields": [
            {"id": "suggested_acceptance",
             "label": f"Valider la suggestion ? ({ask.suggested_answer})",
             "type": "select",
             "options": ["Oui, accepter", "Non, autre reponse"],
             "required": True},
            {"id": "free_answer", "label": "Autre reponse (optionnel)",
             "type": "text", "required": False},
            {"id": "attachment", "label": "Piece jointe (optionnel)",
             "type": "file", "required": False},
        ],
        "instruction": "Repondez brievement et validez.",
    }


def render(req: InteractionRequest) -> dict[str, Any]:
    """Dispatch selon le case. Jamais de fallback : si inconnu => erreur."""
    if req.case == Case.ACCOUNT and isinstance(req.payload, AccountAsk):
        return form_account(req.payload)
    if req.case == Case.PAYMENT and isinstance(req.payload, PaymentAsk):
        return form_payment(req.payload)
    if req.case == Case.CLARIFICATION and isinstance(req.payload, ClarificationAsk):
        return form_clarification(req.payload)
    raise ValueError(f"mismatch case/payload : case={req.case}, "
                      f"payload={type(req.payload).__name__}")
