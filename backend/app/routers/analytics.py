"""Endpoints analytics V3 + V4 - dashboard CEO + intelligence."""
from fastapi import APIRouter

from app.database import get_pool
from app.orchestration import (
    audit_events,
    auto_tuner,
    confidence_rollback,
    decision_router,
    defect_taxonomy,
    dz_rules,
    evidence_ledger,
    hypotheses_registry,
    innovation_scout,
    marketplace,
    memory_engine,
    promotion_engine,
    quality_kernel,
    runtime_mesh,
    self_improver,
    truth_kpis,
)
from app.orchestration.escalator import list_pending
from app.orchestration.prompt_ab import variants_summary

router = APIRouter()


@router.get("/overview")
async def overview() -> dict:
    pool = get_pool()
    base = await memory_engine.overview(pool)
    total = max(1, base["projects"])
    base["pass_rate"] = round(base["pass_count"] / total, 4)
    base["fail_rate"] = round(base["fail_count"] / total, 4)
    return base


@router.get("/trend")
async def trend(limit: int = 30) -> list[dict]:
    pool = get_pool()
    return await memory_engine.recent_trend(pool, limit=limit)


@router.get("/agents")
async def agents() -> list[dict]:
    pool = get_pool()
    return await memory_engine.agents_benchmarks(pool)


@router.get("/errors")
async def errors(limit: int = 10) -> list[dict]:
    pool = get_pool()
    return await memory_engine.top_errors(pool, limit=limit)


@router.get("/pending")
async def pending(limit: int = 20) -> list[dict]:
    pool = get_pool()
    return await memory_engine.pending_decisions(pool, limit=limit)


@router.get("/prompt-variants")
async def prompt_variants() -> list[dict]:
    pool = get_pool()
    return await variants_summary(pool)


# ----------- V4 -----------

@router.get("/thresholds")
async def thresholds() -> list[dict]:
    pool = get_pool()
    return await auto_tuner.list_all(pool)


@router.post("/thresholds/retune")
async def thresholds_retune() -> dict:
    pool = get_pool()
    t = await auto_tuner.retune_global(pool)
    return t.to_dict()


@router.get("/marketplace")
async def marketplace_snapshot() -> list[dict]:
    pool = get_pool()
    return await marketplace.snapshot(pool)


@router.post("/marketplace/refresh")
async def marketplace_refresh() -> list[dict]:
    pool = get_pool()
    return await marketplace.refresh_marketplace(pool)


@router.get("/backlog")
async def backlog(status: str | None = None, limit: int = 50) -> list[dict]:
    pool = get_pool()
    return await self_improver.list_backlog(pool, status=status, limit=limit)


@router.post("/backlog/refresh")
async def backlog_refresh() -> dict:
    pool = get_pool()
    return await self_improver.run_cycle(pool)


@router.get("/questions")
async def questions(limit: int = 20) -> list[dict]:
    pool = get_pool()
    return await list_pending(pool, limit=limit)


# ----------- V4.1 -----------

@router.get("/evidence/tail")
async def evidence_tail(limit: int = 50) -> list[dict]:
    pool = get_pool()
    return await evidence_ledger.tail(pool, limit=limit)


@router.get("/evidence/verify")
async def evidence_verify() -> dict:
    pool = get_pool()
    return await evidence_ledger.verify_chain(pool)


@router.get("/hypotheses")
async def hypotheses(task_id: str | None = None, limit: int = 50) -> list[dict]:
    pool = get_pool()
    return await hypotheses_registry.list_open(pool, task_id=task_id, limit=limit)


@router.get("/audit/tail")
async def audit_tail(limit: int = 100, action: str | None = None) -> list[dict]:
    pool = get_pool()
    return await audit_events.tail(pool, limit=limit, action_filter=action)


@router.get("/audit/verify")
async def audit_verify() -> dict:
    pool = get_pool()
    return await audit_events.verify_immutability(pool)


# ----------- V4.2 -----------

