"""Router /intelligence V5.8 - active learning + XAI + KG + cache evolued."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import get_pool
from app.intelligence.active_learner import ActiveLearner
from app.intelligence.cache_evolved import EvolvedCacheService
from app.intelligence.explainer import DecisionExplainer
from app.intelligence.knowledge_graph import (
    EntityType,
    KnowledgeGraph,
    RelationType,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence_v5_8"])


# ============================================================================
# Active Learning
# ============================================================================

@router.get("/active-learning/pending")
async def al_pending(domain_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    learner = ActiveLearner(get_pool())
    loops = await learner.list_pending(domain_id=domain_id, limit=limit)
    return {"count": len(loops), "loops": [lp.to_dict() for lp in loops]}


@router.post("/active-learning/submit")
async def al_submit(body: dict[str, Any]) -> dict[str, Any]:
    learner = ActiveLearner(get_pool())
    loop_id = await learner.submit_loop(
        decision_id=body.get("decision_id"),
        domain_id=body.get("domain_id"),
        input_context=body.get("input_context", {}),
        original_output=body.get("original_output", {}),
        original_confidence=float(body.get("original_confidence", 0.0)),
        proposals=body.get("proposals"),
    )
    return {"loop_id": loop_id, "submitted": loop_id != -1}


@router.post("/active-learning/feedback/{loop_id}")
async def al_feedback(loop_id: int, body: dict[str, Any]) -> dict[str, Any]:
    learner = ActiveLearner(get_pool())
    loop = await learner.apply_feedback(
        loop_id=loop_id,
        choice=body.get("choice", {}),
        feedback_text=body.get("feedback_text"),
        agreement_score=body.get("agreement_score"),
        status=body.get("status", "accepted"),
    )
    if loop is None:
        raise HTTPException(404, f"loop {loop_id} not found or not pending")
    return loop.to_dict()


@router.get("/active-learning/metrics")
async def al_metrics(
    window_days: int = 30, domain_id: str | None = None,
) -> dict[str, Any]:
    learner = ActiveLearner(get_pool())
    return await learner.metrics(window_days=window_days, domain_id=domain_id)


@router.get("/active-learning/history")
async def al_history(days: int = 30, limit: int = 100) -> dict[str, Any]:
    learner = ActiveLearner(get_pool())
    loops = await learner.history(days=days, limit=limit)
    return {"count": len(loops), "loops": [lp.to_dict() for lp in loops]}


# ============================================================================
# XAI Explainer
# ============================================================================

@router.post("/explain/decision")
async def explain_decision(body: dict[str, Any]) -> dict[str, Any]:
    """Genere (ou reutilise) l'explication d'une decision."""
    from app.domains import RULES_ENGINE
    explainer = DecisionExplainer(get_pool(), rules_engine=RULES_ENGINE)
    return await explainer.explain(
        decision_id=body.get("decision_id"),
        domain_id=body["domain_id"],
        operation=body.get("operation", "process"),
        input_context=body.get("input_context", {}),
        output=body.get("output", {}),
    )


@router.get("/explain/decision/{decision_id}")
async def explain_get(decision_id: str) -> dict[str, Any]:
    explainer = DecisionExplainer(get_pool())
    cached = await explainer.get_cached(decision_id)
    if cached is None:
        raise HTTPException(404, f"explanation for {decision_id} not found")
    return cached


# ============================================================================
# Knowledge Graph
# ============================================================================

@router.get("/graph/stats")
async def kg_stats() -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    return await kg.stats()


@router.post("/graph/populate")
async def kg_populate() -> dict[str, Any]:
    """Seed graph depuis les 5 domaines + rules."""
    from app.intelligence.knowledge_graph import populate_from_domains
    kg = KnowledgeGraph(get_pool())
    return await populate_from_domains(kg)


@router.get("/graph/node/{node_id}")
async def kg_node(node_id: str, direction: str = "both") -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    node = await kg.get_node(node_id)
    if node is None:
        raise HTTPException(404, f"node {node_id} not found")
    neighbors = await kg.get_neighbors(node_id, direction=direction)
    return {
        "node": node.to_dict(),
        "neighbors_count": len(neighbors),
        "neighbors": neighbors,
    }


@router.get("/graph/path")
async def kg_path(from_node: str, to_node: str) -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    path = await kg.shortest_path(from_node, to_node)
    return {"path": path, "length": len(path) - 1 if path else None}


@router.get("/graph/subgraph/{node_id}")
async def kg_subgraph(node_id: str, depth: int = 2) -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    return await kg.subgraph(node_id, depth=min(depth, 4))


@router.get("/graph/contradictions")
async def kg_contradictions() -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    items = await kg.contradictions()
    return {"count": len(items), "contradictions": items}


@router.get("/graph/export")
async def kg_export() -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    return await kg.export()


@router.post("/graph/node")
async def kg_add_node(body: dict[str, Any]) -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    await kg.add_node(
        node_id=body["id"],
        node_type=EntityType(body["node_type"]),
        label=body["label"],
        attributes=body.get("attributes", {}),
    )
    return {"added": True, "id": body["id"]}


@router.post("/graph/edge")
async def kg_add_edge(body: dict[str, Any]) -> dict[str, Any]:
    kg = KnowledgeGraph(get_pool())
    await kg.add_edge(
        source_id=body["source_id"],
        target_id=body["target_id"],
        relation_type=RelationType(body["relation_type"]),
        weight=float(body.get("weight", 1.0)),
        attributes=body.get("attributes", {}),
    )
    return {"added": True}


# ============================================================================
# Cache semantique evolue
# ============================================================================

@router.get("/cache/metrics")
async def cache_metrics(domain: str | None = None) -> dict[str, Any]:
    svc = EvolvedCacheService(get_pool())
    return await svc.metrics(domain_id=domain)


@router.delete("/cache/invalidate/{domain}")
async def cache_invalidate(domain: str) -> dict[str, Any]:
    svc = EvolvedCacheService(get_pool())
    count = await svc.invalidate_domain(domain)
    return {"invalidated": count, "domain": domain}


@router.get("/cache/top_queries/{domain}")
async def cache_top_queries(domain: str, limit: int = 10) -> dict[str, Any]:
    svc = EvolvedCacheService(get_pool())
    items = await svc.top_queries(domain, limit=limit)
    return {"domain": domain, "top_queries": items}


@router.post("/cache/warm/{domain}")
async def cache_warm(domain: str, body: dict[str, Any]) -> dict[str, Any]:
    svc = EvolvedCacheService(get_pool())
    queries = body.get("queries", [])
    return await svc.warm(domain, queries)
