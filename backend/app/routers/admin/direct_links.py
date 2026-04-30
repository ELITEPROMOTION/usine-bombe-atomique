"""Endpoints /admin/direct-links/* : list + revoke."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_pool
from app.routers.admin._schemas import AuditedActionResponse, DirectLinkListItem
from app.routers.admin.dependencies import (
    AdminAuditLogger,
    AdminPrincipal,
    get_admin_audit_logger,
    get_current_admin,
)

router = APIRouter(prefix="/admin/direct-links", tags=["admin-direct-links"])

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
AdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]
AuditDep = Annotated[AdminAuditLogger, Depends(get_admin_audit_logger)]


@router.get("", response_model=list[DirectLinkListItem])
async def list_links(
    _admin: AdminDep,
    pool: PoolDep,
    action_type: str | None = None,
    only_active: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DirectLinkListItem]:
    async with pool.acquire() as conn:
        if action_type and only_active:
            rows = await conn.fetch(
                """
                SELECT link_id, action_type, target_id, principal_id,
                       single_use, consumed_at, revoked_at, expires_at, created_at
                  FROM direct_links
                 WHERE action_type = $1
                   AND consumed_at IS NULL AND revoked_at IS NULL
                   AND expires_at > NOW()
                 ORDER BY created_at DESC LIMIT $2
                """, action_type, limit,
            )
        elif action_type:
            rows = await conn.fetch(
                """
                SELECT link_id, action_type, target_id, principal_id,
                       single_use, consumed_at, revoked_at, expires_at, created_at
                  FROM direct_links
                 WHERE action_type = $1
                 ORDER BY created_at DESC LIMIT $2
                """, action_type, limit,
            )
        elif only_active:
            rows = await conn.fetch(
                """
                SELECT link_id, action_type, target_id, principal_id,
                       single_use, consumed_at, revoked_at, expires_at, created_at
                  FROM direct_links
                 WHERE consumed_at IS NULL AND revoked_at IS NULL
                   AND expires_at > NOW()
                 ORDER BY created_at DESC LIMIT $1
                """, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT link_id, action_type, target_id, principal_id,
                       single_use, consumed_at, revoked_at, expires_at, created_at
                  FROM direct_links
                 ORDER BY created_at DESC LIMIT $1
                """, limit,
            )
    return [DirectLinkListItem(**dict(r)) for r in rows]


@router.post(
    "/{link_id}/revoke",
    response_model=AuditedActionResponse,
)
async def revoke_link(
    link_id: UUID,
    admin: AdminDep,
    pool: PoolDep,
    auditor: AuditDep,
    reason: str = Query(default="admin override", min_length=1, max_length=500),
) -> AuditedActionResponse:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE direct_links
               SET revoked_at = NOW(), revocation_reason = $2
             WHERE link_id = $1 AND revoked_at IS NULL
            RETURNING link_id
            """,
            link_id, reason[:500],
        )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "direct_link introuvable ou deja revoque",
        )
    action_id = await auditor.log(
        admin=admin, action_type="revoke_direct_link",
        target_type="direct_link", target_id=str(link_id),
        payload={"reason": reason},
    )
    return AuditedActionResponse(
        action_id=action_id, target_type="direct_link",
        target_id=str(link_id), timestamp=datetime.now(UTC),
    )
