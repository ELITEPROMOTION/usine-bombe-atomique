"""Phase 9H : Billing + Stripe Checkout (1-shot, pas abonnement).

7 composants :
- types               : DTOs Pydantic (PaymentRecord, InvoiceData, ...)
- vat_rates           : 50+ pays mappes a leur TVA (helper resolve_vat)
- stripe_client       : httpx wrapper + StubStripeClient + UBA_LIVE_STRIPE gate
- checkout            : create_session (gated), persiste payments
- webhook_handler     : signature verif + idempotency + project resume callback
- invoice_generator   : multi-pays multi-langues, tokens IA INVISIBLES
- refund_manager      : refund partiel/complet avec audit
- paywall_trigger     : wire 20% progression -> checkout

Comme 9G : `_do_call` Stripe est marque pragma:no-cover, tests offline.
La bascule live necessite UBA_LIVE_STRIPE=1 + GO Ahmed (cf. ADR-18 9G).
"""
from app.saas_factory.billing.checkout import (
    CheckoutManager,
    CheckoutSession,
)
from app.saas_factory.billing.invoice_generator import (
    Invoice,
    InvoiceGenerator,
)
from app.saas_factory.billing.paywall_trigger import (
    PaywallNotReadyError,
    PaywallTrigger,
)
from app.saas_factory.billing.refund_manager import (
    RefundManager,
    RefundRequest,
)
from app.saas_factory.billing.stripe_client import (
    StripeAPIError,
    StripeClient,
    StripeLiveDisabledError,
    StripeSignatureError,
    StubStripeClient,
)
from app.saas_factory.billing.types import (
    SUPPORTED_BILLING_LOCALES,
    PaymentRecord,
    PaymentStatus,
)
from app.saas_factory.billing.vat_rates import (
    VAT_TABLE,
    VATRate,
    resolve_vat,
)
from app.saas_factory.billing.webhook_handler import (
    StripeEvent,
    WebhookAlreadyProcessed,
    WebhookHandler,
)

__all__ = [
    "CheckoutManager",
    "CheckoutSession",
    "Invoice",
    "InvoiceGenerator",
    "PaymentRecord",
    "PaymentStatus",
    "PaywallNotReadyError",
    "PaywallTrigger",
    "RefundManager",
    "RefundRequest",
    "SUPPORTED_BILLING_LOCALES",
    "StripeAPIError",
    "StripeClient",
    "StripeEvent",
    "StripeLiveDisabledError",
    "StripeSignatureError",
    "StubStripeClient",
    "VAT_TABLE",
    "VATRate",
    "WebhookAlreadyProcessed",
    "WebhookHandler",
    "resolve_vat",
]
