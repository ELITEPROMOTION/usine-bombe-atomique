"""V5.4 - Router /reasoning/* + /cognition/*.

Endpoints :
  GET  /cognition/health
  GET  /cognition/live
  POST /reasoning/reason                     (problem_statement -> trace)
  GET  /reasoning/trace/{trace_id}
  GET  /reasoning/traces
  POST /reasoning/cot/zero_shot
  POST /reasoning/cot/structured
  POST /reasoning/cot/self_consistent
  POST /reasoning/tot                        (thought -> tree)
  POST /reasoning/got                        (build + analyze graph)
  POST /reasoning/react                      (problem -> steps)
  POST /reasoning/reflexion                  (solution -> cycles)
  POST /reasoning/debate                     (question -> verdict)
  POST /reasoning/mcts                       (state -> best_action)
  POST /reasoning/self_discover              (problem -> plan)
  POST /reasoning/constitutional/check       (text -> report)
  POST /reasoning/recursive_refinement       (solution -> refined)
  POST /cognition/benchmarks/run             (run all 5 families)
  GET  /cognition/benchmarks/latest
  GET  /cognition/health/report              (weekly health)
  GET  /cognition/circuit/recent
  GET  /cognition/cache/stats
  POST /cognition/cache/invalidate_all
  POST /cognition/adversarial/run            (50 scenarios)
  GET  /cognition/dependencies/{trace_id}/descendants
  POST /cognition/dependencies/invalidate_cascade/{trace_id}
  GET  /cognition/load/snapshot
  POST /cognition/override
  GET  /cognition/override/list
  POST /cognition/reproducibility/replay
  GET  /cognition/reproducibility/latest
  GET  /cognition/frontier/catalog
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.cognition import (
    adversarial_reasoning_tester,
    bias_detector,
    cognitive_circuit_breaker,
    cognitive_dependency_graph,
    cognitive_health_monitor,
    cognitive_load_balancer,
    constitutional_ai,
    cot_engine,
    debate_engine,
    frontier_knowledge,
    graph_of_thoughts,
    human_reasoning_override,
    mcts_reasoning,
    meta_cognition,
    reasoning_benchmarks,
    reasoning_cache_semantic,
    reasoning_core,
    reasoning_reproducibility_test,
    recursive_refinement,
    reflexion_engine,
    react_engine,
    self_discover,
    tree_of_thoughts,
    uncertainty_quantifier,
)
from app.cognition.reasoning_core import ReasoningRequest
from app.database import get_pool


router = APIRouter()


# ============================================================ health/live

@router.get("/cognition/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "cognition", "version": "v5.4"}


@router.get("/cognition/live")
async def live() -> dict[str, Any]:
    pool = get_pool()
    traces = await reasoning_core.list_traces(pool, limit=10)
    cache = await reasoning_cache_semantic.stats(pool)
    kills = await cognitive_circuit_breaker.recent(pool, limit=5)
    load = await cognitive_load_balancer.snapshot(pool)
    bench = await reasoning_benchmarks.latest(pool)
    return {
        "recent_traces": traces,
        "cache_stats": cache,
        "kill_events": kills,
        "load": load,
        "benchmarks_latest": bench,
    }


# ============================================================ reasoning core

@router.post("/reasoning/reason")
async def do_reason(payload: dict) -> dict[str, Any]:
    ps = payload.get("problem_statement")
    if not ps:
        raise HTTPException(400, "problem_statement required")
    req = ReasoningRequest(
        problem_statement=ps,
        task_id=payload.get("task_id"),
        criticality=payload.get("criticality", "medium"),
        allow_shortcut=bool(payload.get("allow_shortcut", True)),
        budget_tokens=payload.get("budget_tokens"),
    )
    trace = await reasoning_core.reason(get_pool(), req)
    return trace.model_dump()


@router.get("/reasoning/trace/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    r = await reasoning_core.get_trace(get_pool(), trace_id)
    if r is None:
        raise HTTPException(404, "trace not found")
    return r


@router.get("/reasoning/traces")
async def list_traces(limit: int = 20) -> list[dict[str, Any]]:
    return await reasoning_core.list_traces(get_pool(), limit=limit)


# ============================================================ CoT

@router.post("/reasoning/cot/zero_shot")
async def cot_zero_shot(payload: dict) -> dict[str, Any]:
    p = payload.get("problem")
    if not p:
        raise HTTPException(400, "problem required")
    return cot_engine.zero_shot_cot(p).model_dump()


@router.post("/reasoning/cot/structured")
async def cot_structured(payload: dict) -> dict[str, Any]:
    p = payload.get("problem")
    if not p:
        raise HTTPException(400, "problem required")
    return cot_engine.structured_cot(p).model_dump()


@router.post("/reasoning/cot/self_consistent")
async def cot_sc(payload: dict) -> dict[str, Any]:
    p = payload.get("problem")
    if not p:
        raise HTTPException(400, "problem required")
    n = int(payload.get("n_samples", 5))
    return cot_engine.self_consistent_cot(p, n_samples=n).model_dump()


# ============================================================ ToT / GoT

@router.post("/reasoning/tot")
async def tot(payload: dict) -> dict[str, Any]:
    root = payload.get("root_thought")
    if not root:
        raise HTTPException(400, "root_thought required")
    strat = payload.get("strategy", "best_first")
    r = tree_of_thoughts.build_tree(
        root, strategy=strat,
        max_depth=int(payload.get("max_depth", 4)),
        branching=int(payload.get("branching", 3)))
    return r.model_dump()


@router.post("/reasoning/got")
async def got(payload: dict) -> dict[str, Any]:
    thoughts = payload.get("thoughts") or ["A", "B", "C"]
    g = graph_of_thoughts.GraphBuild()
    ids = [g.add(t, value=0.6) for t in thoughts]
    # Link A->C, B->C supports
    if len(ids) >= 3:
        g.link(ids[0], ids[2], "supports")
        g.link(ids[1], ids[2], "supports")
    return graph_of_thoughts.build_trace(g).model_dump()


# ============================================================ ReAct

@router.post("/reasoning/react")
async def do_react(payload: dict) -> dict[str, Any]:
    p = payload.get("problem")
    if not p:
        raise HTTPException(400, "problem required")
    r = await react_engine.run(
        p, max_iterations=int(payload.get("max_iterations", 5)))
    return r.to_dict()


# ============================================================ Reflexion

@router.post("/reasoning/reflexion")
async def do_reflexion(payload: dict) -> dict[str, Any]:
    sol = payload.get("solution")
    if not sol:
        raise HTTPException(400, "solution required")
    r = reflexion_engine.run(
        sol, max_cycles=int(payload.get("max_cycles", 3)))
    return r.model_dump()


# ============================================================ Debate

@router.post("/reasoning/debate")
async def do_debate(payload: dict) -> dict[str, Any]:
    q = payload.get("question", "")
    cfg = debate_engine.DebateConfig(
        role_a=payload.get("role_a", "Optimist"),
        role_b=payload.get("role_b", "Pessimist"),
        max_rounds=int(payload.get("max_rounds", 5)),
    )
    return debate_engine.debate(q, cfg=cfg).model_dump()


# ============================================================ MCTS

@router.post("/reasoning/mcts")
async def do_mcts(payload: dict) -> dict[str, Any]:
    state = payload.get("state", "root")
    r = mcts_reasoning.run_mcts(
        state, n_simulations=int(payload.get("n_simulations", 30)),
        seed=int(payload.get("seed", 42)))
    return {"best_action": r.best_action, "best_value": r.best_value,
            "tree_size": r.tree_size, "simulations": r.simulations,
            "ucb_scores": r.ucb_scores}


# ============================================================ Self-Discover

@router.post("/reasoning/self_discover")
async def do_self_discover(payload: dict) -> dict[str, Any]:
    p = payload.get("problem")
    if not p:
        raise HTTPException(400, "problem required")
    ptype = payload.get("problem_type", "complex")
    plan = self_discover.plan(p, ptype)
    return plan.to_dict()


# ============================================================ Constitutional

@router.post("/reasoning/constitutional/check")
async def constitutional_check(payload: dict) -> dict[str, Any]:
    text = payload.get("text")
    if not text:
        raise HTTPException(400, "text required")
    return constitutional_ai.check_all(text).model_dump()


# ============================================================ Recursive refinement

@router.post("/reasoning/recursive_refinement")
async def recursive_refine(payload: dict) -> dict[str, Any]:
    sol = payload.get("solution")
    if not sol:
        raise HTTPException(400, "solution required")
    r = recursive_refinement.refine(
        sol, target_level=int(payload.get("target_level", 7)))
    return r.to_dict()


# ============================================================ Benchmarks

@router.post("/cognition/benchmarks/run")
async def run_benchmarks() -> dict[str, Any]:
    return await reasoning_benchmarks.run_all(get_pool())


@router.get("/cognition/benchmarks/latest")
async def benchmarks_latest() -> dict[str, Any]:
    return await reasoning_benchmarks.latest(get_pool())


# ============================================================ Health

@router.get("/cognition/health/report")
async def health_report() -> dict[str, Any]:
    return await cognitive_health_monitor.health_report(get_pool())


# ============================================================ Circuit breaker

@router.get("/cognition/circuit/recent")
async def circuit_recent(limit: int = 20) -> list[dict[str, Any]]:
    return await cognitive_circuit_breaker.recent(get_pool(), limit=limit)


# ============================================================ Cache

@router.get("/cognition/cache/stats")
async def cache_stats() -> dict[str, Any]:
    return await reasoning_cache_semantic.stats(get_pool())


@router.post("/cognition/cache/invalidate_all")
async def cache_invalidate() -> dict[str, Any]:
    n = await reasoning_cache_semantic.invalidate_all(get_pool())
    return {"invalidated": n}


# ============================================================ Adversarial

@router.post("/cognition/adversarial/run")
async def adversarial_run() -> dict[str, Any]:
    return await adversarial_reasoning_tester.run_all(get_pool())


# ============================================================ Dependencies

@router.get("/cognition/dependencies/{trace_id}/descendants")
async def deps_descendants(trace_id: str) -> list[dict[str, Any]]:
    return await cognitive_dependency_graph.descendants(get_pool(), trace_id)


@router.post("/cognition/dependencies/invalidate_cascade/{trace_id}")
async def deps_invalidate(trace_id: str) -> dict[str, Any]:
    return await cognitive_dependency_graph.invalidate_cascade(
        get_pool(), trace_id)


# ============================================================ Load

@router.get("/cognition/load/snapshot")
async def load_snapshot() -> dict[str, Any]:
    return await cognitive_load_balancer.snapshot(get_pool())


# ============================================================ Override

@router.post("/cognition/override")
async def do_cog_override(payload: dict) -> dict[str, Any]:
    try:
        i = await human_reasoning_override.override_reasoning(
            get_pool(),
            trace_id=payload["trace_id"], human_id=payload.get("human_id", "ahmed"),
            new_decision=payload.get("new_decision", {}),
            justification=payload.get("justification", ""),
            impact_level=payload.get("impact_level", "medium"))
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return {"override_id": i}


@router.get("/cognition/override/list")
async def list_cog_overrides(limit: int = 20) -> list[dict[str, Any]]:
    return await human_reasoning_override.list_overrides(get_pool(), limit=limit)


# ============================================================ Reproducibility

@router.post("/cognition/reproducibility/replay")
async def repro_replay(sample_size: int = 50) -> dict[str, Any]:
    return await reasoning_reproducibility_test.replay_traces(
        get_pool(), sample_size=sample_size)


@router.get("/cognition/reproducibility/latest")
async def repro_latest() -> list[dict[str, Any]]:
    return await reasoning_reproducibility_test.latest_runs(get_pool())


# ============================================================ Frontier

@router.get("/cognition/frontier/catalog")
async def frontier_catalog() -> dict[str, Any]:
    return frontier_knowledge.catalog()
