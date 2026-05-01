# 14 — Observability & SLOs

Référence : Phase 9K (`docs/V9_PHASE_9K_REPORT.md`), ADR-27/28.

## Stack

- **Prometheus** : metrics scraping `/metrics`
- **Sentry** : optionnel, error tracking, no-op gracieux si absent
- **Health checks** : `/api/v1/health/v9`
- **SLO catalog** : 9 SLOs typés dans `app.saas_factory.observability.slo`

## V9Metrics — 16 métriques

| Métrique | Type | Labels |
|---|---|---|
| `uba_paywall_triggered_total` | Counter | project_status |
| `uba_payment_amount_cents` | Histogram | currency, status |
| `uba_payment_succeeded_total` | Counter | currency |
| `uba_payment_failed_total` | Counter | currency, reason |
| `uba_refund_amount_cents` | Histogram | currency, reason |
| `uba_ai_cost_per_call_usd` | Histogram | provider, status |
| `uba_ai_decisions_total` | Counter | requested_provider, actual_provider, status |
| `uba_ai_loop_detected_total` | Counter | project_id_hash |
| `uba_ai_budget_blocked_total` | Counter | scope |
| `uba_webhook_processing_duration_seconds` | Histogram | source, event_type, status |
| `uba_webhook_replay_blocked_total` | Counter | source |
| `uba_handoff_resolution_duration_hours` | Histogram | action_type |
| `uba_handoff_escalated_total` | Counter | action_type |
| `uba_active_projects` | Gauge | status |
| `uba_open_handoffs` | Gauge | action_type |
| `uba_platform_live_modes` | Gauge | mode |

## Registry injectable (ADR-27)

```python
from prometheus_client import CollectorRegistry
from app.saas_factory.observability import V9Metrics, get_v9_metrics

# Production : singleton sur REGISTRY global
metrics = get_v9_metrics()

# Tests : registry isolé
metrics = V9Metrics(registry=CollectorRegistry())
```

## SLO catalog — 9 SLOs

| Nom | Cible | Fenêtre | Severity |
|---|---|---|---|
| `webhook_handler_latency` | 99.9% | 30d | CRITICAL |
| `webhook_handler_success` | 99.99% | 30d | CRITICAL |
| `payment_succeeded_to_invoice_lag` | 99% | 30d | HIGH |
| `ai_router_availability` | 99.9% | 7d | HIGH |
| `ai_fallback_rate` | 95% | 7d | MEDIUM |
| `ai_loop_detection_rate` | 99.9% | 7d | LOW |
| `handoff_resolution_within_24h` | 95% | 30d | HIGH |
| `admin_endpoint_availability` | 99.9% | 30d | HIGH |
| `admin_endpoint_latency_p99` | 99% | 30d | MEDIUM |
| `direct_link_token_uniqueness` | 99.999% | 90d | CRITICAL |

Helpers :
```python
from app.saas_factory.observability import V9_SLOS, find_slo_by_name

slo = find_slo_by_name("webhook_handler_latency")
print(slo.error_budget_minutes)    # 43.2 (auto-calculé)
```

## Sentry context (ADR-28)

```python
from app.saas_factory.observability.sentry_context import (
    add_project_context, add_payment_context, capture_v9_exception,
)

# No-op si sentry_sdk pas installé
add_project_context(project_id, owner_email="...")  # email hashé SHA-256
```

## Health endpoint

`GET /api/v1/health/v9` retourne :
```json
{
  "status": "pass",
  "checks": {
    "platform_config": { "status": "pass", ... },
    "evidence_chain":  { "status": "pass", "details": { "count": 12 } },
    "live_modes":      { "status": "warn",  "details": { "stripe": true } },
    "jwt_mode":        { "status": "pass", "details": { "jwt_enabled": true } }
  },
  "checked_at": "2026-05-01T..."
}
```

## Voir aussi

- [15 — Resilience](./15_resilience.md)
- `docs/V9_PHASE_9K_REPORT.md`
