"""Module E : orchestrateur des handoffs KYC / carte / etapes manuelles.

Quand le pipeline atteint un service tier 2 ou 3, il doit demander une
intervention humaine breve (carte de paiement, KYC business). Cet orchestrateur :

- genere un magic-link cryptographiquement aleatoire
- prepare un payload de mail multilingue (templates EN/FR, sans envoi reel
  dans la phase 9-BOOT)
- planifie la cadence de relance : 1h -> 12h -> 24h -> escalation Slack
- pause/resume du pipeline encode dans la table `handoff_pending`

L'envoi reel via Resend / Slack est branchable plus tard via `EmailSender`
et `SlackEscalation` (DI : on ne fait que stub ici).
"""
from __future__ import annotations

import enum
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class HandoffType(str, enum.Enum):
    KYC = "kyc"
    CARD = "card"
    MANUAL_STEP = "manual_step"


class HandoffStatus(str, enum.Enum):
    PENDING = "pending"
    REMINDED_1H = "reminded_1h"
    REMINDED_12H = "reminded_12h"
    REMINDED_24H = "reminded_24h"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    EXPIRED = "expired"


REMINDER_SCHEDULE: tuple[tuple[timedelta, HandoffStatus], ...] = (
    (timedelta(hours=1), HandoffStatus.REMINDED_1H),
    (timedelta(hours=12), HandoffStatus.REMINDED_12H),
    (timedelta(hours=24), HandoffStatus.REMINDED_24H),
)
ESCALATION_AFTER = timedelta(hours=24)
DEFAULT_EXPIRY = timedelta(days=3)


# Templates minimalistes — la version finale sera composee par un Template
# Engine dans Phase 9I (legal-multi-langue). Ici on garde du texte neutre.
TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "kyc": {
        "en": {
            "subject": "[UBA Studio] Action required: complete KYC ({service})",
            "body": (
                "Hello,\n\nTo continue activating {service} on your behalf, "
                "please complete the KYC step here:\n\n  {magic_link}\n\n"
                "This link expires on {expires_at} (UTC). It should take less "
                "than 5 minutes.\n\n— UBA Studio Platform"
            ),
        },
        "fr": {
            "subject": "[UBA Studio] Action requise : valider votre KYC ({service})",
            "body": (
                "Bonjour,\n\nPour finaliser l'activation de {service} en votre "
                "nom, merci de completer le KYC ici :\n\n  {magic_link}\n\n"
                "Ce lien expire le {expires_at} (UTC). Comptez moins de "
                "5 minutes.\n\n— UBA Studio Platform"
            ),
        },
    },
    "card": {
        "en": {
            "subject": "[UBA Studio] Action required: add a payment card ({service})",
            "body": (
                "Hello,\n\nTo activate {service}, please add a payment card "
                "via:\n\n  {magic_link}\n\nNo amount is charged at this step.\n\n"
                "Expires on {expires_at} (UTC).\n\n— UBA Studio Platform"
            ),
        },
        "fr": {
            "subject": "[UBA Studio] Action requise : ajout carte ({service})",
            "body": (
                "Bonjour,\n\nPour activer {service}, ajoutez une carte de "
                "paiement via :\n\n  {magic_link}\n\nAucun montant n'est "
                "preleve a cette etape.\nExpiration : {expires_at} (UTC).\n\n"
                "— UBA Studio Platform"
            ),
        },
    },
    "manual_step": {
        "en": {
            "subject": "[UBA Studio] Manual step needed ({service})",
            "body": (
                "Hello,\n\nA short manual step is required for {service}:\n\n  "
                "{magic_link}\n\nDetails inside. Expires {expires_at} (UTC).\n\n"
                "— UBA Studio Platform"
            ),
        },
        "fr": {
            "subject": "[UBA Studio] Etape manuelle requise ({service})",
            "body": (
                "Bonjour,\n\nUne etape manuelle est requise pour {service} :\n\n"
                "  {magic_link}\n\nDetails dans le lien. Expire le {expires_at} "
                "(UTC).\n\n— UBA Studio Platform"
            ),
        },
    },
}


@dataclass
class HandoffEnvelope:
    handoff_id: UUID
    type: HandoffType
    target_email: str
    magic_link: str
    subject: str
    body: str
    locale: str
    expires_at: datetime


