"""Dependencies FastAPI pour les routes /admin/*.

V9J : auth dual-mode :
1. JWT Bearer (`Authorization: Bearer <token>`) — verifie via JWT_ADMIN_SECRET
   + role embarque (admin/viewer/auditor) — Phase 9J ADR-22.
2. Token legacy (`X-Admin-Token: <token>`) — verifie via UBA_ADMIN_TOKEN
   — Phase 9N ADR-17, conserve en backward-compat.

Si **aucune** des deux variables d'env n'est configuree, on rejette tout
en 503 (fail-closed).

`AdminAuditLogger` : INSERT chaque action override dans `admin_actions`.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import asyncpg
from fastapi import Header, HTTPException, status

from app.database import get_pool
from app.security.jwt_admin import (
    AdminRole,
    JWTAdminError,
    JWTConfigMissingError,
    is_jwt_mode_enabled,
    verify_admin_token,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdminPrincipal:
    admin_id: str
    token_hint: str
    role: AdminRole = AdminRole.ADMIN     # default : full access pour legacy
    auth_mode: str = "legacy"             # 'jwt' | 'legacy'


def _hint(token: str) -> str:
    return f"...{token[-4:]}" if len(token) >= 8 else "..."


def _strip_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def get_current_admin(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> AdminPrincipal:
    """Auth admin dual-mode (JWT + legacy token).

    Ordre de priorite : JWT Bearer > X-Admin-Token. Si aucun mode n'est
    configure cote env, on rejette en 503 (fail-closed).
    """
    jwt_enabled = is_jwt_mode_enabled()
    legacy_token = os.environ.get("UBA_ADMIN_TOKEN", "").strip()

    if not jwt_enabled and not legacy_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Auth admin non configuree (JWT_ADMIN_SECRET ou UBA_ADMIN_TOKEN requis)",
        )

    # 1. Tentative JWT Bearer
    bearer = _strip_bearer(authorization)
    if bearer and jwt_enabled:
        try:
            payload = verify_admin_token(bearer)
        except JWTConfigMissingError as exc:    # pragma: no cover — defense
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, str(exc),
            ) from exc
        except JWTAdminError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"JWT invalide: {exc}",
            ) from exc
        return AdminPrincipal(
            admin_id=payload.sub,
            token_hint=_hint(bearer),
            role=payload.role,
            auth_mode="jwt",
        )

    # 2. Fallback legacy X-Admin-Token
    if not legacy_token:
        # Bearer fourni mais JWT pas configure, OU rien fourni.
        if bearer:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "JWT_ADMIN_SECRET requis pour Authorization: Bearer",
            )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentification requise (Authorization Bearer ou X-Admin-Token)",
        )
    if not x_admin_token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "X-Admin-Token requis (ou Authorization: Bearer)",
        )
    if not secrets.compare_digest(x_admin_token, legacy_token):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Admin token invalide",
        )
    return AdminPrincipal(
        admin_id="ahmed",
        token_hint=_hint(x_admin_token),
        role=AdminRole.ADMIN,
        auth_mode="legacy",
    )


def require_role(*roles: AdminRole):
    """Factory de dependency qui exige un des roles fournis.

    Usage :
        require_admin = require_role(AdminRole.ADMIN)
        @router.post("/x")
        async def x(principal: AdminPrincipal = Depends(require_admin)): ...
    """
    allowed = frozenset(roles)
    from fastapi import Depends

    async def _dep(
        principal: AdminPrincipal = Depends(get_current_admin),  # noqa: B008
    ) -> AdminPrincipal:
        if principal.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role {principal.role.value!r} insuffisant "
                f"(requis : {sorted(r.value for r in allowed)})",
            )
        return principal

    return _dep


class AdminAuditLogger:
    """INSERT dans admin_actions a chaque action override."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def log(
        self,
        *,
        admin: AdminPrincipal,
        action_type: str,
        target_type: str,
        target_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> UUID:
        meta = dict(payload or {})
        meta["_auth_mode"] = admin.auth_mode
        meta["_role"] = admin.role.value
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO admin_actions (
                    admin_id, action_type, target_type, target_id,
                    payload_json, token_hint
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                RETURNING action_id
                """,
                admin.admin_id, action_type[:64], target_type[:64],
                (target_id or "")[:120] or None,
                json.dumps(meta, sort_keys=True,
                           ensure_ascii=False, default=str),
                admin.token_hint,
            )
        logger.info(
            "admin_action admin=%s action=%s target=%s/%s mode=%s role=%s",
            admin.admin_id, action_type, target_type, target_id,
            admin.auth_mode, admin.role.value,
        )
        return row["action_id"]


def get_admin_audit_logger() -> AdminAuditLogger:
    return AdminAuditLogger(get_pool())
