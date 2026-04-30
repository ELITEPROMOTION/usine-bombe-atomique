"""InvoiceGenerator : factures multi-pays multi-langues.

Garanties **non-fonctionnelles** :
- Tokens IA INVISIBLES : la facture ne reference JAMAIS `ai_decisions_log`,
  ni les tokens IA, ni les couts internes par appel LLM. Le client voit
  uniquement le projet, le montant total HT/TVA/TTC. Cf. ADR-19.

Format : HTML simple (string templating). PDF generation (weasyprint) en
phase ulterieure. Locales supportees : en, fr, ar, es.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.billing.types import SUPPORTED_BILLING_LOCALES
from app.saas_factory.billing.vat_rates import VATRate, resolve_vat

logger = logging.getLogger(__name__)


# Strings i18n minimales
_I18N: dict[str, dict[str, str]] = {
    "en": {
        "invoice": "Invoice",
        "invoice_number": "Invoice No.",
        "issued_on": "Issued on",
        "billed_to": "Billed to",
        "country": "Country",
        "description": "Description",
        "amount_ht": "Subtotal (excl. tax)",
        "vat": "VAT",
        "amount_ttc": "Total (incl. tax)",
        "footer": "UBA Studio Platform",
    },
    "fr": {
        "invoice": "Facture",
        "invoice_number": "Facture n°",
        "issued_on": "Emise le",
        "billed_to": "Facture à",
        "country": "Pays",
        "description": "Description",
        "amount_ht": "Sous-total HT",
        "vat": "TVA",
        "amount_ttc": "Total TTC",
        "footer": "UBA Studio Platform",
    },
    "ar": {
        "invoice": "فاتورة",
        "invoice_number": "رقم الفاتورة",
        "issued_on": "صدرت في",
        "billed_to": "فوترة لصالح",
        "country": "الدولة",
        "description": "الوصف",
        "amount_ht": "المجموع الفرعي",
        "vat": "ضريبة القيمة المضافة",
        "amount_ttc": "المجموع الإجمالي",
        "footer": "منصة UBA Studio",
    },
    "es": {
        "invoice": "Factura",
        "invoice_number": "Factura nº",
        "issued_on": "Emitida el",
        "billed_to": "Facturado a",
        "country": "País",
        "description": "Descripción",
        "amount_ht": "Subtotal sin IVA",
        "vat": "IVA",
        "amount_ttc": "Total con IVA",
        "footer": "UBA Studio Platform",
    },
}


@dataclass(frozen=True)
class Invoice:
    invoice_id: UUID
    invoice_number: str
    payment_id: UUID
    project_id: str
    owner_email: str
    country: str
    locale: str
    description: str
    net_amount_cents: int
    vat_pct: float
    vat_amount_cents: int
    gross_amount_cents: int
    currency: str
    vat_label: str
    issued_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


def _format_amount(cents: int, currency: str) -> str:
    return f"{cents / 100:.2f} {currency}"


def _strings(locale: str) -> dict[str, str]:
    if locale not in SUPPORTED_BILLING_LOCALES:
        locale = "en"
    return _I18N[locale]


class InvoiceGenerator:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def _next_invoice_number(now: datetime, seq: int) -> str:
        return f"UBA-{now:%Y%m}-{seq:06d}"

    async def issue_for_payment(
        self,
        *,
        payment_id: UUID,
        description: str = "",
    ) -> Invoice:
        """Cree une invoice depuis un payment SUCCEEDED."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT project_id, amount_cents, currency, owner_email,
                       country, locale, status
                  FROM payments
                 WHERE payment_id = $1
                """,
                payment_id,
            )
            if row is None:
                raise LookupError(f"payment {payment_id} introuvable")
            if row["status"] != "succeeded":
                raise RuntimeError(
                    f"payment {payment_id} pas en status 'succeeded' "
                    f"(actuel: {row['status']})"
                )

            vat: VATRate = resolve_vat(row["country"])
            # `amount_cents` du payment est le TTC charge par Stripe.
            # On reverse-calcule le HT et la TVA depuis le TTC.
            gross = int(row["amount_cents"])
            vat_pct = float(vat.standard_pct)
            net = round(gross / (1.0 + vat_pct / 100.0))
            vat_amount = gross - net

            # Numero de facture : seq global + mois courant
            now = datetime.now(UTC)
            seq_row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(seq_in_month), 0) + 1 AS next_seq
                  FROM invoices
                 WHERE issued_year = $1 AND issued_month = $2
                """,
                now.year, now.month,
            )
            seq = int(seq_row["next_seq"])
            invoice_number = self._next_invoice_number(now, seq)

            ins = await conn.fetchrow(
                """
                INSERT INTO invoices (
                    invoice_number, payment_id, project_id, owner_email,
                    country, locale, description,
                    net_amount_cents, vat_pct, vat_amount_cents,
                    gross_amount_cents, currency, vat_label,
                    seq_in_month, issued_year, issued_month
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7,
                    $8, $9, $10,
                    $11, $12, $13,
                    $14, $15, $16
                ) RETURNING invoice_id, issued_at
                """,
                invoice_number, payment_id, row["project_id"], row["owner_email"],
                row["country"], row["locale"],
                description[:200] or "UBA Studio Project",
                net, vat_pct, vat_amount,
                gross, row["currency"], vat.label,
                seq, now.year, now.month,
            )

        invoice = Invoice(
            invoice_id=ins["invoice_id"],
            invoice_number=invoice_number,
            payment_id=payment_id,
            project_id=row["project_id"],
            owner_email=row["owner_email"],
            country=row["country"],
            locale=row["locale"],
            description=description[:200] or "UBA Studio Project",
            net_amount_cents=net,
            vat_pct=vat_pct,
            vat_amount_cents=vat_amount,
            gross_amount_cents=gross,
            currency=row["currency"],
            vat_label=vat.label,
            issued_at=ins["issued_at"],
        )
        logger.info(
            "invoice.issued number=%s payment=%s amount=%s/%s",
            invoice_number, payment_id,
            _format_amount(gross, row["currency"]),
            row["country"],
        )
        return invoice

    @staticmethod
    def render_html(invoice: Invoice) -> str:
        """Rend une facture en HTML simple. Aucune reference aux tokens IA."""
        s = _strings(invoice.locale)
        rtl = ' dir="rtl"' if invoice.locale == "ar" else ""
        return (
            f'<!DOCTYPE html><html lang="{invoice.locale}"{rtl}>'
            f'<head><meta charset="utf-8"><title>{s["invoice"]} '
            f'{invoice.invoice_number}</title></head><body>'
            f'<h1>{s["invoice"]}</h1>'
            f'<p><strong>{s["invoice_number"]}</strong> '
            f'{invoice.invoice_number}</p>'
            f'<p><strong>{s["issued_on"]}</strong> '
            f'{invoice.issued_at:%Y-%m-%d}</p>'
            f'<hr>'
            f'<h2>{s["billed_to"]}</h2>'
            f'<p>{invoice.owner_email}<br>{s["country"]}: {invoice.country}</p>'
            f'<hr>'
            f'<table><thead><tr><th>{s["description"]}</th>'
            f'<th>{s["amount_ht"]}</th></tr></thead>'
            f'<tbody><tr><td>{invoice.description}</td>'
            f'<td>{_format_amount(invoice.net_amount_cents, invoice.currency)}</td>'
            f'</tr></tbody></table>'
            f'<p><strong>{s["amount_ht"]}:</strong> '
            f'{_format_amount(invoice.net_amount_cents, invoice.currency)}</p>'
            f'<p><strong>{invoice.vat_label} ({invoice.vat_pct}%):</strong> '
            f'{_format_amount(invoice.vat_amount_cents, invoice.currency)}</p>'
            f'<p><strong>{s["amount_ttc"]}:</strong> '
            f'{_format_amount(invoice.gross_amount_cents, invoice.currency)}</p>'
            f'<hr><footer>{s["footer"]}</footer></body></html>'
        )
