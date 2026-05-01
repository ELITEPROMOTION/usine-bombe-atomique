"""Endpoints /admin/payments/* — failed payments listing for n8n dunning.

Phase 2 V9 production : ajoute l'endpoint manquant identifie en 9Q
(workflow 04 payment_retry).
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.database import get_pool
from app.routers.admin.dependencies import AdminPrincipal, get_current_admin

router = APIRouter(prefix="/admin/payments", tags=["admin-payments"])

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
AdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]


class PaymentListItem(BaseModel):
    payment_id: UUID
    project_id: str
    amount_cents: int = Field(ge=0)
    currency: str
    status: str
    owner_email: str
    country: str
    created_at: datetime
    paid_at: datetime | None


@router.get("", response_model=list[PaymentListItem])
async def list_payments(
    _admin: AdminDep,
    pool: PoolDep,
    payment_status: str | None = Query(default=None, alias="status"),
    min_age_hours: int = Query(default=0, ge=0, le=24 * 30),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PaymentListItem]:
    """Liste les paiements filtrables par status + age minimum.

    Consomme par n8n workflow 04 (payment_retry) avec
    `?status=failed&min_age_hours=6`.
    """
    where_clauses = []
    params: list = []
    idx = 1

    if payment_status:
        where_clauses.append(f"status = ${idx}")
        params.append(payment_status)
        idx += 1
    if min_age_hours > 0:
        where_clauses.append(
            f"created_at < NOW() - (${idx} || ' hours')::interval",
        )
        params.append(str(min_age_hours))
        idx += 1

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    params.append(limit)

    # where_sql + idx construits depuis whitelist statique (status enum +
    # int range typed Pydantic), pas de SQL injection possible
    base = (
        "SELECT payment_id, project_id, amount_cents, currency, status, "
        "owner_email, country, created_at, paid_at "
        "FROM payments WHERE "
    )
    sql = base + where_sql + " ORDER BY created_at DESC LIMIT $" + str(idx)  # nosec B608
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [PaymentListItem(**dict(r)) for r in rows]
