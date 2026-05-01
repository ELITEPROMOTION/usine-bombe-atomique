"""Tests Phase 9H — Billing + Stripe.

AUCUN appel Stripe reel emis. Stub client + signature verifiee via HMAC
manuel. Tests offline complets.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.saas_factory.billing.checkout import (
    CheckoutManager,
    CheckoutSessionRequest,
)
from app.saas_factory.billing.invoice_generator import (
    Invoice,
    InvoiceGenerator,
    _format_amount,
    _strings,
)
from app.saas_factory.billing.paywall_trigger import (
    PaywallNotReadyError,
    PaywallTrigger,
)
from app.saas_factory.billing.refund_manager import (
    RefundManager,
    RefundRecord,
    RefundRequest,
    _map_stripe_reason,
)
from app.saas_factory.billing.stripe_client import (
    LIVE_GATE_ENV,
    StripeAPIError,
    StripeClient,
    StripeLiveDisabledError,
    StripeSignatureError,
    StubStripeClient,
    _flatten_form,
    is_live_enabled,
    verify_webhook_signature,
)
from app.saas_factory.billing.types import (
    SUPPORTED_BILLING_LOCALES,
    PaymentStatus,
    RefundReason,
)
from app.saas_factory.billing.vat_rates import (
    DEFAULT_VAT_PCT,
    VAT_TABLE,
    resolve_vat,
)
from app.saas_factory.billing.webhook_handler import (
    WebhookAlreadyProcessed,
    WebhookHandler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    return pool, conn


def _signed_webhook(
    payload: str, secret: str = "whsec_test", timestamp: int | None = None,
) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    sig = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={sig}"


# ===========================================================================
# VAT rates
# ===========================================================================
class TestVATRates:
    def test_table_has_50_plus_countries(self) -> None:
        assert len(VAT_TABLE) >= 50

    def test_eu_27_present(self) -> None:
        eu = {"AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR",
              "HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK",
              "SI","ES","SE"}
        assert eu <= set(VAT_TABLE)

    def test_maghreb_present(self) -> None:
        assert {"DZ", "MA", "TN"} <= set(VAT_TABLE)

    def test_resolve_known_country(self) -> None:
        assert resolve_vat("FR").standard_pct == 20.0
        assert resolve_vat("DZ").label == "TVA"
        assert resolve_vat("DE").standard_pct == 19.0

    def test_resolve_unknown_country_fallback(self) -> None:
        r = resolve_vat("XX")
        assert r.standard_pct == DEFAULT_VAT_PCT
        assert r.label == "VAT"

    def test_resolve_lowercase_normalized(self) -> None:
        r = resolve_vat("fr")
        assert r.country == "FR"

    def test_resolve_empty(self) -> None:
        r = resolve_vat("")
        assert r.standard_pct == DEFAULT_VAT_PCT


# ===========================================================================
# Stripe client : gate, signature
# ===========================================================================
class TestStripeClient:
    def test_construction(self) -> None:
        c = StripeClient()
        assert c.name == "stripe"

    def test_is_live_enabled_default_false(self, monkeypatch) -> None:
        monkeypatch.delenv(LIVE_GATE_ENV, raising=False)
        assert is_live_enabled() is False

    def test_is_live_enabled_true(self, monkeypatch) -> None:
        monkeypatch.setenv(LIVE_GATE_ENV, "1")
        assert is_live_enabled() is True

    @pytest.mark.asyncio
    async def test_request_blocks_when_live_disabled(self, monkeypatch) -> None:
        monkeypatch.delenv(LIVE_GATE_ENV, raising=False)
        c = StripeClient()
        with pytest.raises(StripeLiveDisabledError):
            await c.request("POST", "/checkout/sessions", form_data={})

    def test_headers_raises_without_api_key(self, monkeypatch) -> None:
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        c = StripeClient()
        with pytest.raises(StripeAPIError, match="STRIPE_API_KEY"):
            c._headers()

    def test_headers_present_with_api_key(self, monkeypatch) -> None:
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_1234")
        c = StripeClient()
        h = c._headers()
        assert h["Authorization"] == "Bearer sk_test_1234"
        assert "Stripe-Version" in h


class TestSignatureVerification:
    def test_valid_signature_passes(self) -> None:
        payload = '{"id":"evt_1","type":"checkout.session.completed"}'
        secret = "whsec_xyz"
        ts = int(time.time())
        sig = hmac.new(
            secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256,
        ).hexdigest()
        verify_webhook_signature(
            payload=payload,
            signature_header=f"t={ts},v1={sig}",
            webhook_secret=secret,
        )

    def test_missing_header_raises(self) -> None:
        with pytest.raises(StripeSignatureError, match="manquant"):
            verify_webhook_signature(
                payload="{}", signature_header="", webhook_secret="s",
            )

    def test_empty_secret_raises(self) -> None:
        with pytest.raises(StripeSignatureError, match="webhook_secret"):
            verify_webhook_signature(
                payload="{}", signature_header="t=1,v1=abc",
                webhook_secret="",
            )

    def test_missing_timestamp_raises(self) -> None:
        with pytest.raises(StripeSignatureError, match="timestamp"):
            verify_webhook_signature(
                payload="{}", signature_header="v1=abc",
                webhook_secret="s",
            )

    def test_non_int_timestamp_raises(self) -> None:
        with pytest.raises(StripeSignatureError, match="entier"):
            verify_webhook_signature(
                payload="{}", signature_header="t=notint,v1=abc",
                webhook_secret="s",
            )

    def test_old_timestamp_raises(self) -> None:
        old_ts = int(time.time()) - 10000   # > 5min
        sig = "x" * 64
        with pytest.raises(StripeSignatureError, match="tolerance"):
            verify_webhook_signature(
                payload="{}",
                signature_header=f"t={old_ts},v1={sig}",
                webhook_secret="s",
            )

    def test_no_v1_signature_raises(self) -> None:
        ts = int(time.time())
        with pytest.raises(StripeSignatureError, match="v1"):
            verify_webhook_signature(
                payload="{}", signature_header=f"t={ts}",
                webhook_secret="s",
            )

    def test_wrong_signature_raises(self) -> None:
        payload = '{"x":1}'
        ts = int(time.time())
        with pytest.raises(StripeSignatureError, match="match"):
            verify_webhook_signature(
                payload=payload,
                signature_header=f"t={ts},v1=ffffff",
                webhook_secret="s",
            )

    def test_multiple_v1_signatures_one_matches(self) -> None:
        """Stripe envoie parfois plusieurs v1 (rotation)."""
        payload = '{"x":1}'
        secret = "whsec"
        ts = int(time.time())
        good_sig = hmac.new(
            secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256,
        ).hexdigest()
        verify_webhook_signature(
            payload=payload,
            signature_header=f"t={ts},v1=deadbeef,v1={good_sig}",
            webhook_secret=secret,
        )


class TestFormFlattening:
    def test_simple(self) -> None:
        out = _flatten_form({"a": 1, "b": "x"})
        assert ("a", "1") in out
        assert ("b", "x") in out

    def test_nested(self) -> None:
        out = dict(_flatten_form({"line_items": {"qty": 2}}))
        assert "line_items[qty]" in out

    def test_list_of_dicts(self) -> None:
        out = dict(_flatten_form({
            "line_items": [{"qty": 1}, {"qty": 2}],
        }))
        assert out["line_items[0][qty]"] == "1"
        assert out["line_items[1][qty]"] == "2"

    def test_bool_serialized(self) -> None:
        out = dict(_flatten_form({"flag": True, "no": False}))
        assert out["flag"] == "true"
        assert out["no"] == "false"

    def test_none_skipped(self) -> None:
        out = dict(_flatten_form({"a": None, "b": 1}))
        assert "a" not in out


# ===========================================================================
# CheckoutManager
# ===========================================================================
class TestCheckoutManager:
    @pytest.mark.asyncio
    async def test_create_session_succeeds(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {"payment_id": new_id, "created_at": now}
        client = StubStripeClient()
        client.set_response(
            "POST", "/checkout/sessions",
            json_body={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/cs_test_1"},
        )
        cm = CheckoutManager(pool, client)
        req = CheckoutSessionRequest(
            project_id="p1", amount_cents=100_00, currency="EUR",
            owner_email="x@y.com", country="FR", locale="fr",
            success_url="https://app.uba.studio/ok",
            cancel_url="https://app.uba.studio/cancel",
            description="Test project",
        )
        session = await cm.create_session(req)
        assert session.payment_id == new_id
        assert session.stripe_session_id == "cs_test_1"
        assert session.checkout_url and "checkout.stripe.com" in session.checkout_url

    @pytest.mark.asyncio
    async def test_create_session_failure_marks_failed(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "payment_id": uuid4(), "created_at": datetime.now(UTC),
        }
        client = StubStripeClient()      # no canned -> raises
        cm = CheckoutManager(pool, client)
        req = CheckoutSessionRequest(
            project_id="p1", amount_cents=10000, currency="EUR",
            owner_email="x@y.com", country="FR", locale="fr",
            success_url="https://x/ok", cancel_url="https://x/no",
        )
        with pytest.raises(StripeAPIError):
            await cm.create_session(req)
        executes = [c.args[0] for c in conn.execute.await_args_list]
        assert any("status = 'failed'" in s for s in executes)

    def test_invalid_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutSessionRequest(
                project_id="p", amount_cents=1000, currency="eur",  # lowercase
                owner_email="x@y.com", country="FR", locale="fr",
                success_url="https://x", cancel_url="https://x",
            )

    def test_amount_too_small_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutSessionRequest(
                project_id="p", amount_cents=50,        # < 100
                currency="EUR", owner_email="x@y.com",
                country="FR", locale="fr",
                success_url="https://x", cancel_url="https://x",
            )

    def test_country_must_be_2_uppercase(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutSessionRequest(
                project_id="p", amount_cents=1000, currency="EUR",
                owner_email="x@y.com", country="fr",   # lowercase
                locale="fr",
                success_url="https://x", cancel_url="https://x",
            )


# ===========================================================================
# WebhookHandler
# ===========================================================================
class TestWebhookHandler:
    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self) -> None:
        pool, _ = _mock_pool()
        h = WebhookHandler(pool, webhook_secret="whsec_x")
        with pytest.raises(StripeSignatureError):
            await h.process(
                raw_payload='{"id":"evt_1"}',
                signature_header="t=1,v1=bad",
            )

    @pytest.mark.asyncio
    async def test_checkout_completed_marks_paid_and_calls_resume(self) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        uba_payment = uuid4()
        payload = json.dumps({
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_1",
                "payment_intent": "pi_1",
                "amount_total": 10000,
                "currency": "eur",
                "metadata": {
                    "uba_payment_id": str(uba_payment),
                    "uba_project_id": "proj-X",
                },
            }},
        })
        # 1ere fetchrow : INSERT webhook_events RETURNING (idempotency ok)
        conn.fetchrow.return_value = {"event_db_id": uuid4()}

        called: list = []

        async def resume(pid, proj, amt, cur):
            called.append((pid, proj, amt, cur))

        h = WebhookHandler(
            pool, webhook_secret=secret, project_resume=resume,
        )
        sig = _signed_webhook(payload, secret)
        evt = await h.process(raw_payload=payload, signature_header=sig)
        assert evt.payment_id == uba_payment
        assert called == [(uba_payment, "proj-X", 10000, "EUR")]
        # UPDATE payments status='succeeded'
        executes = [c.args[0] for c in conn.execute.await_args_list]
        assert any("status = 'succeeded'" in s for s in executes)

    @pytest.mark.asyncio
    async def test_idempotent_replay_raises_already_processed(self) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        payload = json.dumps({"id": "evt_dup", "type": "checkout.session.completed",
                              "data": {"object": {"metadata": {}}}})
        # ON CONFLICT DO NOTHING -> RETURNING None
        conn.fetchrow.return_value = None
        h = WebhookHandler(pool, webhook_secret=secret)
        sig = _signed_webhook(payload, secret)
        with pytest.raises(WebhookAlreadyProcessed):
            await h.process(raw_payload=payload, signature_header=sig)

    @pytest.mark.asyncio
    async def test_checkout_completed_without_uba_payment_id_logs_warning(
        self, caplog,
    ) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        conn.fetchrow.return_value = {"event_db_id": uuid4()}
        payload = json.dumps({
            "id": "evt_no_meta", "type": "checkout.session.completed",
            "data": {"object": {"metadata": {}, "amount_total": 5000}},
        })
        h = WebhookHandler(pool, webhook_secret=secret)
        with caplog.at_level("WARNING"):
            evt = await h.process(
                raw_payload=payload,
                signature_header=_signed_webhook(payload, secret),
            )
        assert evt.payment_id is None

    @pytest.mark.asyncio
    async def test_payment_intent_failed(self) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        conn.fetchrow.return_value = {"event_db_id": uuid4()}
        uba_payment = uuid4()
        payload = json.dumps({
            "id": "evt_failed", "type": "payment_intent.payment_failed",
            "data": {"object": {"metadata": {"uba_payment_id": str(uba_payment)}}},
        })
        h = WebhookHandler(pool, webhook_secret=secret)
        evt = await h.process(
            raw_payload=payload, signature_header=_signed_webhook(payload, secret),
        )
        assert evt.payment_id == uba_payment
        executes = [c.args[0] for c in conn.execute.await_args_list]
        assert any("status = $2" in s for s in executes)

    @pytest.mark.asyncio
    async def test_charge_refunded_full(self) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        # 1er fetchrow : INSERT webhook (RETURNING)
        # 2eme fetchrow : UPDATE payments WHERE stripe_payment_intent_id RETURNING
        uba_payment = uuid4()
        conn.fetchrow.side_effect = [
            {"event_db_id": uuid4()},
            {"payment_id": uba_payment},
        ]
        payload = json.dumps({
            "id": "evt_refund", "type": "charge.refunded",
            "data": {"object": {
                "payment_intent": "pi_xyz",
                "amount_refunded": 10000, "amount_captured": 10000,
            }},
        })
        h = WebhookHandler(pool, webhook_secret=secret)
        evt = await h.process(
            raw_payload=payload, signature_header=_signed_webhook(payload, secret),
        )
        assert evt.payment_id == uba_payment

    @pytest.mark.asyncio
    async def test_unhandled_event_type_returns_event_with_no_payment(
        self, caplog,
    ) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        conn.fetchrow.return_value = {"event_db_id": uuid4()}
        payload = json.dumps({
            "id": "evt_other", "type": "customer.created",
            "data": {"object": {}},
        })
        h = WebhookHandler(pool, webhook_secret=secret)
        evt = await h.process(
            raw_payload=payload, signature_header=_signed_webhook(payload, secret),
        )
        assert evt.payment_id is None
        assert evt.event_type == "customer.created"

    @pytest.mark.asyncio
    async def test_resume_callback_exception_does_not_break_webhook(self) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        conn.fetchrow.return_value = {"event_db_id": uuid4()}
        uba_payment = uuid4()
        payload = json.dumps({
            "id": "evt_x", "type": "checkout.session.completed",
            "data": {"object": {
                "metadata": {"uba_payment_id": str(uba_payment),
                             "uba_project_id": "p"},
                "amount_total": 1000, "currency": "eur",
            }},
        })

        async def bad(*a):
            raise RuntimeError("boom")

        h = WebhookHandler(pool, webhook_secret=secret, project_resume=bad)
        evt = await h.process(
            raw_payload=payload, signature_header=_signed_webhook(payload, secret),
        )
        # Le webhook n'a pas plante malgre le callback en erreur
        assert evt.payment_id == uba_payment

    @pytest.mark.asyncio
    async def test_invalid_uba_payment_id_uuid(self) -> None:
        pool, conn = _mock_pool()
        secret = "whsec_test"
        conn.fetchrow.return_value = {"event_db_id": uuid4()}
        payload = json.dumps({
            "id": "evt_bad_uuid", "type": "checkout.session.completed",
            "data": {"object": {"metadata": {"uba_payment_id": "not-a-uuid"}}},
        })
        h = WebhookHandler(pool, webhook_secret=secret)
        evt = await h.process(
            raw_payload=payload, signature_header=_signed_webhook(payload, secret),
        )
        assert evt.payment_id is None


# ===========================================================================
# InvoiceGenerator (TOKEN IA INVISIBLE — non-leak)
# ===========================================================================
class TestInvoiceGenerator:
    @pytest.mark.asyncio
    async def test_issue_for_payment_succeeds(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        pid = uuid4()
        now = datetime.now(UTC)
        conn.fetchrow.side_effect = [
            # 1. SELECT payments
            {
                "project_id": "p1", "amount_cents": 12000,
                "currency": "EUR", "owner_email": "x@y.com",
                "country": "FR", "locale": "fr", "status": "succeeded",
            },
            # 2. SELECT MAX seq
            {"next_seq": 1},
            # 3. INSERT invoices RETURNING
            {"invoice_id": new_id, "issued_at": now},
        ]
        gen = InvoiceGenerator(pool)
        inv = await gen.issue_for_payment(payment_id=pid, description="Pack saas")
        assert inv.invoice_number.startswith("UBA-")
        assert inv.gross_amount_cents == 12000
        # FR -> 20% TVA -> 12000 = 10000 net + 2000 vat
        assert inv.net_amount_cents == 10000
        assert inv.vat_amount_cents == 2000
        assert inv.vat_label == "TVA"

    @pytest.mark.asyncio
    async def test_issue_unknown_payment_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        gen = InvoiceGenerator(pool)
        with pytest.raises(LookupError):
            await gen.issue_for_payment(payment_id=uuid4())

    @pytest.mark.asyncio
    async def test_issue_payment_not_succeeded_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": "p", "amount_cents": 1000, "currency": "EUR",
            "owner_email": "x@y.com", "country": "FR", "locale": "fr",
            "status": "pending",
        }
        gen = InvoiceGenerator(pool)
        with pytest.raises(RuntimeError, match="succeeded"):
            await gen.issue_for_payment(payment_id=uuid4())

    def test_render_html_locales(self) -> None:
        invoice = Invoice(
            invoice_id=uuid4(),
            invoice_number="UBA-202604-000001",
            payment_id=uuid4(),
            project_id="p1",
            owner_email="x@y.com",
            country="FR",
            locale="fr",
            description="Pack saas_small",
            net_amount_cents=10000,
            vat_pct=20.0,
            vat_amount_cents=2000,
            gross_amount_cents=12000,
            currency="EUR",
            vat_label="TVA",
            issued_at=datetime.now(UTC),
        )
        html = InvoiceGenerator.render_html(invoice)
        assert "UBA-202604-000001" in html
        assert "Facture" in html  # locale FR
        assert "TVA" in html
        assert "100.00 EUR" in html
        assert "120.00 EUR" in html

    def test_render_html_arabic_rtl(self) -> None:
        invoice = Invoice(
            invoice_id=uuid4(), invoice_number="UBA-202604-000002",
            payment_id=uuid4(), project_id="p", owner_email="x@y.com",
            country="DZ", locale="ar", description="Pack",
            net_amount_cents=8403, vat_pct=19.0, vat_amount_cents=1597,
            gross_amount_cents=10000, currency="DZD", vat_label="TVA",
            issued_at=datetime.now(UTC),
        )
        html = InvoiceGenerator.render_html(invoice)
        assert 'dir="rtl"' in html
        assert "فاتورة" in html

    def test_render_html_unknown_locale_falls_back_to_en(self) -> None:
        invoice = Invoice(
            invoice_id=uuid4(), invoice_number="UBA-202604-000003",
            payment_id=uuid4(), project_id="p", owner_email="x@y.com",
            country="US", locale="zz",  # unknown
            description="Pack", net_amount_cents=10000, vat_pct=0,
            vat_amount_cents=0, gross_amount_cents=10000, currency="USD",
            vat_label="Sales tax", issued_at=datetime.now(UTC),
        )
        html = InvoiceGenerator.render_html(invoice)
        assert "Invoice" in html  # fallback en

    def test_render_html_does_not_leak_ai_metadata(self) -> None:
        """ADR-19 : tokens IA INVISIBLES — l'invoice ne reference jamais
        ai_decisions_log, tokens_in/out, cost_usd, provider, etc.
        """
        invoice = Invoice(
            invoice_id=uuid4(), invoice_number="UBA-X",
            payment_id=uuid4(), project_id="p",
            owner_email="x@y.com", country="FR", locale="fr",
            description="Pack saas", net_amount_cents=10000,
            vat_pct=20.0, vat_amount_cents=2000, gross_amount_cents=12000,
            currency="EUR", vat_label="TVA",
            issued_at=datetime.now(UTC),
            metadata={
                # Meme si l'invoice metadata contient ces valeurs (ne devrait
                # pas en production), le rendu HTML ne les surface pas.
                "ai_decisions": [{"provider": "claude", "cost_usd": 0.05}],
                "tokens_in": 1000, "tokens_out": 500,
            },
        )
        html = InvoiceGenerator.render_html(invoice)
        forbidden_terms = (
            "claude", "perplexity", "manus", "ai_decisions", "tokens_in",
            "tokens_out", "cost_usd", "provider", "anthropic",
        )
        for term in forbidden_terms:
            assert term.lower() not in html.lower(), (
                f"LEAK : terme interdit '{term}' dans l'HTML invoice"
            )

    def test_format_amount_helper(self) -> None:
        assert _format_amount(10000, "EUR") == "100.00 EUR"
        assert _format_amount(0, "USD") == "0.00 USD"
        assert _format_amount(9999, "DZD") == "99.99 DZD"

    def test_strings_helper(self) -> None:
        assert _strings("fr")["invoice"] == "Facture"
        assert _strings("zz")["invoice"] == "Invoice"  # fallback en

    def test_invoice_number_format(self) -> None:
        n = InvoiceGenerator._next_invoice_number(
            datetime(2026, 4, 30, tzinfo=UTC), 42,
        )
        assert n == "UBA-202604-000042"


# ===========================================================================
# RefundManager
# ===========================================================================
class TestRefundManager:
    @pytest.mark.asyncio
    async def test_refund_succeeds(self) -> None:
        pool, conn = _mock_pool()
        ref_id = uuid4()
        # 1. SELECT payment
        # 2. INSERT refund RETURNING
        conn.fetchrow.side_effect = [
            {
                "amount_cents": 10000, "currency": "EUR",
                "status": "succeeded",
                "stripe_payment_intent_id": "pi_xyz",
            },
            {"refund_id": ref_id, "requested_at": datetime.now(UTC)},
        ]
        client = StubStripeClient()
        client.set_response(
            "POST", "/refunds",
            json_body={"id": "re_test_1"},
        )
        rm = RefundManager(pool, client)
        rec = await rm.refund(RefundRequest(
            payment_id=uuid4(), reason=RefundReason.SLA_VIOLATION,
            detail="SLA missed",
        ))
        assert isinstance(rec, RefundRecord)
        assert rec.amount_cents == 10000  # full refund (req.amount_cents=None)
        assert rec.stripe_refund_id == "re_test_1"

    @pytest.mark.asyncio
    async def test_refund_partial(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            {
                "amount_cents": 10000, "currency": "EUR",
                "status": "succeeded",
                "stripe_payment_intent_id": "pi_xyz",
            },
            {"refund_id": uuid4(), "requested_at": datetime.now(UTC)},
        ]
        client = StubStripeClient()
        client.set_response(
            "POST", "/refunds", json_body={"id": "re_partial"},
        )
        rm = RefundManager(pool, client)
        rec = await rm.refund(RefundRequest(
            payment_id=uuid4(), amount_cents=4000,
            reason=RefundReason.OTHER, detail="partial",
        ))
        assert rec.amount_cents == 4000

    @pytest.mark.asyncio
    async def test_refund_unknown_payment_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        rm = RefundManager(pool, StubStripeClient())
        with pytest.raises(LookupError):
            await rm.refund(RefundRequest(
                payment_id=uuid4(),
                reason=RefundReason.OTHER,
            ))

    @pytest.mark.asyncio
    async def test_refund_payment_not_refundable_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "amount_cents": 1000, "currency": "EUR",
            "status": "pending", "stripe_payment_intent_id": None,
        }
        rm = RefundManager(pool, StubStripeClient())
        with pytest.raises(RuntimeError, match="refund-able"):
            await rm.refund(RefundRequest(
                payment_id=uuid4(), reason=RefundReason.OTHER,
            ))

    @pytest.mark.asyncio
    async def test_refund_missing_payment_intent_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "amount_cents": 1000, "currency": "EUR",
            "status": "succeeded", "stripe_payment_intent_id": None,
        }
        rm = RefundManager(pool, StubStripeClient())
        with pytest.raises(RuntimeError, match="stripe_payment_intent_id"):
            await rm.refund(RefundRequest(
                payment_id=uuid4(), reason=RefundReason.OTHER,
            ))

    @pytest.mark.asyncio
    async def test_refund_amount_exceeds_payment_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "amount_cents": 1000, "currency": "EUR",
            "status": "succeeded", "stripe_payment_intent_id": "pi_x",
        }
        rm = RefundManager(pool, StubStripeClient())
        with pytest.raises(ValueError, match=">"):
            await rm.refund(RefundRequest(
                payment_id=uuid4(), amount_cents=99999,
                reason=RefundReason.OTHER,
            ))

    def test_map_stripe_reason(self) -> None:
        assert _map_stripe_reason(RefundReason.DUPLICATE_PAYMENT) == "duplicate"
        assert _map_stripe_reason(RefundReason.FRAUDULENT) == "fraudulent"
        assert _map_stripe_reason(RefundReason.SLA_VIOLATION) == "requested_by_customer"


# ===========================================================================
# PaywallTrigger
# ===========================================================================
class TestPaywallTrigger:
    @pytest.mark.asyncio
    async def test_trigger_succeeds(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            # paywall_triggered_at present
            {"triggered_at": datetime.now(UTC)},
            # project row
            {"pid": "proj-uuid", "owner_email": "x@y.com",
             "country": "FR", "locale": "fr", "currency": "EUR"},
            # pricing row
            {"gross_price": 12000.00, "currency": "EUR"},
            # existing payment? -> None
            None,
            # pour create_session : INSERT payments RETURNING
            {"payment_id": uuid4(), "created_at": datetime.now(UTC)},
        ]
        client = StubStripeClient()
        client.set_response(
            "POST", "/checkout/sessions",
            json_body={"id": "cs_p1", "url": "https://checkout.stripe.com/cs_p1"},
        )
        cm = CheckoutManager(pool, client)
        pt = PaywallTrigger(pool, cm)
        result = await pt.maybe_trigger("proj-uuid")
        assert result is not None
        assert result.stripe_session_id == "cs_p1"

    @pytest.mark.asyncio
    async def test_paywall_not_triggered_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"triggered_at": None}
        client = StubStripeClient()
        cm = CheckoutManager(pool, client)
        pt = PaywallTrigger(pool, cm)
        with pytest.raises(PaywallNotReadyError, match="paywall pas encore"):
            await pt.maybe_trigger("p1")

    @pytest.mark.asyncio
    async def test_project_missing_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            {"triggered_at": datetime.now(UTC)},
            None,   # project row
        ]
        cm = CheckoutManager(pool, StubStripeClient())
        pt = PaywallTrigger(pool, cm)
        with pytest.raises(PaywallNotReadyError, match="introuvable"):
            await pt.maybe_trigger("p-ghost")

    @pytest.mark.asyncio
    async def test_no_pricing_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            {"triggered_at": datetime.now(UTC)},
            {"pid": "p", "owner_email": "x@y.com",
             "country": "FR", "locale": "fr", "currency": "EUR"},
            None,   # pricing
        ]
        cm = CheckoutManager(pool, StubStripeClient())
        pt = PaywallTrigger(pool, cm)
        with pytest.raises(PaywallNotReadyError, match="pricing"):
            await pt.maybe_trigger("p")

    @pytest.mark.asyncio
    async def test_zero_price_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            {"triggered_at": datetime.now(UTC)},
            {"pid": "p", "owner_email": "x@y.com",
             "country": "FR", "locale": "fr", "currency": "EUR"},
            {"gross_price": 0.0, "currency": "EUR"},
        ]
        cm = CheckoutManager(pool, StubStripeClient())
        pt = PaywallTrigger(pool, cm)
        with pytest.raises(PaywallNotReadyError, match="manual_quote"):
            await pt.maybe_trigger("p")

    @pytest.mark.asyncio
    async def test_existing_payment_returns_none(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            {"triggered_at": datetime.now(UTC)},
            {"pid": "p", "owner_email": "x@y.com",
             "country": "FR", "locale": "fr", "currency": "EUR"},
            {"gross_price": 100.0, "currency": "EUR"},
            {"1": 1},   # payment existant
        ]
        cm = CheckoutManager(pool, StubStripeClient())
        pt = PaywallTrigger(pool, cm)
        result = await pt.maybe_trigger("p")
        assert result is None


# ===========================================================================
# Types
# ===========================================================================
def test_payment_status_enum() -> None:
    assert PaymentStatus.SUCCEEDED.value == "succeeded"
    assert PaymentStatus.PARTIALLY_REFUNDED.value == "partially_refunded"


def test_supported_locales() -> None:
    assert "en" in SUPPORTED_BILLING_LOCALES
    assert "fr" in SUPPORTED_BILLING_LOCALES
    assert "ar" in SUPPORTED_BILLING_LOCALES
    assert "es" in SUPPORTED_BILLING_LOCALES


def test_refund_reason_enum() -> None:
    assert RefundReason.SLA_VIOLATION.value == "sla_violation"
