"""Endpoints /admin/onboarding/* : funnel + sessions list."""
from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.database import get_pool
from app.routers.admin._schemas import (
    OnboardingFunnelItem,
    OnboardingSessionListItem,
)
from app.routers.admin.dependencies import (
    AdminPrincipal,
    get_current_admin,
)

router = APIRouter(prefix="/admin/onboarding", tags=["admin-onboarding"])

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
AdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]


@router.get("/funnel", response_model=list[OnboardingFunnelItem])
async def funnel(_admin: AdminDep, pool: PoolDep) -> list[OnboardingFunnelItem]:
    """Conversion funnel : pour chaque etape, in_progress/abandoned/submitted."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT current_step, in_progress, abandoned, submitted
              FROM v_onboarding_funnel
             ORDER BY current_step
            """,
        )
    return [OnboardingFunnelItem(**dict(r)) for r in rows]


@router.get("/sessions", response_model=list[OnboardingSessionListItem])
async def sessions(
    _admin: AdminDep,
    pool: PoolDep,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OnboardingSessionListItem]:
    async with pool.acquire() as conn:
        if status_filter:
            rows = await conn.fetch(
                """
                SELECT session_id, current_step, status, owner_email,
                       project_id, started_at, submitted_at
                  FROM client_onboarding_sessions
                 WHERE status = $1
                 ORDER BY started_at DESC LIMIT $2
                """, status_filter, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT session_id, current_step, status, owner_email,
                       project_id, started_at, submitted_at
                  FROM client_onboarding_sessions
                 ORDER BY started_at DESC LIMIT $1
                """, limit,
            )
    return [OnboardingSessionListItem(**dict(r)) for r in rows]
