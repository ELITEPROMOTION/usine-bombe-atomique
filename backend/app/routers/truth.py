"""V5.3 CTC - Router /truth/*.

Endpoints :
  Overview + live :
    GET  /truth/health
    GET  /truth/ready
    GET  /truth/live

  Sources :
    GET  /truth/sources
    POST /truth/sources/harvest/{source_id}
    POST /truth/sources/quarantine/{source_id}
    POST /truth/sources/restore/{source_id}

  Assertions / triangulation :
    POST /truth/triangulate            {claim, domain?}
    GET  /truth/assertions              ?domain=
    GET  /truth/assertions/{id}

  Chain :
    POST /truth/chain/genesis
    GET  /truth/chain/tail
    GET  /truth/chain/integrity_check
    POST /truth/chain/verify

  Explain :
    GET  /truth/explain/{event_id}
    GET  /truth/explain/{event_id}/sources
    GET  /truth/explain/{event_id}/assertions

  Phase gates :
    POST /truth/phase_gate/validate
    GET  /truth/phase_gate/{gate_id}
    GET  /truth/phase_gate/distribution
    GET  /truth/phase_gate/for_task/{task_id}

  Validation :
    POST /truth/validate/7_layer         {context}
    POST /truth/cycles/tick              (manual cycle)

  Chaos :
    POST /truth/chaos/run

  Overrides :
    POST /truth/override                 {justification, human_id, new_verdict}
    GET  /truth/override/active

  Meta :
    POST /truth/meta_audit
    GET  /truth/meta_audit/latest

  Snapshots :
    POST /truth/snapshot/create
    GET  /truth/snapshot/list

  Budget :
    GET  /truth/budget/daily

  Risk detection :
    POST /truth/risk/analyze             {text}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.ctc import (
    assertion_risk_detector,
    auto_triangulator,
    continuous_validators,
    evidence_chain,
    evidence_harvester,
    human_override_manager,
    meta_truth_auditor,
    phase_gate_enforcer,
    seven_layer_validator,
    source_registry,
    truth_budget_manager,
    truth_chaos_engine,
    truth_engine_snapshotter,
    truth_explainability_api,
    truth_graph,
)
from app.database import get_pool

router = APIRouter()


# ============================================================ Health

@router.get("/truth/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "ctc"}


@router.get("/truth/ready")
async def ready() -> dict[str, Any]:
    pool = get_pool()
    async with pool.acquire() as conn:
        chain_events = await conn.fetchval(
            "SELECT COUNT(*) FROM evidence_chain_events")
        sources = await conn.fetchval(
            "SELECT COUNT(*) FROM truth_sources WHERE status = 'active'")
    return {"ready": True, "chain_events": int(chain_events or 0),
            "active_sources": int(sources or 0)}


@router.get("/truth/live")
async def live() -> dict[str, Any]:
    """Dashboard /truth/live : etat global CTC."""
    pool = get_pool()
    chain_rep = await evidence_chain.verify_chain(pool, limit=500)
    async with pool.acquire() as conn:
        sources_by_status = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM truth_sources GROUP BY status"
        )
        assertions_by_status = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM truth_assertions GROUP BY status"
        )
        gates_dist = await phase_gate_enforcer.distribution(pool)
        contradictions = await truth_graph.contradictions_open(pool, limit=100)
        cost = await truth_budget_manager.daily_cost(pool)
    return {
        "status_global": "GREEN" if chain_rep.status == "preserved" else "RED",
        "evidence_chain": chain_rep.to_dict(),
        "sources_by_status": {r["status"]: int(r["n"]) for r in sources_by_status},
        "assertions_by_status": {r["status"]: int(r["n"]) for r in assertions_by_status},
        "phase_gates": gates_dist,
        "contradictions_open": len(contradictions),
        "daily_cost_usd": round(cost, 4),
    }


# ============================================================ Sources

@router.get("/truth/sources")
async def list_sources(status: str | None = None) -> list[dict[str, Any]]:
    srcs = await source_registry.list_all(get_pool(), status=status)
    return [s.to_dict() for s in srcs]


@router.post("/truth/sources/harvest/{source_id}")
async def harvest_one(source_id: str, real: bool = False) -> dict[str, Any]:
    r = await evidence_harvester.fetch_one(
        get_pool(), source_id, skip_actual_fetch=not real)
    return r.to_dict()


@router.post("/truth/sources/quarantine/{source_id}")
async def quarantine(source_id: str, payload: dict) -> dict[str, Any]:
    reason = payload.get("reason", "manual")
    ok = await source_registry.quarantine(get_pool(), source_id, reason)
    return {"quarantined": ok}


@router.post("/truth/sources/restore/{source_id}")
async def restore(source_id: str) -> dict[str, Any]:
    ok = await source_registry.restore(get_pool(), source_id)
    return {"restored": ok}


# ============================================================ Assertions

@router.post("/truth/triangulate")
async def triangulate(payload: dict) -> dict[str, Any]:
    claim = payload.get("claim")
    if not claim:
        raise HTTPException(400, "claim required")
    r = await auto_triangulator.triangulate(
        get_pool(), claim, skip_fetch=True)
    return r.to_dict()


@router.get("/truth/assertions")
async def assertions_by_domain(
    domain: str | None = None, limit: int = 20,
) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        if domain:
            rows = await conn.fetch(
                """
                SELECT assertion_id, assertion_type, domain, severity,
                       confidence, status, normalized_text
                FROM truth_assertions WHERE domain = $1
                ORDER BY extracted_at DESC LIMIT $2
                """, domain[:60], limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT assertion_id, assertion_type, domain, severity,
                       confidence, status, normalized_text
                FROM truth_assertions ORDER BY extracted_at DESC LIMIT $1
                """, limit,
            )
    return [{
        "assertion_id": str(r["assertion_id"]),
        "type": r["assertion_type"], "domain": r["domain"],
        "severity": r["severity"], "confidence": r["confidence"],
        "status": r["status"], "text": r["normalized_text"][:300],
    } for r in rows]


