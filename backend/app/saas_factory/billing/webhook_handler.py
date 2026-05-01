"""WebhookHandler Stripe : signature verif + idempotency + project resume.

Flow standard d'un webhook Stripe :
1. Stripe POST /webhooks/stripe avec body raw + header Stripe-Signature
2. On verifie la signature (HMAC SHA-256, timestamp tolerance 5min)
3. On insere `webhook_events` avec idempotency_key=event.id (UNIQUE)
   - Si UNIQUE violation -> on retourne 200 OK sans rejouer (idempotent)
4. On dispatch sur event.type :
   - 'checkout.session.completed' -> payment.status = succeeded + callback project resume
   - 'payment_intent.payment_failed' -> payment.status = failed
   - 'charge.refunded' -> payment.status = refunded (ou partially_refunded)

Le callback `project_resume_callback` est injecte (Protocol). Default :
no-op safe pour les tests.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.billing.stripe_client import (
    StripeSignatureError,
    verify_webhook_signature,
)
from app.saas_factory.billing.types import PaymentStatus

logger = logging.getLogger(__name__)


# Callback type : reçoit (payment_id, project_id, amount_cents, currency)
ProjectResumeCallback = Callable[[UUID, str, int, str], Awaitable[None]]


async def _noop_resume(*_args: Any, **_kwargs: Any) -> None:
    return None


class WebhookAlreadyProcessed(Exception):
    """Levee quand l'event Stripe a deja ete traite (idempotency hit)."""

    def __init__(self, event_id: str) -> None:
        super().__init__(f"webhook event {event_id} deja traite")
        self.event_id = event_id


@dataclass(frozen=True)
class StripeEvent:
    event_id: str
    event_type: str
    data: dict[str, Any]
    received_at: datetime
    payment_id: UUID | None = None    # rempli si l'event est rattache a un payment


@dataclass(frozen=True)
class WebhookHandlerConfig:
    webhook_secret: str
    tolerance_s: int = 300


class WebhookHandler:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        webhook_secret: str,
        project_resume: ProjectResumeCallback | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._pool = pool
        self._webhook_secret = webhook_secret
        self._resume: ProjectResumeCallback = project_resume or _noop_resume
        self._clock = clock      # None = time.time() default dans verify_webhook_signature

    async def process(
        self,
        *,
        raw_payload: str,
        signature_header: str,
    ) -> StripeEvent:
        # 1. Verif signature (peut lever StripeSignatureError)
        verify_webhook_signature(
            payload=raw_payload,
            signature_header=signature_header,
            webhook_secret=self._webhook_secret,
            now=self._clock() if self._clock else None,
        )

        # 2. Parse JSON
        try:
            event = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise StripeSignatureError(
                f"payload non-JSON: {exc}",
            ) from exc

        event_id = str(event.get("id") or "")
        event_type = str(event.get("type") or "")
        if not event_id or not event_type:
            raise StripeSignatureError(
                "event.id ou event.type manquant",
            )

        # 3. Insertion idempotente : ON CONFLICT DO NOTHING
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO webhook_events (
                    idempotency_key, source, event_type,
                    signature_verified, payload_json
                ) VALUES ($1, 'stripe', $2, TRUE, $3::jsonb)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING event_db_id
                """,
                event_id, event_type[:64],
                json.dumps(event, sort_keys=True, ensure_ascii=False, default=str),
            )
        if row is None:
            raise WebhookAlreadyProcessed(event_id)

        received_at = datetime.now(UTC)

        # 4. Dispatch
        payment_id = await self._dispatch(event_id=event_id, event_type=event_type, event=event)

        # 5. Marque processed_at
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE webhook_events
                   SET processed_at = NOW(),
                       payment_id = $2
                 WHERE idempotency_key = $1
                """,
                event_id, payment_id,
            )

        logger.info(
            "stripe_webhook processed event_id=%s type=%s payment=%s",
            event_id, event_type, payment_id,
        )
        return StripeEvent(
            event_id=event_id, event_type=event_type,
            data=event.get("data", {}) or {}, received_at=received_at,
            payment_id=payment_id,
        )

    async def _dispatch(
        self,
        *,
        event_id: str,
        event_type: str,
        event: dict[str, Any],
    ) -> UUID | None:
        obj = ((event.get("data") or {}).get("object") or {})
        meta = obj.get("metadata") or {}
        uba_payment_id_str = meta.get("uba_payment_id")
        try:
            uba_payment_id = UUID(uba_payment_id_str) if uba_payment_id_str else None
        except (ValueError, TypeError):
            uba_payment_id = None

        if event_type == "checkout.session.completed":
            if uba_payment_id is None:
                logger.warning(
                    "checkout.session.completed sans uba_payment_id (event=%s)",
                    event_id,
                )
                return None
            await self._mark_paid(
                payment_id=uba_payment_id,
                stripe_payment_intent_id=str(obj.get("payment_intent") or "") or None,
                stripe_session_id=str(obj.get("id") or ""),
            )
            # Trigger project resume
            project_id = str(meta.get("uba_project_id") or "")
            amount_cents = int(obj.get("amount_total") or 0)
            currency = str(obj.get("currency") or "").upper()
            try:
                await self._resume(uba_payment_id, project_id, amount_cents, currency)
            except Exception as exc:
                logger.exception("project_resume callback failed: %s", exc)
            return uba_payment_id

        if event_type == "payment_intent.payment_failed":
            if uba_payment_id is None:
                return None
            await self._mark_status(uba_payment_id, PaymentStatus.FAILED)
            return uba_payment_id

        if event_type == "charge.refunded":
            # On lit le payment_intent et on retrouve le payment via stripe_payment_intent_id
            pi_id = str(obj.get("payment_intent") or "")
            if not pi_id:
                return None
            pid = await self._mark_refunded_by_pi(pi_id, obj)
            return pid

        # Type non-gere : on log et on retourne None
        logger.info("stripe_webhook event_type ignored: %s", event_type)
        return None

    async def _mark_paid(
        self,
        *,
        payment_id: UUID,
        stripe_payment_intent_id: str | None,
        stripe_session_id: str | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE payments
                   SET status = 'succeeded', paid_at = NOW(),
                       stripe_payment_intent_id = COALESCE($2, stripe_payment_intent_id),
                       stripe_session_id = COALESCE($3, stripe_session_id),
                       updated_at = NOW()
                 WHERE payment_id = $1 AND status IN ('pending', 'failed')
                """,
                payment_id, stripe_payment_intent_id, stripe_session_id,
            )

    async def _mark_status(
        self, payment_id: UUID, status: PaymentStatus,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE payments
                   SET status = $2, updated_at = NOW()
                 WHERE payment_id = $1
                """,
                payment_id, status.value,
            )

    async def _mark_refunded_by_pi(
        self, pi_id: str, charge_obj: dict[str, Any],
    ) -> UUID | None:
        amount_refunded = int(charge_obj.get("amount_refunded") or 0)
        amount_total = int(charge_obj.get("amount_captured") or charge_obj.get("amount") or 0)
        new_status = (
            PaymentStatus.REFUNDED if amount_refunded >= amount_total
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE payments
                   SET status = $2, updated_at = NOW()
                 WHERE stripe_payment_intent_id = $1
                RETURNING payment_id
                """,
                pi_id, new_status.value,
            )
        return row["payment_id"] if row else None
