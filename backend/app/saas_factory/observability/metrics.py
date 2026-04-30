"""V9Metrics : Prometheus counters/histograms/gauges pour business KPIs.

Pattern important : la classe accepte un `CollectorRegistry` optionnel.
- Production : registry = None → utilise le `REGISTRY` global Prometheus
- Tests     : registry = CollectorRegistry() local → isolation totale

Cf. ADR-27 pour justification (eviter la pollution du global registry
quand pytest re-importe les modules).
"""
from __future__ import annotations

import logging
from typing import Final

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

logger = logging.getLogger(__name__)


# Buckets en USD pour AI cost — granular pour faible amounts, large pour cas extremes
_AI_COST_BUCKETS_USD: Final[tuple[float, ...]] = (
    0.001, 0.01, 0.05, 0.10, 0.50, 1.00, 5.00, 10.00, 50.00, 100.00,
)
# Buckets en cents pour amounts paiement (1€ - 50k€)
_PAYMENT_BUCKETS_CENTS: Final[tuple[float, ...]] = (
    100, 500, 1000, 5000, 10_000, 50_000, 100_000, 500_000,
    1_000_000, 5_000_000,
)
# Buckets duration handoff resolution en heures (1h - 1 semaine)
_HANDOFF_BUCKETS_HOURS: Final[tuple[float, ...]] = (
    0.5, 1, 2, 6, 12, 24, 48, 72, 168,
)
# Buckets webhook processing en secondes (1ms - 5s)
_WEBHOOK_BUCKETS_S: Final[tuple[float, ...]] = (
    0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0,
)


class V9Metrics:
    """Collection Prometheus pour les KPIs V9.

    Tous les noms metriques ont le prefixe `uba_` pour eviter les
    collisions avec d'autres systemes.
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        # `registry=None` -> Prometheus utilise le default REGISTRY global
        reg = registry if registry is not None else REGISTRY

        # ---- Paywall / billing ----
        self.paywall_triggered = Counter(
            "uba_paywall_triggered_total",
            "Paywall declenche (20% progression atteinte)",
            labelnames=("project_status",),
            registry=reg,
        )
        self.payment_amount_cents = Histogram(
            "uba_payment_amount_cents",
            "Distribution des montants de paiement en cents",
            buckets=_PAYMENT_BUCKETS_CENTS,
            labelnames=("currency", "status"),
            registry=reg,
        )
        self.payment_succeeded = Counter(
            "uba_payment_succeeded_total",
            "Paiements reussis (webhook checkout.session.completed)",
            labelnames=("currency",),
            registry=reg,
        )
        self.payment_failed = Counter(
            "uba_payment_failed_total",
            "Paiements echoues",
            labelnames=("currency", "reason"),
            registry=reg,
        )
        self.refund_amount_cents = Histogram(
            "uba_refund_amount_cents",
            "Distribution des montants de refund en cents",
            buckets=_PAYMENT_BUCKETS_CENTS,
            labelnames=("currency", "reason"),
            registry=reg,
        )

        # ---- AI cost / router ----
        self.ai_cost_per_call_usd = Histogram(
            "uba_ai_cost_per_call_usd",
            "Cout par appel IA en USD (post-router)",
            buckets=_AI_COST_BUCKETS_USD,
            labelnames=("provider", "status"),
            registry=reg,
        )
        self.ai_decisions_total = Counter(
            "uba_ai_decisions_total",
            "Decisions du router IA",
            labelnames=("requested_provider", "actual_provider", "status"),
            registry=reg,
        )
        self.ai_loop_detected = Counter(
            "uba_ai_loop_detected_total",
            "Boucles detectees par le LoopDetector",
            labelnames=("project_id_hash",),     # hash, pas le project_id raw
            registry=reg,
        )
        self.ai_budget_blocked = Counter(
            "uba_ai_budget_blocked_total",
            "Appels bloques par le CostGuard",
            labelnames=("scope",),       # 'per_call' | 'per_project' | 'daily'
            registry=reg,
        )

        # ---- Webhook ----
        self.webhook_processing_duration = Histogram(
            "uba_webhook_processing_duration_seconds",
            "Duree de traitement des webhooks",
            buckets=_WEBHOOK_BUCKETS_S,
            labelnames=("source", "event_type", "status"),
            registry=reg,
        )
        self.webhook_replay_blocked = Counter(
            "uba_webhook_replay_blocked_total",
            "Webhooks bloques pour idempotency hit (replay deja traite)",
            labelnames=("source",),
            registry=reg,
        )

        # ---- Handoff ----
        self.handoff_resolution_duration_hours = Histogram(
            "uba_handoff_resolution_duration_hours",
            "Temps de resolution des handoffs en heures",
            buckets=_HANDOFF_BUCKETS_HOURS,
            labelnames=("action_type",),
            registry=reg,
        )
        self.handoff_escalated = Counter(
            "uba_handoff_escalated_total",
            "Handoffs escaladees (>24h sans resolution)",
            labelnames=("action_type",),
            registry=reg,
        )

        # ---- Active state gauges ----
        self.active_projects = Gauge(
            "uba_active_projects",
            "Nombre de projets actifs (par status)",
            labelnames=("status",),
            registry=reg,
        )
        self.open_handoffs = Gauge(
            "uba_open_handoffs",
            "Nombre de handoffs ouverts (requested/notified/acknowledged/escalated)",
            labelnames=("action_type",),
            registry=reg,
        )
        self.platform_live_modes = Gauge(
            "uba_platform_live_modes",
            "Modes live actives (1) ou pas (0)",
            labelnames=("mode",),       # 'hostinger' | 'stripe' | 'jwt'
            registry=reg,
        )

    # -----------------------------------------------------------------------
    # Helpers d'observation (raccourcis pour les call-sites)
    # -----------------------------------------------------------------------
    def record_payment(
        self, *, amount_cents: int, currency: str, status: str,
    ) -> None:
        self.payment_amount_cents.labels(
            currency=currency.upper(), status=status,
        ).observe(float(amount_cents))
        if status == "succeeded":
            self.payment_succeeded.labels(currency=currency.upper()).inc()

    def record_ai_decision(
        self,
        *,
        requested_provider: str,
        actual_provider: str,
        status: str,
        cost_usd: float,
    ) -> None:
        self.ai_decisions_total.labels(
            requested_provider=requested_provider,
            actual_provider=actual_provider,
            status=status,
        ).inc()
        self.ai_cost_per_call_usd.labels(
            provider=actual_provider, status=status,
        ).observe(max(0.0, cost_usd))

    def record_webhook(
        self, *, source: str, event_type: str, status: str, duration_s: float,
    ) -> None:
        self.webhook_processing_duration.labels(
            source=source, event_type=event_type[:64], status=status,
        ).observe(max(0.0, duration_s))


# ---------------------------------------------------------------------------
# Module-level singleton (lazy init)
# ---------------------------------------------------------------------------
_v9_metrics: V9Metrics | None = None


def get_v9_metrics() -> V9Metrics:
    """Retourne le singleton V9Metrics enregistre dans REGISTRY global."""
    global _v9_metrics
    if _v9_metrics is None:
        _v9_metrics = V9Metrics()
    return _v9_metrics


def reset_v9_metrics_for_test(registry: CollectorRegistry | None = None) -> V9Metrics:
    """Helper de test : reinitialise le singleton avec un registry propre."""
    global _v9_metrics
    _v9_metrics = V9Metrics(registry=registry or CollectorRegistry())
    return _v9_metrics
