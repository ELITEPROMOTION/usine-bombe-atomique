"""CheckoutManager : cree une session Stripe Checkout (1-shot).

Persiste la creation dans `payments` AVANT l'appel Stripe (status=pending).
Apres reponse Stripe, met a jour `stripe_session_id` + `checkout_url`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel, EmailStr, Field

from app.saas_factory.billing.stripe_client import StripeClient
from app.saas_factory.billing.types import PaymentStatus
from app.saas_factory.billing.vat_rates import resolve_vat

logger = logging.getLogger(__name__)


class CheckoutSessionRequest(BaseModel):
    project_id: str = Field(min_length=1)
    amount_cents: int = Field(ge=100, le=10_000_000)   # 1€ min, 100k€ max
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    owner_email: EmailStr
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    locale: str = Field(min_length=2, max_length=5)
    success_url: str = Field(pattern=r"^https://[^\s]+$")
    cancel_url: str = Field(pattern=r"^https://[^\s]+$")
    description: str = Field(max_length=200, default="")


@dataclass(frozen=True)
class CheckoutSession:
    payment_id: UUID
    project_id: str
    stripe_session_id: str | None
    checkout_url: str | None
    amount_cents: int
    currency: str
    status: PaymentStatus
    created_at: datetime


class CheckoutManager:
    def __init__(self, pool: asyncpg.Pool, client: StripeClient | Any) -> None:
        self._pool = pool
        self._client = client

    async def create_session(self, req: CheckoutSessionRequest) -> CheckoutSession:
        # 1. Persiste pre-call (status=pending)
        meta = {
            "vat_country": req.country,
            "locale": req.locale,
            "vat_rate": resolve_vat(req.country).standard_pct,
        }
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO payments (
                    project_id, amount_cents, currency, status,
                    owner_email, country, locale, metadata_json
                ) VALUES (
                    $1, $2, $3, 'pending', $4, $5, $6, $7::jsonb
                ) RETURNING payment_id, created_at
                """,
                req.project_id, req.amount_cents, req.currency.upper(),
                req.owner_email, req.country, req.locale,
                json.dumps(meta, sort_keys=True, ensure_ascii=False, default=str),
            )
            payment_id: UUID = row["payment_id"]
            created_at: datetime = row["created_at"]

        # 2. Stripe Checkout Session creation
        try:
            result = await self._client.request(
                "POST", "/checkout/sessions",
                form_data={
                    "mode": "payment",      # 1-shot, pas subscription
                    "line_items": [{
                        "price_data": {
                            "currency": req.currency.lower(),
                            "product_data": {
                                "name": req.description or "UBA Studio Project",
                            },
                            "unit_amount": req.amount_cents,
                        },
                        "quantity": 1,
                    }],
                    "success_url": req.success_url,
                    "cancel_url": req.cancel_url,
                    "customer_email": req.owner_email,
                    "metadata": {
                        "uba_payment_id": str(payment_id),
                        "uba_project_id": req.project_id,
                    },
                    "locale": "auto",
                    "billing_address_collection": "required",
                },
            )
        except Exception as exc:
            await self._mark_failed(payment_id, str(exc)[:500])
            raise

        body = result.json_body
        session_id = body.get("id")
        checkout_url = body.get("url")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE payments
                   SET stripe_session_id = $2,
                       metadata_json = metadata_json
                                       || jsonb_build_object('checkout_url', $3::text),
                       updated_at = NOW()
                 WHERE payment_id = $1
                """,
                payment_id, session_id, checkout_url or "",
            )

        logger.info(
            "checkout.session_created project=%s payment=%s session=%s",
            req.project_id, payment_id, session_id,
        )
        return CheckoutSession(
            payment_id=payment_id,
            project_id=req.project_id,
            stripe_session_id=session_id,
            checkout_url=checkout_url,
            amount_cents=req.amount_cents,
            currency=req.currency.upper(),
            status=PaymentStatus.PENDING,
            created_at=created_at,
        )

    async def _mark_failed(self, payment_id: UUID, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE payments
                   SET status = 'failed', updated_at = NOW(),
                       metadata_json = metadata_json
                                        || jsonb_build_object('error', $2::text)
                 WHERE payment_id = $1
                """,
                payment_id, reason,
            )
