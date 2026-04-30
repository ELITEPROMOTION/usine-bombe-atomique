"""Endpoints /admin/handoffs/* : list + cancel + escalate."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_pool
from app.routers.admin._schemas import (
    AuditedActionResponse,
    HandoffListItem,
    HandoffOverrideRequest,
)
from app.routers.admin.dependencies import (
    AdminAuditLogger,
    AdminPrincipal,
    get_admin_audit_logger,
    get_current_admin,
)

router = APIRouter(prefix="/admin/handoffs", tags=["admin-handoffs"])

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
AdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]
AuditDep = Annotated[AdminAuditLogger, Depends(get_admin_audit_logger)]


@router.get("", response_model=list[HandoffListItem])
async def list_handoffs(
    _admin: AdminDep,
    pool: PoolDep,
    state: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[HandoffListItem]:
    async with pool.acquire() as conn:
        if state:
            rows = await conn.fetch(
                """
                SELECT handoff_id, project_id, action_type, state, target_email,
                       title, expires_at, created_at
                  FROM handoff_requests
                 WHERE state = $1
                 ORDER BY created_at DESC LIMIT $2
                """, state, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT handoff_id, project_id, action_type, state, target_email,
                       title, expires_at, created_at
                  FROM handoff_requests
                 ORDER BY created_at DESC LIMIT $1
                """, limit,
            )
    return [HandoffListItem(**dict(r)) for r in rows]


async def _force_state_transition(
    pool: asyncpg.Pool,
    handoff_id: UUID,
    new_state: str,
    *,
    valid_from: tuple[str, ...],
    extra_payload_json: str | None = None,
) -> bool:
    """UPDATE conditionnel : autorise uniquement depuis valid_from."""
    async with pool.acquire() as conn:
        if extra_payload_json:
            row = await conn.fetchrow(
                """
                UPDATE handoff_requests
                   SET state = $2, updated_at = NOW(),
                       payload_json = payload_json || $3::jsonb
                 WHERE handoff_id = $1 AND state = ANY($4::text[])
                RETURNING handoff_id
                """,
                handoff_id, new_state, extra_payload_json, list(valid_from),
            )
        else:
            row = await conn.fetchrow(
                """
                UPDATE handoff_requests
                   SET state = $2, updated_at = NOW()
                 WHERE handoff_id = $1 AND state = ANY($3::text[])
                RETURNING handoff_id
                """,
                handoff_id, new_state, list(valid_from),
            )
    return row is not None


@router.post(
    "/{handoff_id}/cancel",
    response_model=AuditedActionResponse,
)
async def cancel_handoff(
    handoff_id: UUID,
    payload: HandoffOverrideRequest,
    admin: AdminDep,
    pool: PoolDep,
    auditor: AuditDep,
) -> AuditedActionResponse:
    import json
    extra = json.dumps(
        {"cancel_reason": payload.reason[:500], "by": "admin"},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    ok = await _force_state_transition(
        pool, handoff_id, "cancelled",
        valid_from=("requested", "notified", "acknowledged", "escalated"),
        extra_payload_json=extra,
    )
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "handoff introuvable ou deja terminal",
        )
    action_id = await auditor.log(
        admin=admin, action_type="cancel_handoff",
        target_type="handoff", target_id=str(handoff_id),
        payload={"reason": payload.reason},
    )
    return AuditedActionResponse(
        action_id=action_id, target_type="handoff",
        target_id=str(handoff_id), timestamp=datetime.now(UTC),
    )


@router.post(
    "/{handoff_id}/escalate",
    response_model=AuditedActionResponse,
)
async def escalate_handoff(
    handoff_id: UUID,
    payload: HandoffOverrideRequest,
    admin: AdminDep,
    pool: PoolDep,
    auditor: AuditDep,
) -> AuditedActionResponse:
    ok = await _force_state_transition(
        pool, handoff_id, "escalated",
        valid_from=("notified", "acknowledged"),
    )
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "handoff introuvable ou pas en etat notified/acknowledged",
        )
    action_id = await auditor.log(
        admin=admin, action_type="escalate_handoff",
        target_type="handoff", target_id=str(handoff_id),
        payload={"reason": payload.reason},
    )
    return AuditedActionResponse(
        action_id=action_id, target_type="handoff",
        target_id=str(handoff_id), timestamp=datetime.now(UTC),
    )
