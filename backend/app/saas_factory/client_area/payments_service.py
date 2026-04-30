"""ClientPaymentsService : invoices + handoffs (lecture seule).

Sources :
- `invoices` (V9H migration 038)
- `handoff_requests` (V9A migration 046) — `target_email = client.owner_email`
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClientInvoiceRow:
    invoice_id: UUID
    number: str
    amount_cents: int
    currency: str
    status: str               # 'draft'|'issued'|'paid'|'refunded'
    issued_at: datetime
    paid_at: datetime | None
    pdf_token: str            # invoice_id en str pour route /pdf


@dataclass(frozen=True)
class ClientHandoffRow:
    id: UUID
    action_type: str
    title: str
    description: str
    due_at: datetime
    status: str
    cta_label: str
    cta_url: str


class ClientPaymentsService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_invoices(self, project_id: UUID) -> list[ClientInvoiceRow]:
        """Toutes les factures du projet, du plus recent au plus ancien."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.invoice_id, i.invoice_number, i.gross_amount_cents,
                       i.currency, i.issued_at, p.status AS payment_status,
                       p.paid_at
                  FROM invoices i
                  JOIN payments p ON p.payment_id = i.payment_id
                 WHERE i.project_id = $1
                 ORDER BY i.issued_at DESC
                """,
                str(project_id),
            )
        out: list[ClientInvoiceRow] = []
        for r in rows:
            out.append(ClientInvoiceRow(
                invoice_id=r["invoice_id"],
                number=r["invoice_number"],
                amount_cents=int(r["gross_amount_cents"]),
                currency=r["currency"],
                status=_invoice_ui_status(
                    r["payment_status"], r["paid_at"],
                ),
                issued_at=r["issued_at"],
                paid_at=r["paid_at"],
                pdf_token=str(r["invoice_id"]),
            ))
        return out

    async def list_handoffs(
        self, project_id: UUID,
    ) -> list[ClientHandoffRow]:
        """Handoffs du projet, ouverts ou recents (max 10)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT handoff_id, action_type, state, title, body,
                       cta_url, expires_at, created_at
                  FROM handoff_requests
                 WHERE project_id = $1
                 ORDER BY
                   CASE WHEN state IN ('requested','notified','acknowledged')
                        THEN 0 ELSE 1 END,
                   created_at DESC
                 LIMIT 10
                """,
                str(project_id),
            )
        out: list[ClientHandoffRow] = []
        for r in rows:
            cta_label = _cta_label_for(r["action_type"])
            out.append(ClientHandoffRow(
                id=r["handoff_id"],
                action_type=r["action_type"],
                title=r["title"],
                description=r["body"],
                due_at=r["expires_at"],
                status=r["state"],
                cta_label=cta_label,
                cta_url=r["cta_url"],
            ))
        return out


def _invoice_ui_status(payment_status: str, paid_at: datetime | None) -> str:
    """Mapping payment.status -> UI invoice status."""
    if payment_status == "succeeded" and paid_at is not None:
        return "paid"
    if payment_status in {"refunded", "partially_refunded"}:
        return "refunded"
    if payment_status == "pending":
        return "issued"
    if payment_status == "failed":
        return "issued"     # client peut re-payer
    return "draft"


def _cta_label_for(action_type: str) -> str:
    return {
        "payment_confirm":  "Confirmer le paiement",
        "mandate_sign":     "Signer le mandat",
        "review_approve":   "Ouvrir la revue",
    }.get(action_type, "Voir l'action")
