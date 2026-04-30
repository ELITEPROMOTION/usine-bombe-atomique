"""SLO definitions pour la V9.

Les SLOs sont des **specifications statiques** ; le calcul de compliance
se fait cote Prometheus (avec recording rules + alerting). Ce module
fournit le catalogue, utilisable pour generer les rules YAML, le
dashboard Grafana, ou la documentation /admin.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Final


class SLOSeverity(str, enum.Enum):
    CRITICAL = "critical"   # paging immediat
    HIGH = "high"            # alerte heure ouvree
    MEDIUM = "medium"        # ticket standard
    LOW = "low"              # info, pas d'action immediate


@dataclass(frozen=True)
class SLODefinition:
    name: str                       # identifiant unique
    description: str                 # description metier
    target: float                   # 0.0..1.0 (e.g. 0.999 = 99.9%)
    window: str                      # 7d | 30d | 90d
    severity: SLOSeverity
    metric_name: str                 # nom Prometheus
    threshold_ms: int = 0            # latency threshold en ms (0 = pas de seuil)
    error_budget_minutes: float = 0  # calcule automatiquement
    labels_filter: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 < self.target < 1.0:
            raise ValueError(f"target doit etre dans (0, 1), got {self.target}")
        if self.window not in {"7d", "30d", "90d"}:
            raise ValueError(f"window invalide : {self.window!r}")
        # error budget en minutes pour la fenetre
        window_minutes = {
            "7d": 7 * 24 * 60,
            "30d": 30 * 24 * 60,
            "90d": 90 * 24 * 60,
        }[self.window]
        budget = round((1.0 - self.target) * window_minutes, 2)
        object.__setattr__(self, "error_budget_minutes", budget)


# ---------------------------------------------------------------------------
# Catalogue V9 SLOs
# ---------------------------------------------------------------------------
V9_SLOS: Final[tuple[SLODefinition, ...]] = (
    # --- Paywall / paiement (chemin critique revenu) ---
    SLODefinition(
        name="webhook_handler_latency",
        description="Stripe webhook traite en moins de 500ms (p99)",
        target=0.999, window="30d",
        severity=SLOSeverity.CRITICAL,
        metric_name="uba_webhook_processing_duration_seconds",
        threshold_ms=500,
        labels_filter={"source": "stripe"},
    ),
    SLODefinition(
        name="webhook_handler_success",
        description="Stripe webhook processe sans erreur (status=ok|fallback)",
        target=0.9999, window="30d",
        severity=SLOSeverity.CRITICAL,
        metric_name="uba_webhook_processing_duration_seconds",
        labels_filter={"source": "stripe"},
    ),
    SLODefinition(
        name="payment_succeeded_to_invoice_lag",
        description="Invoice emise dans la minute suivant payment succeeded",
        target=0.99, window="30d",
        severity=SLOSeverity.HIGH,
        metric_name="uba_invoice_emission_lag_seconds",
        threshold_ms=60_000,    # 60s
    ),

    # --- AI router ---
    SLODefinition(
        name="ai_router_availability",
        description="AIRouter retourne sans RouterFailureError",
        target=0.999, window="7d",
        severity=SLOSeverity.HIGH,
        metric_name="uba_ai_decisions_total",
    ),
    SLODefinition(
        name="ai_fallback_rate",
        description="Fallback rate AI provider < 5%",
        target=0.95, window="7d",
        severity=SLOSeverity.MEDIUM,
        metric_name="uba_ai_decisions_total",
    ),
    SLODefinition(
        name="ai_loop_detection_rate",
        description="Loop detector trigger < 0.1% des appels (false positive bas)",
        target=0.999, window="7d",
        severity=SLOSeverity.LOW,
        metric_name="uba_ai_loop_detected_total",
    ),

    # --- Handoff ---
    SLODefinition(
        name="handoff_resolution_within_24h",
        description="Handoffs payment_confirm resolus < 24h",
        target=0.95, window="30d",
        severity=SLOSeverity.HIGH,
        metric_name="uba_handoff_resolution_duration_hours",
        threshold_ms=24 * 3600 * 1000,
        labels_filter={"action_type": "payment_confirm"},
    ),

    # --- Admin endpoints ---
    SLODefinition(
        name="admin_endpoint_availability",
        description="Endpoints /admin/* HTTP 5xx < 0.1%",
        target=0.999, window="30d",
        severity=SLOSeverity.HIGH,
        metric_name="http_requests_total",
        labels_filter={"endpoint": "admin"},
    ),
    SLODefinition(
        name="admin_endpoint_latency_p99",
        description="Endpoints /admin/* p99 < 1s",
        target=0.99, window="30d",
        severity=SLOSeverity.MEDIUM,
        metric_name="http_request_duration_seconds",
        threshold_ms=1000,
        labels_filter={"endpoint": "admin"},
    ),

    # --- Direct links ---
    SLODefinition(
        name="direct_link_token_uniqueness",
        description="Aucune collision SHA-256 sur token_hash",
        target=0.99999, window="90d",
        severity=SLOSeverity.CRITICAL,
        metric_name="uba_direct_link_collision_total",
    ),
)


def find_slo_by_name(name: str) -> SLODefinition | None:
    for slo in V9_SLOS:
        if slo.name == name:
            return slo
    return None


def slos_by_severity(severity: SLOSeverity) -> tuple[SLODefinition, ...]:
    return tuple(s for s in V9_SLOS if s.severity is severity)


def total_error_budget_critical_minutes() -> float:
    """Somme des budgets d'erreur pour les SLOs critiques (au moins 30j)."""
    return sum(
        s.error_budget_minutes for s in V9_SLOS
        if s.severity is SLOSeverity.CRITICAL
    )
