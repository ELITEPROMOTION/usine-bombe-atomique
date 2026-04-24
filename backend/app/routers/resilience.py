"""Router resilience V5.7 : circuit breakers + chaos + runbooks."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.resilience import CircuitBreakerRegistry
from app.resilience.chaos import ChaosRunner, list_scenarios
from app.resilience.runbooks import RunbookOrchestrator, list_runbooks

router = APIRouter(prefix="/resilience", tags=["resilience_v5_7"])


# ---------- Circuit breakers ----------
@router.get("/breakers")
async def breakers_list() -> dict[str, Any]:
    reg = CircuitBreakerRegistry.instance()
    return {"count": 6, "breakers": reg.list_all()}


@router.post("/breakers/{name}/reset")
async def breaker_reset(name: str) -> dict[str, Any]:
    try:
        cb = CircuitBreakerRegistry.instance().get(name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cb.reset()
    return {"reset": True, "breaker": name}


# ---------- Chaos ----------
@router.get("/chaos/scenarios")
async def chaos_list() -> dict[str, Any]:
    return {"count": 20, "scenarios": list_scenarios()}


@router.post("/chaos/run")
async def chaos_run(body: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(body.get("dry_run", True))
    runner = ChaosRunner(dry_run=dry_run)
    ids = body.get("scenario_ids")
    if ids:
        results = await runner.run_by_ids(ids)
    else:
        results = await runner.run_all()
    return {"dry_run": dry_run, "count": len(results), "results": results}


# ---------- Runbooks ----------
@router.get("/runbooks")
async def runbooks_list() -> dict[str, Any]:
    return {"count": 15, "runbooks": list_runbooks()}


@router.post("/runbooks/scan")
async def runbooks_scan() -> dict[str, Any]:
    orch = RunbookOrchestrator()
    results = await orch.scan_all()
    detected = [r for r in results if r.detected]
    return {
        "count": len(results),
        "detected": len(detected),
        "remediated": sum(1 for r in results if r.remediated),
        "executions": [r.to_dict() for r in results],
    }
