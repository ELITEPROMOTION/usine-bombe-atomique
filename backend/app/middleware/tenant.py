"""Tenant middleware V4.1 - extrait tenant_id du JWT et injecte en BDD.

Sur chaque requete authentifiee :
1. Decode le JWT, resout `user.tenant_id` + `user.is_super_admin` en DB.
2. Expose ces infos dans `request.state` pour les handlers.
3. Pour chaque query asyncpg : `SET LOCAL app.tenant_id = '<uuid>'`
   et `SET LOCAL app.is_super_admin = 'on'|'off'` via un pool helper.

Super-admin = bypass RLS (utilisateur Ahmed Dendani).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import Request
from jose import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings
from app.database import get_pool

logger = logging.getLogger(__name__)

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"


class TenantMiddleware(BaseHTTPMiddleware):
    """Decode JWT Authorization et attache tenant_id / is_super_admin au state."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._settings = get_settings()

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        request.state.tenant_id = DEFAULT_TENANT
        request.state.user_id = None
        request.state.is_super_admin = False
        request.state.tenant_code = "default"

        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
            try:
                payload = jwt.decode(
                    token, self._settings.JWT_SECRET,
                    algorithms=[self._settings.JWT_ALGORITHM],
                )
                user_id = payload.get("sub")
                if user_id:
                    request.state.user_id = user_id
                    await _hydrate_tenant(request, user_id)
            except Exception as exc:
                logger.debug("tenant middleware JWT decode skipped: %s", exc)
        return await call_next(request)


async def _hydrate_tenant(request: Request, user_id: str) -> None:
    try:
        pool = get_pool()
    except RuntimeError:
        return
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.tenant_id, u.is_super_admin, t.code
            FROM users u
            LEFT JOIN tenants t ON t.id = u.tenant_id
            WHERE u.id = $1
            """,
            UUID(user_id),
        )
    if not row:
        return
    request.state.tenant_id = str(row["tenant_id"])
    request.state.is_super_admin = bool(row["is_super_admin"])
    request.state.tenant_code = row["code"] or "default"


async def apply_session_vars(conn: Any, request: Request) -> None:
    """Helper : pose `app.tenant_id` + `app.is_super_admin` sur une connexion."""
    tenant_id = getattr(request.state, "tenant_id", DEFAULT_TENANT)
    is_super = getattr(request.state, "is_super_admin", False)
    await conn.execute(
        f"SET LOCAL app.tenant_id = '{tenant_id}'",
    )
    await conn.execute(
        f"SET LOCAL app.is_super_admin = '{'on' if is_super else 'off'}'",
    )
