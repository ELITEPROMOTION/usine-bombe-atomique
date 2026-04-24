"""Router /health V5.7 : quick + detailed + individual + history."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.health.checks import CheckStatus, HealthCheckRegistry

router = APIRouter(prefix="/health", tags=["health_v5_7"])


@router.get("/v2")
async def health_quick(response: Response) -> dict[str, Any]:
    """Check rapide pour load balancer. 200 ou 503."""
    registry = HealthCheckRegistry.instance()
    results = await registry.run_all()
    critical_failures = [
        r for r in results
        if r.is_critical and r.status == CheckStatus.UNHEALTHY
    ]
    degraded = [
        r for r in results if r.status == CheckStatus.DEGRADED
    ]
    if critical_failures:
        response.status_code = 503
        return {
            "status": "unhealthy",
            "critical_failures": [r.name for r in critical_failures],
        }
    return {
        "status": "degraded" if degraded else "healthy",
        "checks_count": len(results),
        "degraded_count": len(degraded),
    }


@router.get("/detailed")
async def health_detailed() -> dict[str, Any]:
    """Rapport complet des 15 checks."""
    registry = HealthCheckRegistry.instance()
    results = await registry.run_all()
    overall = "healthy"
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        if r.is_critical and r.status == CheckStatus.UNHEALTHY:
            overall = "unhealthy"
        elif r.status in (CheckStatus.DEGRADED, CheckStatus.UNHEALTHY) \
             and overall == "healthy":
            overall = "degraded"
    return {
        "overall": overall,
        "checks_count": len(results),
        "by_status": by_status,
        "checks": [r.to_dict() for r in results],
    }


@router.get("/checks/{check_name}")
async def health_check_individual(check_name: str) -> dict[str, Any]:
    """Execute un check individuel (bypass cache)."""
    registry = HealthCheckRegistry.instance()
    if check_name not in registry.list_check_names():
        raise HTTPException(404, f"unknown check: {check_name}")
    result = await registry.run(check_name, use_cache=False)
    return result.to_dict()


@router.get("/list")
async def health_list_checks() -> dict[str, Any]:
    registry = HealthCheckRegistry.instance()
    return {"checks": registry.list_check_names(), "count": 15}
