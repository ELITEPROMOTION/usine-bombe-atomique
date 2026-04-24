"""V5.2 - Router dehardcoding.

Endpoints :
  GET  /dehardcoding/overview         : distribution P0-P3 + counters
  GET  /dehardcoding/parameters        : liste system_parameters current
  POST /dehardcoding/parameters/{key}  : set_value (body: value, actor, justification)
  POST /dehardcoding/parameters/{key}/rollback
  GET  /dehardcoding/parameters/{key}/history
  GET  /dehardcoding/boundaries        : whitelist/blacklist reasoning
  GET  /dehardcoding/decisions/{task_id}
  GET  /dehardcoding/decisions/replay/{decision_id}
  GET  /dehardcoding/drift             : derives detectees
  POST /dehardcoding/drift/scan        : force un scan
  GET  /dehardcoding/promotions         : historique shadow->limited->full
  GET  /dehardcoding/invariants/check   : lance verify_pre + verify_post snapshot
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import get_pool
from app.governance import (
    drift_detector,
    invariants_runtime,
    parameter_manager,
    reasoning_boundaries,
    reasoning_canary,
    reasoning_engine,
    rules_classifier,
)

router = APIRouter()


@router.get("/dehardcoding/overview")
async def overview() -> dict[str, Any]:
    pool = get_pool()
    # Distribution via classifier live
    root = Path("/app/app")
    if not root.exists():
        root = Path(__file__).resolve().parents[1]
    items = rules_classifier.scan_tree(root)
    dist = rules_classifier.distribution(items)
    total = len(items)
    # Compteurs lies
    params = await parameter_manager.list_all(pool)
    return {
        "classification": {
            "total_constants": total,
            "distribution": dist,
            "pct": {k: round(v / total * 100, 1) if total else 0
                    for k, v in dist.items()},
        },
        "system_parameters": {
            "count": len(params),
            "parametrizable": sum(1 for p in params if p["category"] == "PARAMETRIZABLE"),
            "learnable": sum(1 for p in params if p["category"] == "LEARNABLE"),
        },
        "reasoning_boundaries": reasoning_boundaries.catalog(),
        "fiscal_dz_signature": invariants_runtime.snapshot_signature()[:32],
    }


@router.get("/dehardcoding/parameters")
async def list_parameters() -> list[dict[str, Any]]:
    return await parameter_manager.list_all(get_pool())


@router.post("/dehardcoding/parameters/{key}")
async def set_parameter(key: str, payload: dict) -> dict[str, Any]:
    actor = payload.get("actor")
    if not actor:
        raise HTTPException(400, "actor required")
    if "value" not in payload:
        raise HTTPException(400, "value required")
    justification = payload.get("justification", "")
    try:
        p = await parameter_manager.set_value(
            get_pool(), key, payload["value"],
            actor=actor, justification=justification)
    except parameter_manager.ParameterError as exc:
        raise HTTPException(400, str(exc))
    return p.to_dict()


@router.post("/dehardcoding/parameters/{key}/rollback")
async def rollback_parameter(key: str, versions_back: int = 1) -> dict[str, Any]:
    try:
        p = await parameter_manager.rollback(
            get_pool(), key, versions_back=versions_back, actor="ahmed")
    except parameter_manager.ParameterError as exc:
        raise HTTPException(400, str(exc))
    return p.to_dict()


@router.get("/dehardcoding/parameters/{key}/history")
async def parameter_history(key: str, limit: int = 20) -> list[dict[str, Any]]:
    return await parameter_manager.history(get_pool(), key, limit=limit)


@router.get("/dehardcoding/boundaries")
async def boundaries() -> dict[str, Any]:
    return reasoning_boundaries.catalog()


@router.post("/dehardcoding/boundaries/check")
async def boundaries_check(payload: dict) -> dict[str, Any]:
    domain = payload.get("domain", "")
    v = reasoning_boundaries.verdict(domain)
    return {"domain": domain, "allowed": v.allowed,
            "reason": v.reason, "route_to": v.route_to}


@router.get("/dehardcoding/decisions/{task_id}")
async def decisions_for_task(task_id: str,
                                limit: int = 50) -> list[dict[str, Any]]:
    return await reasoning_engine.fetch_by_task(
        get_pool(), task_id, limit=limit)


@router.get("/dehardcoding/decisions/replay/{decision_id}")
async def decision_replay(decision_id: str) -> dict[str, Any]:
    return await reasoning_engine.replay(get_pool(), decision_id)


@router.get("/dehardcoding/drift")
async def drift_recent(limit: int = 20) -> list[dict[str, Any]]:
    return await drift_detector.recent(get_pool(), limit=limit)


@router.post("/dehardcoding/drift/scan")
async def drift_scan(window_days: int = 7,
                      baseline_days: int = 30) -> dict[str, Any]:
    alerts = await drift_detector.scan_all(
        get_pool(), window_days=window_days, baseline_days=baseline_days)
    return {"alerts_count": len(alerts),
            "alerts": [a.to_dict() for a in alerts]}


@router.get("/dehardcoding/promotions")
async def promotions_history(rule_key: str | None = None,
                                limit: int = 30) -> list[dict[str, Any]]:
    return await reasoning_canary.history(
        get_pool(), rule_key=rule_key, limit=limit)


@router.get("/dehardcoding/invariants/check")
async def invariants_check() -> dict[str, Any]:
    pre = invariants_runtime.verify_pre({
        "tenant_id": "test-tenant", "builder": "b", "critic": "c", "judge": "j",
    })
    post = invariants_runtime.verify_post({
        "proof_coverage": 0.95, "tests_passed": 10, "tests_total": 10,
    })
    sig = invariants_runtime.verify_fiscal_dz_signature()
    all_results = pre + post + [sig]
    return {
        "total_checked": len(all_results),
        "passed": sum(1 for r in all_results if r.passed),
        "failed": sum(1 for r in all_results if not r.passed),
        "fiscal_dz_signature_ok": sig.passed,
        "details": [{"name": r.name, "family": r.family,
                      "passed": r.passed} for r in all_results],
    }


@router.get("/dehardcoding/classification")
async def classification() -> dict[str, Any]:
    root = Path("/app/app")
    if not root.exists():
        root = Path(__file__).resolve().parents[1]
    items = rules_classifier.scan_tree(root)
    return {
        "total": len(items),
        "distribution": rules_classifier.distribution(items),
        "sample": [
            {"file": it.file.replace("\\", "/").split("backend/")[-1],
             "line": it.line, "name": it.name,
             "category": it.category, "justification": it.justification}
            for it in items[:30]
        ],
    }
