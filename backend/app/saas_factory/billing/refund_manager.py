"""RefundManager : refunds partiels ou complets, audit complet."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field

from app.saas_factory.billing.stripe_client import StripeClient
from app.saas_factory.billing.types import PaymentStatus, RefundReason

logger = logging.getLogger(__name__)


class RefundRequest(BaseModel):
    payment_id: UUID
    amount_cents: int | None = Field(default=None, ge=1)  # None = total
    reason: RefundReason
    detail: str = Field(default="", max_length=500)


@dataclass(frozen=True)
class RefundRecord:
    refund_id: UUID
    payment_id: UUID
    amount_cents: int
    reason: RefundReason
    detail: str
    stripe_refund_id: str | None
    requested_at: datetime
    completed_at: datetime | None


class RefundManager:
    def __init__(self, pool: asyncpg.Pool, client: StripeClient | Any) -> None:
        self._pool = pool
        self._client = client

    async def refund(self, req: RefundRequest) -> RefundRecord:
        # 1. Lecture du payment (statut + stripe_payment_intent_id)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT amount_cents, currency, status, stripe_payment_intent_id
                  FROM payments WHERE payment_id = $1
                """,
                req.payment_id,
            )
        if row is None:
            raise LookupError(f"payment {req.payment_id} introuvable")
        if row["status"] not in ("succeeded", "partially_refunded"):
            raise RuntimeError(
                f"payment {req.payment_id} pas refund-able "
                f"(status={row['status']})"
            )
        if not row["stripe_payment_intent_id"]:
            raise RuntimeError(
                f"payment {req.payment_id} sans stripe_payment_intent_id",
            )

        amount = req.amount_cents if req.amount_cents else int(row["amount_cents"])
        if amount > int(row["amount_cents"]):
            raise ValueError(
                f"amount {amount} > total {row['amount_cents']}",
            )

        # 2. Pre-record en DB
        async with self._pool.acquire() as conn:
            ins = await conn.fetchrow(
                """
                INSERT INTO refunds (
                    payment_id, amount_cents, reason, detail
                ) VALUES ($1, $2, $3, $4)
                RETURNING refund_id, requested_at
                """,
                req.payment_id, amount, req.reason.value, req.detail[:500],
            )
            refund_id: UUID = ins["refund_id"]
            requested_at: datetime = ins["requested_at"]

        # 3. Appel Stripe
        try:
            result = await self._client.request(
                "POST", "/refunds",
                form_data={
                    "payment_intent": row["stripe_payment_intent_id"],
                    "amount": amount,
                    "reason": _map_stripe_reason(req.reason),
                    "metadata": {"uba_refund_id": str(refund_id)},
                },
            )
        except Exception as exc:
            await self._mark_failed(refund_id, str(exc)[:500])
            raise

        body = result.json_body
        stripe_refund_id = str(body.get("id") or "")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE refunds
                   SET stripe_refund_id = $2, completed_at = NOW()
                 WHERE refund_id = $1
                """,
                refund_id, stripe_refund_id,
            )
            # MAJ statut payment
            new_status = (
                PaymentStatus.REFUNDED if amount >= int(row["amount_cents"])
                else PaymentStatus.PARTIALLY_REFUNDED
            )
            await conn.execute(
                """
                UPDATE payments SET status = $2, updated_at = NOW()
                 WHERE payment_id = $1
                """,
                req.payment_id, new_status.value,
            )

        logger.info(
            "refund.completed payment=%s amount=%d/%s reason=%s",
            req.payment_id, amount, row["currency"], req.reason.value,
        )
        return RefundRecord(
            refund_id=refund_id,
            payment_id=req.payment_id,
            amount_cents=amount,
            reason=req.reason,
            detail=req.detail,
            stripe_refund_id=stripe_refund_id or None,
            requested_at=requested_at,
            completed_at=datetime.now(UTC),
        )

    async def _mark_failed(self, refund_id: UUID, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE refunds
                   SET completed_at = NULL,
                       detail = detail || ' [FAILED: ' || $2 || ']'
                 WHERE refund_id = $1
                """,
                refund_id, reason[:200],
            )


_STRIPE_REASON_MAP: dict[RefundReason, str] = {
    RefundReason.DUPLICATE_PAYMENT: "duplicate",
    RefundReason.FRAUDULENT: "fraudulent",
    RefundReason.REQUESTED_BY_CUSTOMER: "requested_by_customer",
    RefundReason.SLA_VIOLATION: "requested_by_customer",
    RefundReason.PROJECT_CANCELLED: "requested_by_customer",
    RefundReason.OTHER: "requested_by_customer",
}


def _map_stripe_reason(r: RefundReason) -> str:
    """Map vers les `reason` acceptes par Stripe."""
    return _STRIPE_REASON_MAP.get(r, "requested_by_customer")
