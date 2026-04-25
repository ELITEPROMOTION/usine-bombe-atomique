"""Router /observability V5.9 - Datadog + Sentry + OTel dual-mode."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import get_pool
from app.observability import otel_setup
from app.observability.datadog_exporter import DatadogExporter, Metric
from app.observability.sentry_integration import SentryIntegration

router = APIRouter(prefix="/observability", tags=["observability_v5_9"])


# ============================================================================
# Datadog
# ============================================================================

@router.get("/datadog/status")
async def datadog_status() -> dict[str, Any]:
    exporter = DatadogExporter()
    return {
        "mode": exporter.config.mode,
        "site": exporter.config.site,
        "default_tags": exporter.config.default_tags,
        "log_file_path": exporter.config.log_file_path,
    }


@router.post("/datadog/test")
async def datadog_test() -> dict[str, Any]:
    """Emet une metrique de test pour verifier le pipeline."""
    exporter = DatadogExporter()
    m = Metric("uba.test.ping", 1.0, "gauge", ["source:api"])
    result = await exporter.emit(m)
    return {"emitted": True, "mode": exporter.config.mode, "result": result}


@router.post("/datadog/snapshot")
async def datadog_snapshot() -> dict[str, Any]:
    """Collecte + emet toutes les metriques UBA."""
    exporter = DatadogExporter()
    return await exporter.collect_snapshot(get_pool())


# ============================================================================
# Sentry
# ============================================================================

@router.get("/sentry/status")
async def sentry_status() -> dict[str, Any]:
    sentry = SentryIntegration.instance()
    return {
        "mode": sentry.config.mode,
        "environment": sentry.config.environment,
        "release": sentry.config.release,
        "sample_rate": sentry.config.sample_rate,
        "log_file_path": sentry.config.log_file_path,
    }


@router.post("/sentry/test")
async def sentry_test(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Capture un event de test (mode fichier = ecrit local)."""
    sentry = SentryIntegration.instance()
    body = body or {}
    try:
        raise ValueError(body.get("message", "test event from /sentry/test"))
    except ValueError as exc:
        fp = sentry.capture(
            exc=exc,
            tenant_id=body.get("tenant_id"),
            user_id=body.get("user_id"),
            domain_id=body.get("domain_id"),
            correlation_id=body.get("correlation_id"),
        )
    return {"captured": True, "fingerprint": fp, "mode": sentry.config.mode}


@router.get("/sentry/errors")
async def sentry_errors(limit: int = 50) -> dict[str, Any]:
    sentry = SentryIntegration.instance()
    if sentry.config.mode != "file":
        return {"available_in_file_mode_only": True,
                "cloud_url": "Sentry dashboard"}
    recent = sentry.list_recent(limit=limit)
    grouped = sentry.grouped_issues(limit=limit)
    return {"count": len(recent), "events": recent, "groups": grouped}


# ============================================================================
# OpenTelemetry
# ============================================================================

@router.get("/otel/status")
async def otel_status() -> dict[str, Any]:
    return otel_setup.status()


@router.post("/otel/init")
async def otel_init_endpoint() -> dict[str, Any]:
    return otel_setup.init_otel()