class EmailSender(Protocol):
    """Implemente par un adapteur Resend dans une phase ulterieure."""

    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class SlackEscalation(Protocol):
    async def escalate(self, *, message: str, handoff_id: UUID) -> None: ...


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _build_magic_link(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/handoff/{token}"


class HandoffKycOrchestrator:
    """Cree, suit et relance les handoffs. Pas d'envoi reel sans `email_sender`."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        base_url: str = "https://app.uba.studio",
        email_sender: EmailSender | None = None,
        slack: SlackEscalation | None = None,
        clock: Any = None,
    ) -> None:
        self._pool = pool
        self._base_url = base_url
        self._email = email_sender
        self._slack = slack
        self._clock = clock or (lambda: datetime.now(UTC))

    async def open_handoff(
        self,
        *,
        handoff_type: HandoffType,
        target_email: str,
        service: str,
        locale: str = "en",
        instructions: dict[str, Any] | None = None,
        expires_in: timedelta = DEFAULT_EXPIRY,
    ) -> HandoffEnvelope:
        if locale not in {"en", "fr"}:
            locale = "en"

        token = _new_token()
        magic = _build_magic_link(self._base_url, token)
        expires_at = self._clock() + expires_in
        tpl = TEMPLATES[handoff_type.value][locale]
        subject = tpl["subject"].format(service=service)
        body = tpl["body"].format(
            service=service,
            magic_link=magic,
            expires_at=expires_at.strftime("%Y-%m-%d %H:%M"),
        )

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO handoff_pending (
                    handoff_type, target_email, magic_link_token,
                    instructions_json, locale, status, expires_at
                ) VALUES ($1, $2, $3, $4::jsonb, $5, 'pending', $6)
                RETURNING handoff_id
                """,
                handoff_type.value,
                target_email,
                token,
                _canon_instructions(instructions, service),
                locale,
                expires_at,
            )

        envelope = HandoffEnvelope(
            handoff_id=row["handoff_id"],
            type=handoff_type,
            target_email=target_email,
            magic_link=magic,
            subject=subject,
            body=body,
            locale=locale,
            expires_at=expires_at,
        )

        if self._email is not None:
            await self._email.send(to=target_email, subject=subject, body=body)
        else:
            logger.info(
                "handoff.opened type=%s id=%s email_sender=stub",
                handoff_type.value, envelope.handoff_id,
            )

        return envelope

    async def resolve(self, token: str) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE handoff_pending
                   SET status = 'resolved', resolved_at = NOW()
                 WHERE magic_link_token = $1 AND status NOT IN ('resolved','expired')
                RETURNING handoff_id
                """,
                token,
            )
        if row:
            logger.info("handoff.resolved id=%s", row["handoff_id"])
            return True
        return False

    async def tick(self) -> dict[str, int]:
        """Une iteration de surveillance. A appeler periodiquement (cron / Arq).

        Retourne un compteur des transitions effectuees.
        """
        now = self._clock()
        sent_reminders = 0
        escalated = 0
        expired = 0

        async with self._pool.acquire() as conn:
            # 1) reminders selon le schedule
            for delta, status in REMINDER_SCHEDULE:
                rows = await conn.fetch(
                    """
                    UPDATE handoff_pending
                       SET status = $1
                     WHERE status = (
                            CASE $1
                                WHEN 'reminded_1h'  THEN 'pending'
                                WHEN 'reminded_12h' THEN 'reminded_1h'
                                WHEN 'reminded_24h' THEN 'reminded_12h'
                            END
                        )
                       AND created_at <= $2
                       AND expires_at > $3
                    RETURNING handoff_id, target_email, locale, magic_link_token
                    """,
                    status.value,
                    now - delta,
                    now,
                )
                sent_reminders += len(rows)
                for r in rows:
                    if self._email is not None:
                        magic = _build_magic_link(self._base_url, r["magic_link_token"])
                        await self._email.send(
                            to=r["target_email"],
                            subject=f"[UBA Studio] Reminder ({status.value})",
                            body=f"Lien : {magic}",
                        )

            # 2) escalation Slack apres 24h sans resolution
            rows = await conn.fetch(
                """
                UPDATE handoff_pending
                   SET status = 'escalated'
                 WHERE status = 'reminded_24h'
                   AND created_at <= $1
                   AND expires_at > $2
                RETURNING handoff_id, target_email
                """,
                now - ESCALATION_AFTER,
                now,
            )
            escalated = len(rows)
            for r in rows:
                if self._slack is not None:
                    await self._slack.escalate(
                        message=f"Handoff stuck >24h (target={r['target_email']})",
                        handoff_id=r["handoff_id"],
                    )

            # 3) expiration apres `expires_at`
            rows = await conn.fetch(
                """
                UPDATE handoff_pending
                   SET status = 'expired'
                 WHERE status NOT IN ('resolved','expired')
                   AND expires_at <= $1
                RETURNING handoff_id
                """,
                now,
            )
            expired = len(rows)

        return {
            "reminders_sent": sent_reminders,
            "escalated": escalated,
            "expired": expired,
        }


def _canon_instructions(d: dict[str, Any] | None, service: str) -> str:
    import json
    payload = {"service": service, **(d or {})}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
