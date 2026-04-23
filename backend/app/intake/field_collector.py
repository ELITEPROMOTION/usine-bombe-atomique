"""Upgrade 11 - Moteur de champs a remplir : blocs structures (email/OTP/carte/cle API).

Quand le systeme a besoin d'une information SENSIBLE fournie par l'utilisateur
(et qu'il ne peut pas inventer), il genere un bloc FieldRequest structure :
- request_kind : email | password | otp | captcha | payment | api_key | custom | two_factor
- fields       : liste de Field {id, label, type, required, placeholder, example, mask}
- context      : explication, lien direct, duree d'expiration

L'UI affiche ces champs ; l'API persiste la soumission ; le systeme continue
automatiquement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FieldType = Literal["text", "password", "email", "number", "url", "otp", "file", "select"]


@dataclass
class Field:
    id: str
    label: str
    type: FieldType = "text"
    required: bool = True
    placeholder: str = ""
    example: str = ""
    mask: bool = False
    prefilled: str = ""
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "type": self.type,
            "required": self.required, "placeholder": self.placeholder,
            "example": self.example, "mask": self.mask,
            "prefilled": self.prefilled, "options": self.options,
        }


@dataclass
class FieldRequest:
    request_kind: str
    fields: list[Field] = field(default_factory=list)
    context: str = ""
    action_url: str | None = None
    expires_in_minutes: int = 60
    screenshot_b64: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "context": self.context,
            "action_url": self.action_url,
            "expires_in_minutes": self.expires_in_minutes,
            "screenshot_b64": self.screenshot_b64[:64] + "..." if self.screenshot_b64 else None,
            "fields": [f.to_dict() for f in self.fields],
        }


def ask_email(prefilled: str = "") -> FieldRequest:
    return FieldRequest(
        request_kind="email",
        fields=[Field(id="email", label="Adresse email",
                       type="email", required=True,
                       placeholder="vous@exemple.com", prefilled=prefilled)],
        context="Adresse utilisee pour creer un compte sur l'outil externe.",
    )


def ask_password(label: str = "Mot de passe (pour le nouvel outil)") -> FieldRequest:
    return FieldRequest(
        request_kind="password",
        fields=[Field(id="password", label=label, type="password",
                       required=True, mask=True,
                       example="Au moins 12 caracteres, 1 majuscule, 1 chiffre")],
        context="Choisissez un mot de passe fort, jamais utilise ailleurs. "
                "Sera stocke chiffre dans Vault des reception.",
    )


def ask_otp(delivery_channel: str = "email") -> FieldRequest:
    return FieldRequest(
        request_kind="otp",
        fields=[Field(id="otp", label=f"Code OTP recu par {delivery_channel}",
                       type="otp", required=True, placeholder="123456",
                       example="6 chiffres")],
        context=(f"Un code a ete envoye via {delivery_channel}. Saisissez-le "
                  "dans les 10 minutes."),
        expires_in_minutes=10,
    )


def ask_captcha(image_b64: str, action_url: str | None = None) -> FieldRequest:
    return FieldRequest(
        request_kind="captcha",
        fields=[Field(id="captcha_solution", label="Solution du CAPTCHA",
                       type="text", required=True,
                       placeholder="Tapez le texte / les caracteres de l'image")],
        context="CAPTCHA requis pour continuer l'automatisation. Screenshot ci-dessous.",
        action_url=action_url, screenshot_b64=image_b64,
        expires_in_minutes=10,
    )


def ask_payment(amount: str, currency: str = "EUR",
                 action_url: str | None = None) -> FieldRequest:
    return FieldRequest(
        request_kind="payment",
        fields=[Field(id="payment_confirmation",
                       label=f"Cliquez sur le bouton pour payer {amount} {currency}",
                       type="url", required=False, prefilled=action_url or ""),
                Field(id="payment_status", label="Statut final (OK / Echec / Abandon)",
                       type="select", options=["OK", "Echec", "Abandon"],
                       required=True)],
        context=(f"Paiement de {amount} {currency} requis pour provisionner l'outil. "
                 "Nous ne manipulons JAMAIS votre numero de carte : "
                 "cliquez sur le lien, payez sur le site officiel, puis revenez "
                 "confirmer le statut ici."),
        action_url=action_url,
    )


def ask_api_key(tool_name: str) -> FieldRequest:
    return FieldRequest(
        request_kind="api_key",
        fields=[Field(id="api_key", label=f"Cle API {tool_name}",
                       type="password", required=True, mask=True,
                       placeholder=f"Cle obtenue depuis le dashboard {tool_name}")],
        context=(f"Apres creation du compte sur {tool_name}, generez une cle API "
                  "avec les permissions minimales. La cle sera stockee dans Vault."),
    )


def ask_custom(question: str, field_id: str,
                field_type: FieldType = "text") -> FieldRequest:
    return FieldRequest(
        request_kind="custom",
        fields=[Field(id=field_id, label=question, type=field_type, required=True)],
        context="Question specifique generee par l'agent.",
    )
