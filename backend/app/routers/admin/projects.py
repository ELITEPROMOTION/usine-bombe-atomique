"""Endpoints /admin/projects/* : list + status override."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_pool
from app.routers.admin._schemas import (
    AuditedActionResponse,
    ProjectListItem,
    ProjectStatusOverride,
)
from app.routers.admin.dependencies import (
    AdminAuditLogger,
    AdminPrincipal,
    get_admin_audit_logger,
    get_current_admin,
)

router = APIRouter(prefix="/admin/projects", tags=["admin-projects"])

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
AdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]
AuditDep = Annotated[AdminAuditLogger, Depends(get_admin_audit_logger)]


# Doit matcher la contrainte CHECK de la migration 047.
ALLOWED_STATUSES: Final[frozenset[str]] = frozenset({
    "submitted", "qualifying", "assembled", "paywall_pending",
    "in_production", "delivered", "archived", "cancelled",
})


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    _admin: AdminDep,
    pool: PoolDep,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ProjectListItem]:
    async with pool.acquire() as conn:
        if status_filter:
            rows = await conn.fetch(
                """
                SELECT project_id, owner_email, company_name, pack_id_hint,
                       title, status, created_at
                  FROM projects
                 WHERE status = $1
                 ORDER BY created_at DESC LIMIT $2
                """, status_filter, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT project_id, owner_email, company_name, pack_id_hint,
                       title, status, created_at
                  FROM projects
                 ORDER BY created_at DESC LIMIT $1
                """, limit,
            )
    return [ProjectListItem(**dict(r)) for r in rows]


@router.get("/inactive", response_model=list[ProjectListItem])
async def list_inactive_projects(
    _admin: AdminDep,
    pool: PoolDep,
    days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ProjectListItem]:
    """Phase 2 V9 — Projets actifs sans audit_event depuis N jours.

    Consomme par n8n workflow 06 (churn alert).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.project_id, p.owner_email, p.company_name,
                   p.pack_id_hint, p.title, p.status, p.created_at
              FROM projects p
             WHERE p.status NOT IN ('cancelled', 'archived')
               AND NOT EXISTS (
                   SELECT 1 FROM audit_events ae
                    WHERE ae.payload_json->>'project_id' = p.project_id::text
                      AND ae.created_at > NOW() - ($1 || ' days')::interval
               )
             ORDER BY p.updated_at ASC
             LIMIT $2
            """, str(days), limit,
        )
    return [ProjectListItem(**dict(r)) for r in rows]


@router.patch(
    "/{project_id}/status",
    response_model=AuditedActionResponse,
)
async def override_status(
    project_id: UUID,
    payload: ProjectStatusOverride,
    admin: AdminDep,
    pool: PoolDep,
    auditor: AuditDep,
) -> AuditedActionResponse:
    if payload.new_status not in ALLOWED_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"new_status invalide. Autorises : {sorted(ALLOWED_STATUSES)}",
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE projects
               SET status = $2, updated_at = NOW()
             WHERE project_id = $1
            RETURNING project_id, status
            """,
            project_id, payload.new_status,
        )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"project {project_id} introuvable",
        )
    action_id = await auditor.log(
        admin=admin, action_type="override_project_status",
        target_type="project", target_id=str(project_id),
        payload={"new_status": payload.new_status, "reason": payload.reason},
    )
    return AuditedActionResponse(
        action_id=action_id, target_type="project",
        target_id=str(project_id), timestamp=datetime.now(UTC),
    )
