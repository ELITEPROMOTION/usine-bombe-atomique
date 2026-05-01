"""Phase 9K : Observabilité 360°.

5 composants :
- metrics      : V9Metrics (Counters/Histograms/Gauges Prometheus business)
- slo          : SLODefinition + V9_SLOS catalog (webhook latency,
                 paywall success rate, admin availability, etc.)
- health       : V9HealthCheck (vault, gates live, platform_config,
                 evidence_ledger chain)
- sentry_context : helpers pour enrichir Sentry events (no-op si SDK absent)

Pattern clef : `V9Metrics` accepte un `CollectorRegistry` injectable —
permet aux tests de creer un registry propre, eviter la pollution
globale Prometheus (ADR-27).
"""
from app.saas_factory.observability.health import (
    HealthCheckResult,
    HealthStatus,
    V9HealthCheck,
)
from app.saas_factory.observability.metrics import (
    V9Metrics,
    get_v9_metrics,
)
from app.saas_factory.observability.sentry_context import (
    add_payment_context,
    add_project_context,
    capture_v9_exception,
    is_sentry_available,
)
from app.saas_factory.observability.slo import (
    V9_SLOS,
    SLODefinition,
    SLOSeverity,
    find_slo_by_name,
)

__all__ = [
    "HealthCheckResult",
    "HealthStatus",
    "SLODefinition",
    "SLOSeverity",
    "V9HealthCheck",
    "V9Metrics",
    "V9_SLOS",
    "add_payment_context",
    "add_project_context",
    "capture_v9_exception",
    "find_slo_by_name",
    "get_v9_metrics",
    "is_sentry_available",
]
