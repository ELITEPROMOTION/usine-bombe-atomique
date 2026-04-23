"""V5.1 - Endpoints Autonomy (V5.1 Ultimate 99.9%+).

Expose :
  - /autonomy/kpis                       : KPIs auditor (capture ou dernier)
  - /autonomy/chaos/run                  : lance les scenarios chaos
  - /autonomy/ladder/decide              : simule une decision ladder
  - /autonomy/leases                     : list + grant + revoke
  - /autonomy/boundaries                 : registre + ajout
  - /autonomy/learn/recent               : batch intervention_learner
  - /autonomy/calibration                : rapport calibration
  - /autonomy/sim/replay                 : simulation replay + grid search
  - /autonomy/explain/{correlation_id}   : trace + decisions
  - /autonomy/avoided                    : escalations evitees recentes
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.autonomy import (
    ambiguity_resolver,
    autonomy_auditor,
    autonomy_chaos_engine,
    autonomy_cost_model,
    autonomy_explainability_api,
    autonomy_ladder,
    autonomy_simulation_lab,
    calibration_engine,
    hard_boundary_registry,
    intervention_learner,
    permission_lease_manager,
)
from app.autonomy.autonomy_ladder import LadderInput
from app.autonomy.autonomy_simulation_lab import Policy
from app.database import get_pool

router = APIRouter()


@router.get("/autonomy/kpis")
async def get_kpis(window_hours: int = 168, capture: bool = False) -> dict[str, Any]:
    pool = get_pool()
    if capture:
        k = await autonomy_auditor.compute(pool, window_hours=window_hours)
        await autonomy_auditor.persist(pool, k)
        return k.to_dict()
    last = await autonomy_auditor.latest(pool)
    return last or {"empty": True}


@router.post("/autonomy/kpis/capture")
async def capture_kpis(window_hours: int = 168) -> dict[str, Any]:
    pool = get_pool()
    k = await autonomy_auditor.compute(pool, window_hours=window_hours)
    await autonomy_auditor.persist(pool, k)
    return k.to_dict()


@router.post("/autonomy/chaos/run")
async def run_chaos(seed: int | None = None) -> dict[str, Any]:
    pool = get_pool()
    return await autonomy_chaos_engine.run_all(pool, seed=seed)


@router.post("/autonomy/ladder/decide")
async def ladder_decide(payload: dict) -> dict[str, Any]:
    try:
        li = LadderInput(
            confidence=float(payload.get("confidence", 0.7)),
            reversible=bool(payload.get("reversible", True)),
            scope_reducible=bool(payload.get("scope_reducible", True)),
            hard_boundary=bool(payload.get("hard_boundary", False)),
            proof_valid=bool(payload.get("proof_valid", False)),
            ambiguity_resolved=bool(payload.get("ambiguity_resolved", False)),
            sub_type=payload.get("sub_type"),
            criticality=payload.get("criticality", "medium"),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"payload invalide: {exc}")
    d = autonomy_ladder.decide(li)
    d = autonomy_ladder.upgrade_for_criticality(d, li.criticality)
    return d.to_dict()


@router.post("/autonomy/resolve_ambiguity")
async def resolve_amb(payload: dict) -> dict[str, Any]:
    pool = get_pool()
    q = payload.get("question", "")
    if not q:
        raise HTTPException(400, "question required")
    res = await ambiguity_resolver.resolve(
        pool, q, context=payload.get("context", ""),
        task_id=payload.get("task_id"),
        correlation_id=payload.get("correlation_id"),
    )
    return {
        "resolved": res.resolved, "level": res.level_resolved,
        "resolution": res.resolution, "kind": res.kind,
        "sub_type": res.sub_type,
    }


@router.get("/autonomy/leases")
async def list_leases() -> list[dict[str, Any]]:
    return await permission_lease_manager.list_active(get_pool())


@router.post("/autonomy/leases/grant")
async def grant_lease(payload: dict) -> dict[str, Any]:
    scope = payload.get("scope")
    if not scope:
        raise HTTPException(400, "scope required")
    lease = await permission_lease_manager.grant(
        get_pool(), scope,
        duration_days=int(payload.get("duration_days", 30)),
        cap_amount=payload.get("cap_amount"),
        cap_currency=payload.get("cap_currency"),
        usage_cap=int(payload.get("usage_cap", 1)),
        task_id=payload.get("task_id"),
        granter=payload.get("granter", "ahmed"),
    )
    return lease.to_dict()


@router.post("/autonomy/leases/{lease_id}/revoke")
async def revoke_lease(lease_id: int) -> dict[str, Any]:
    ok = await permission_lease_manager.revoke(get_pool(), lease_id)
    return {"revoked": ok}


@router.get("/autonomy/boundaries")
async def boundaries() -> list[dict[str, Any]]:
    return await hard_boundary_registry.list_all(get_pool())


@router.post("/autonomy/boundaries")
async def add_boundary(payload: dict) -> dict[str, Any]:
    scope = payload.get("scope")
    desc = payload.get("description", "")
    rt = payload.get("requires_type", "C")
    if not scope:
        raise HTTPException(400, "scope required")
    await hard_boundary_registry.register(get_pool(), scope, desc, rt)
    return {"scope": scope, "registered": True}


@router.post("/autonomy/learn/recent")
async def learn_recent(limit: int = 50) -> dict[str, Any]:
    return await intervention_learner.learn_from_recent(get_pool(), limit=limit)


@router.get("/autonomy/calibration")
async def calibration(window_days: int = 14) -> dict[str, Any]:
    r = await calibration_engine.compute(get_pool(), window_days=window_days)
    return r.to_dict()


@router.post("/autonomy/sim/replay")
async def sim_replay(payload: dict) -> dict[str, Any]:
    pol = Policy(
        escalate_confidence_threshold=float(
            payload.get("escalate_confidence_threshold", 0.40)),
        constrain_confidence_threshold=float(
            payload.get("constrain_confidence_threshold", 0.60)),
        probe_confidence_threshold=float(
            payload.get("probe_confidence_threshold", 0.75)),
        continue_confidence_threshold=float(
            payload.get("continue_confidence_threshold", 0.92)),
    )
    r = await autonomy_simulation_lab.replay(
        get_pool(), pol, window_days=int(payload.get("window_days", 14)))
    return r.to_dict()


@router.post("/autonomy/sim/grid_search")
async def sim_grid(window_days: int = 14) -> dict[str, Any]:
    return await autonomy_simulation_lab.grid_search(
        get_pool(), window_days=window_days)


@router.get("/autonomy/cost/best_mode")
async def cost_best(confidence: float = 0.7,
                    tokens_in: int = 0, tokens_out: int = 0,
                    duration_ms: int = 0,
                    downstream_cost_usd: float = 100.0) -> dict[str, Any]:
    return autonomy_cost_model.best_mode(
        confidence, tokens_in=tokens_in, tokens_out=tokens_out,
        duration_ms=duration_ms, downstream_cost_usd=downstream_cost_usd,
    )


@router.get("/autonomy/explain/{correlation_id}")
async def explain(correlation_id: str) -> dict[str, Any]:
    return await autonomy_explainability_api.explain(get_pool(), correlation_id)


@router.get("/autonomy/avoided")
async def avoided(limit: int = 10) -> list[dict[str, Any]]:
    return await autonomy_explainability_api.recent_avoided_escalations(
        get_pool(), limit=limit)
