"""Dependencies FastAPI pour les routes /admin/*.

- `get_current_admin` : verifie X-Admin-Token contre UBA_ADMIN_TOKEN.
- `AdminAuditLogger`   : INSERT chaque action override dans admin_actions.
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdminPrincipal:
    admin_id: str             # par defaut "ahmed" tant que RBAC non branche
    token_hint: str           # 4 derniers chars du token, jamais le brut


def _hint(token: str) -> str:
    return f"...{token[-4:]}" if len(token) >= 8 else "..."


async def get_current_admin(
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> AdminPrincipal:
    """Auth admin par token statique (stopgap V9N, voir ADR-17).

    Le token est lu via os.environ['UBA_ADMIN_TOKEN'] a chaque requete.
    Une eventuelle rotation prend effet immediat (pas de cache).
    """
    expected = os.environ.get("UBA_ADMIN_TOKEN", "").strip()
    if not expected:
        # Si l'env n'est pas configuree, on rejette TOUT pour eviter
        # un mode "admin libre" par megarde.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "UBA_ADMIN_TOKEN non configure",
        )
    if not x_admin_token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "X-Admin-Token requis",
        )
    if not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Admin token invalide",
        )
    return AdminPrincipal(admin_id="ahmed", token_hint=_hint(x_admin_token))


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
                json.dumps(payload or {}, sort_keys=True,
                           ensure_ascii=False, default=str),
                admin.token_hint,
            )
        logger.info(
            "admin_action admin=%s action=%s target=%s/%s",
            admin.admin_id, action_type, target_type, target_id,
        )
        return row["action_id"]


def get_admin_audit_logger() -> AdminAuditLogger:
    """Construit le logger sur le pool global. Override-able dans les tests."""
    return AdminAuditLogger(get_pool())
