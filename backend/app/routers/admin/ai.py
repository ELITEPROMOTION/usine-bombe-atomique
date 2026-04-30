"""Endpoints /admin/ai/* : FinOps dashboard + AI router policy.

Lecture seule pour decisions/cost-dashboard. Override autorise pour la
policy AI router (impacte la production immediate).
"""
from __future__ import annotations

import json
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_pool
from app.routers.admin._schemas import (
    AICostDashboardItem,
    AIDecisionListItem,
    AIRouterPolicy,
    AIRouterPolicyOverride,
    AuditedActionResponse,
)
from app.routers.admin.dependencies import (
    AdminAuditLogger,
    AdminPrincipal,
    get_admin_audit_logger,
    get_current_admin,
)

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])


PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
AdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]
AuditDep = Annotated[AdminAuditLogger, Depends(get_admin_audit_logger)]


@router.get("/decisions", response_model=list[AIDecisionListItem])
async def list_decisions(
    _admin: AdminDep,
    pool: PoolDep,
    project_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AIDecisionListItem]:
    async with pool.acquire() as conn:
        if project_id:
            rows = await conn.fetch(
                """
                SELECT decision_id, project_id, requested_provider, actual_provider,
                       status, cost_usd::FLOAT8 AS cost_usd, tokens_in, tokens_out,
                       latency_ms, fallback_used, retries, loop_detected, created_at
                  FROM ai_decisions_log
                 WHERE project_id = $1
                 ORDER BY created_at DESC LIMIT $2
                """, project_id, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT decision_id, project_id, requested_provider, actual_provider,
                       status, cost_usd::FLOAT8 AS cost_usd, tokens_in, tokens_out,
                       latency_ms, fallback_used, retries, loop_detected, created_at
                  FROM ai_decisions_log
                 ORDER BY created_at DESC LIMIT $1
                """, limit,
            )
    return [AIDecisionListItem(**dict(r)) for r in rows]


@router.get("/cost-dashboard", response_model=list[AICostDashboardItem])
async def cost_dashboard(_admin: AdminDep, pool: PoolDep) -> list[AICostDashboardItem]:
    """Vue FinOps 24h : agrege par project_id (depuis v_ai_cost_24h)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT project_id, calls,
                   total_cost_usd::FLOAT8 AS total_cost_usd,
                   tokens_in, tokens_out, fallbacks, loops, errors
              FROM v_ai_cost_24h
             ORDER BY total_cost_usd DESC
            """,
        )
    return [AICostDashboardItem(**dict(r)) for r in rows]


@router.get(
    "/cost-by-project/{project_id}",
    response_model=AICostDashboardItem,
)
async def cost_by_project(
    project_id: str, _admin: AdminDep, pool: PoolDep,
) -> AICostDashboardItem:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT project_id, calls,
                   total_cost_usd::FLOAT8 AS total_cost_usd,
                   tokens_in, tokens_out, fallbacks, loops, errors
              FROM v_ai_cost_24h
             WHERE project_id = $1
            """,
            project_id,
        )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"aucun cout pour project={project_id} (24h)",
        )
    return AICostDashboardItem(**dict(row))


@router.get("/router-policy", response_model=AIRouterPolicy)
async def get_router_policy(_admin: AdminDep, pool: PoolDep) -> AIRouterPolicy:
    """Lit la policy en vigueur depuis platform_config.operations_json."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT operations_json FROM platform_config WHERE id = 1",
        )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "platform_config non initialise (Phase 9B requise)",
        )
    ops = row["operations_json"]
    if isinstance(ops, str):
        ops = json.loads(ops)
    weights = {
        "claude":     int(ops.get("ai_router_claude_pct", 0)),
        "perplexity": int(ops.get("ai_router_perplexity_pct", 0)),
        "manus":      int(ops.get("ai_router_manus_pct", 0)),
        "internal":   int(ops.get("ai_router_internal_pct", 0)),
    }
    return AIRouterPolicy(
        weights=weights,
        fallback_order=["claude", "perplexity", "manus", "internal"],
        allow_fallback=True,
        max_attempts_per_provider=3,
        base_delay_s=0.5,
    )


@router.post(
    "/router-policy",
    response_model=AuditedActionResponse,
    status_code=status.HTTP_200_OK,
)
async def override_router_policy(
    payload: AIRouterPolicyOverride,
    admin: AdminDep,
    pool: PoolDep,
    auditor: AuditDep,
) -> AuditedActionResponse:
    """Override les pourcentages du router (mutation platform_config)."""
    total = sum(int(v) for v in payload.weights.values())
    if total != 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"weights doivent sommer a 100 (actuel: {total})",
        )

    new_ops_partial: dict[str, Any] = {
        "ai_router_claude_pct":     int(payload.weights.get("claude", 0)),
        "ai_router_perplexity_pct": int(payload.weights.get("perplexity", 0)),
        "ai_router_manus_pct":      int(payload.weights.get("manus", 0)),
        "ai_router_internal_pct":   int(payload.weights.get("internal", 0)),
    }
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE platform_config
               SET operations_json = operations_json || $1::jsonb,
                   committed_at = NOW(),
                   committed_by = $2,
                   version = version + 1
             WHERE id = 1
            """,
            json.dumps(new_ops_partial, sort_keys=True,
                       ensure_ascii=False, default=str),
            admin.admin_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "platform_config non initialise",
        )

    action_id = await auditor.log(
        admin=admin,
        action_type="override_router_policy",
        target_type="platform_config",
        target_id="1",
        payload={"new_weights": new_ops_partial,
                 "fallback_order": payload.fallback_order,
                 "allow_fallback": payload.allow_fallback,
                 "max_attempts_per_provider": payload.max_attempts_per_provider},
    )
    from datetime import UTC, datetime
    return AuditedActionResponse(
        action_id=action_id,
        target_type="platform_config",
        target_id="1",
        timestamp=datetime.now(UTC),
    )
