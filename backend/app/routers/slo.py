"""Router /slo V5.7 : status, history, incidents, burn rate."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.database import get_pool
from app.observability.slo_tracker import SLOTracker

router = APIRouter(prefix="/slo", tags=["slo_v5_7"])


def _tracker() -> SLOTracker:
    return SLOTracker(get_pool())


@router.get("/status")
async def slo_status() -> dict[str, Any]:
    statuses = await _tracker().status_all()
    return {
        "count": len(statuses),
        "slos": [
            {
                "slo_name": s.slo_name,
                "target_percent": s.target_percent,
                "current_sli": s.current_sli,
                "error_budget_minutes": s.error_budget_minutes,
                "error_budget_remaining_minutes": s.error_budget_remaining_minutes,
                "burn_rate_1h": s.burn_rate_1h,
                "burn_rate_6h": s.burn_rate_6h,
                "status": s.status,
                "incident_active": s.incident_active,
            }
            for s in statuses
        ],
    }


@router.get("/incidents")
async def slo_incidents(limit: int = 50) -> dict[str, Any]:
    items = await _tracker().incidents(limit=limit)
    return {"count": len(items), "incidents": items}


@router.post("/measure")
async def slo_measure(body: dict[str, Any]) -> dict[str, Any]:
    """Enregistre une mesure (admin)."""
    t = _tracker()
    await t.record(
        slo_name=body["slo_name"],
        good=int(body.get("good", 0)),
        bad=int(body.get("bad", 0)),
        sli_value=body.get("sli_value"),
        metadata=body.get("metadata"),
    )
    return {"recorded": True, "slo_name": body["slo_name"]}


@router.get("/definitions")
async def slo_definitions() -> dict[str, Any]:
    defs = await _tracker().list_definitions()
    return {
        "count": len(defs),
        "definitions": [
            {
                "slo_name": d.slo_name,
                "description": d.description,
                "target_percent": d.target_percent,
                "window_days": d.window_days,
                "sli_type": d.sli_type,
            }
            for d in defs
        ],
    }