@router.get("/dz-rules")
async def dz_rules_list() -> list[dict]:
    pool = get_pool()
    rules = await dz_rules.load_active(pool)
    return [
        {"rule_code": r.rule_code, "version": r.version, "label": r.label,
         "severity": r.severity, "regex_positive": r.regex_positive}
        for r in rules
    ]


@router.get("/defects/summary")
async def defects_summary() -> dict:
    pool = get_pool()
    return await defect_taxonomy.summary(pool)


@router.get("/truth-kpis/capture")
async def truth_kpis_capture() -> dict:
    pool = get_pool()
    snap = await truth_kpis.capture(pool)
    return snap.to_dict()


@router.get("/truth-kpis/latest")
async def truth_kpis_latest() -> dict:
    pool = get_pool()
    data = await truth_kpis.latest(pool)
    return data or {}


@router.get("/innovations")
async def innovations_list(stage: str | None = None) -> list[dict]:
    pool = get_pool()
    return await innovation_scout.list_all(pool, stage=stage)


@router.get("/quality-kernel")
async def quality_kernel_report() -> dict:
    pool = get_pool()
    rep = await quality_kernel.full_report(pool)
    return rep.to_dict()


@router.get("/rollbacks")
async def rollbacks_history(limit: int = 20) -> list[dict]:
    pool = get_pool()
    return await confidence_rollback.history(pool, limit=limit)


# ----------- V4.4 -----------

@router.get("/router/history")
async def router_history(limit: int = 50) -> list[dict]:
    pool = get_pool()
    return await decision_router.history(pool, limit=limit)


@router.get("/router/distribution")
async def router_distribution_endpoint() -> dict:
    pool = get_pool()
    return await decision_router.route_distribution(pool)


@router.get("/promotion/active")
async def promotion_active() -> list[dict]:
    pool = get_pool()
    return await promotion_engine.active_artifacts(pool)


@router.get("/promotion/{task_id}")
async def promotion_by_task(task_id: str) -> list[dict]:
    pool = get_pool()
    return await promotion_engine.list_task_stages(pool, task_id)


@router.post("/promotion/{task_id}/rollback")
async def promotion_rollback(task_id: str, payload: dict) -> dict:
    pool = get_pool()
    av = (payload or {}).get("artifact_version", "")
    reason = (payload or {}).get("reason", "manual rollback")
    if not av:
        return {"ok": False, "error": "artifact_version required"}
    ev = await promotion_engine.rollback(pool, task_id, av, reason)
    return {"ok": True, "evidence_event_id": ev}


@router.get("/runtime/incidents")
async def runtime_incidents(acknowledged: bool | None = None, limit: int = 50) -> list[dict]:
    pool = get_pool()
    return await runtime_mesh.incidents(pool, acknowledged=acknowledged, limit=limit)


@router.post("/runtime/incidents/{incident_id}/ack")
async def runtime_ack(incident_id: str) -> dict:
    pool = get_pool()
    ok = await runtime_mesh.acknowledge(pool, incident_id)
    return {"ok": ok}


@router.get("/runtime/metrics")
async def runtime_metrics_endpoint(target: str | None = None, limit: int = 100) -> list[dict]:
    pool = get_pool()
    return await runtime_mesh.latest_metrics(pool, target=target, limit=limit)


@router.post("/runtime/observe")
async def runtime_observe(payload: dict) -> dict:
    pool = get_pool()
    targets = (payload or {}).get("targets") or {
        "backend": "http://backend:8000/api/v1/health",
    }
    task_id = (payload or {}).get("task_id")
    return await runtime_mesh.observe_once(pool, targets, task_id=task_id)


@router.post("/runtime/baseline")
async def runtime_baseline(payload: dict) -> dict:
    pool = get_pool()
    target = (payload or {}).get("target")
    url = (payload or {}).get("url")
    if not target or not url:
        return {"ok": False, "error": "target + url requis"}
    samples = int((payload or {}).get("samples", 5))
    b = await runtime_mesh.capture_baseline(pool, target, url, samples=samples)
    return {"ok": True, "baseline": b}