# ============================================================ Chain

@router.post("/truth/chain/genesis")
async def chain_genesis() -> dict[str, Any]:
    ev = await evidence_chain.genesis(get_pool())
    return ev.to_dict() if ev else {"already_initialized": True}


@router.get("/truth/chain/tail")
async def chain_tail(limit: int = 20) -> list[dict[str, Any]]:
    return await evidence_chain.tail(get_pool(), limit=limit)


@router.post("/truth/chain/verify")
async def chain_verify() -> dict[str, Any]:
    rep = await evidence_chain.verify_chain(get_pool())
    return rep.to_dict()


@router.get("/truth/chain/integrity_check")
async def chain_integrity() -> dict[str, Any]:
    return await truth_explainability_api.latest_integrity_check(get_pool())


# ============================================================ Explain

@router.get("/truth/explain/{event_id}")
async def explain(event_id: str) -> dict[str, Any]:
    return await truth_explainability_api.explain_event(get_pool(), event_id)


@router.get("/truth/explain/{event_id}/sources")
async def explain_sources(event_id: str) -> list[dict[str, Any]]:
    return await truth_explainability_api.sources_for_event(get_pool(), event_id)


@router.get("/truth/explain/{event_id}/assertions")
async def explain_assertions(event_id: str) -> list[dict[str, Any]]:
    return await truth_explainability_api.assertions_for_event(get_pool(), event_id)


# ============================================================ Phase gates

@router.post("/truth/phase_gate/validate")
async def phase_gate_validate(payload: dict) -> dict[str, Any]:
    name = payload.get("name")
    task_id = payload.get("task_id")
    if not name or not task_id:
        raise HTTPException(400, "name and task_id required")
    ctx = payload.get("context") or {}
    try:
        d = await phase_gate_enforcer.validate(
            get_pool(), name=name, task_id=task_id, context=ctx)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return d.to_dict()


@router.get("/truth/phase_gate/distribution")
async def phase_gate_distribution() -> dict[str, int]:
    return await phase_gate_enforcer.distribution(get_pool())


@router.get("/truth/phase_gate/for_task/{task_id}")
async def phase_gate_for_task(task_id: str) -> list[dict[str, Any]]:
    return await phase_gate_enforcer.list_for_task(get_pool(), task_id)


@router.get("/truth/phase_gate/{gate_id}")
async def phase_gate_details(gate_id: str) -> dict[str, Any]:
    return await truth_explainability_api.phase_gate_details(
        get_pool(), gate_id)


# ============================================================ Validation

@router.post("/truth/validate/7_layer")
async def validate_7layer(payload: dict) -> dict[str, Any]:
    ctx = payload.get("context") or {}
    r = await seven_layer_validator.validate(get_pool(), ctx)
    return r.to_dict()


@router.post("/truth/cycles/tick")
async def cycles_tick() -> dict[str, Any]:
    results = await continuous_validators.tick(get_pool())
    return {k: v.to_dict() for k, v in results.items()}


# ============================================================ Chaos

@router.post("/truth/chaos/run")
async def chaos_run(seed: int | None = None) -> dict[str, Any]:
    return await truth_chaos_engine.run_all(get_pool(), seed=seed)


# ============================================================ Overrides

@router.post("/truth/override")
async def do_override(payload: dict) -> dict[str, Any]:
    try:
        r = await human_override_manager.override(
            get_pool(),
            original_verdict_id=payload.get("original_verdict_id"),
            new_verdict=payload.get("new_verdict", "PASS"),
            justification=payload.get("justification", ""),
            human_id=payload.get("human_id", "ahmed"),
            task_id=payload.get("task_id"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return r


@router.get("/truth/override/active")
async def overrides_active() -> list[dict[str, Any]]:
    return await human_override_manager.list_active(get_pool())


# ============================================================ Meta

@router.post("/truth/meta_audit")
async def meta_audit() -> dict[str, Any]:
    a = await meta_truth_auditor.audit(get_pool())
    return a.to_dict()


@router.get("/truth/meta_audit/latest")
async def meta_audit_latest() -> dict[str, Any]:
    r = await meta_truth_auditor.latest(get_pool())
    return r or {"never_audited": True}


# ============================================================ Snapshots

@router.post("/truth/snapshot/create")
async def snapshot_create() -> dict[str, Any]:
    return await truth_engine_snapshotter.create_snapshot(get_pool())


@router.get("/truth/snapshot/list")
async def snapshot_list(limit: int = 10) -> list[dict[str, Any]]:
    return await truth_engine_snapshotter.list_snapshots(get_pool(), limit=limit)


# ============================================================ Budget

@router.get("/truth/budget/daily")
async def budget_daily() -> dict[str, Any]:
    bc = await truth_budget_manager.check_daily_budget(get_pool())
    return bc.to_dict()


# ============================================================ Risk detection

@router.post("/truth/risk/analyze")
async def risk_analyze(payload: dict) -> dict[str, Any]:
    text = payload.get("text")
    if not text:
        raise HTTPException(400, "text required")
    risks = await assertion_risk_detector.analyze(text, pool=get_pool())
    score = assertion_risk_detector.hallucination_score(risks)
    return {
        "risks": [r.to_dict() for r in risks],
        "hallucination_score": round(score, 4),
        "should_block": assertion_risk_detector.should_block(score),
    }
