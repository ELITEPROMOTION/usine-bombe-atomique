"""API feature flags : list, toggle, rollout, status, metrics."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.feature_flags import FeatureFlagsService
from app.database import get_pool

router = APIRouter(prefix="/features", tags=["features"])


def _service() -> FeatureFlagsService:
    # Redis injection optionelle - ici None pour simplicite, le service
    # fonctionne sans cache (lecture DB directe)
    return FeatureFlagsService(pool=get_pool(), redis_client=None)


@router.get("/list")
async def features_list() -> dict[str, Any]:
    svc = _service()
    flags = await svc.list_flags()
    return {"count": len(flags), "flags": flags}


@router.get("/{flag_name}/status")
async def feature_status(
    flag_name: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    svc = _service()
    enabled = await svc.is_enabled(flag_name, user_id=user_id,
                                     tenant_id=tenant_id)
    return {
        "flag_name": flag_name,
        "enabled": enabled,
        "user_id": user_id,
        "tenant_id": tenant_id,
    }


@router.post("/{flag_name}/toggle")
async def feature_toggle(
    flag_name: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    enabled = bool(body.get("enabled"))
    updated_by = str(body.get("updated_by", "api"))
    svc = _service()
    try:
        await svc.toggle(flag_name, enabled, updated_by)
    except Exception as exc:
        raise HTTPException(400, f"toggle failed: {exc}") from exc
    return {"flag_name": flag_name, "enabled_globally": enabled}


@router.post("/{flag_name}/rollout")
async def feature_rollout(
    flag_name: str, percent: int, updated_by: str = "api",
) -> dict[str, Any]:
    svc = _service()
    await svc.set_rollout(flag_name, percent, updated_by)
    return {"flag_name": flag_name, "rollout_percent": max(0, min(100, percent))}


@router.get("/{flag_name}/metrics")
async def feature_metrics(
    flag_name: str, hours: int = 24,
) -> dict[str, Any]:
    svc = _service()
    return await svc.metrics(flag_name, hours=hours)
