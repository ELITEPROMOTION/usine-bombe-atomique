"""Types Pydantic / dataclasses pour Phase 9H billing."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from uuid import UUID

SUPPORTED_BILLING_LOCALES: Final[tuple[str, ...]] = ("en", "fr", "ar", "es")


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"           # checkout cree, pas encore paye
    SUCCEEDED = "succeeded"       # webhook checkout.session.completed valide
    FAILED = "failed"             # webhook payment_intent.failed
    REFUNDED = "refunded"         # refund total
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"       # session expirée ou annulée client


class RefundReason(str, enum.Enum):
    SLA_VIOLATION = "sla_violation"
    DUPLICATE_PAYMENT = "duplicate_payment"
    REQUESTED_BY_CUSTOMER = "requested_by_customer"
    FRAUDULENT = "fraudulent"
    PROJECT_CANCELLED = "project_cancelled"
    OTHER = "other"


@dataclass(frozen=True)
class PaymentRecord:
    payment_id: UUID
    project_id: str
    stripe_session_id: str | None
    stripe_payment_intent_id: str | None
    amount_cents: int
    currency: str
    status: PaymentStatus
    owner_email: str
    country: str
    locale: str
    created_at: datetime
    paid_at: datetime | None
    metadata: dict[str, Any] = field(default_factory=dict)
