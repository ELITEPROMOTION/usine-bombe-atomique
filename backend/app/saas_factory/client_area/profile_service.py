"""ClientProfileService : profile + consents + GDPR triggers.

Sources :
- `projects` (owner_email, company_name, locale)
- `user_consents` (V9I migration 050) via ConsentManager
- `data_export_requests`, `data_erasure_requests` via GDPRExporter / GDPREraser
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from app.saas_factory.client_area.dashboard_service import (
    ProjectNotFoundError,
)
from app.saas_factory.legal.consent_manager import (
    ConsentAlreadyRecordedError,
    ConsentManager,
)
from app.saas_factory.legal.gdpr_erasure import GDPREraser
from app.saas_factory.legal.types import ConsentScope

logger = logging.getLogger(__name__)

__all__ = ("ClientProfileService", "ClientProfileRow", "ProjectNotFoundError")


@dataclass(frozen=True)
class ClientProfileRow:
    owner_email: str
    company_name: str
    locale: str
    consent_marketing: bool
    consent_analytics: bool
    created_at: datetime


class ClientProfileService:
    """Profile + consents + GDPR pour un project_id donne."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._consents = ConsentManager(pool)
        self._eraser = GDPREraser(pool)

    async def get_profile(self, project_id: UUID) -> ClientProfileRow:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT owner_email, company_name, locale, created_at
                  FROM projects
                 WHERE project_id = $1
                """,
                project_id,
            )
            if row is None:
                raise ProjectNotFoundError(
                    f"project {project_id} introuvable",
                )
            consent_rows = await conn.fetch(
                """
                SELECT scope, revoked_at
                  FROM user_consents
                 WHERE owner_email = $1
                """,
                row["owner_email"].lower(),
            )

        active = {c["scope"] for c in consent_rows if c["revoked_at"] is None}
        return ClientProfileRow(
            owner_email=row["owner_email"],
            company_name=row["company_name"],
            locale=row["locale"],
            consent_marketing=ConsentScope.MARKETING_OPT_IN.value in active,
            consent_analytics=ConsentScope.COOKIE_ANALYTICS.value in active,
            created_at=row["created_at"],
        )

    async def update_consents(
        self,
        project_id: UUID,
        *,
        consent_marketing: bool,
        consent_analytics: bool,
        ip: str | None = None,
    ) -> ClientProfileRow:
        profile = await self.get_profile(project_id)
        await self._sync(
            profile.owner_email, ConsentScope.MARKETING_OPT_IN,
            target=consent_marketing, ip=ip,
        )
        await self._sync(
            profile.owner_email, ConsentScope.COOKIE_ANALYTICS,
            target=consent_analytics, ip=ip,
        )
        return await self.get_profile(project_id)

    async def _sync(
        self, owner_email: str, scope: ConsentScope, *,
        target: bool, ip: str | None,
    ) -> None:
        import contextlib

        if target:
            with contextlib.suppress(ConsentAlreadyRecordedError):
                await self._consents.record_consent(
                    owner_email=owner_email,
                    scope=scope,
                    doc_version="v1",
                    ip=ip,
                )
        else:
            await self._consents.revoke_consent(
                owner_email=owner_email,
                scope=scope,
                reason="client.toggle",
            )

    async def request_export(
        self, project_id: UUID, requester_email: str | None,
    ) -> dict[str, str]:
        """Insere une `data_export_requests` row (status pending)."""
        async with self._pool.acquire() as conn:
            check = await conn.fetchrow(
                "SELECT 1 FROM projects WHERE project_id = $1",
                project_id,
            )
            if check is None:
                raise ProjectNotFoundError(
                    f"project {project_id} introuvable",
                )
            row = await conn.fetchrow(
                """
                INSERT INTO data_export_requests (
                    project_id, requester_email, status
                ) VALUES ($1, $2, 'pending')
                RETURNING request_id
                """,
                project_id, (requester_email or "").lower() or None,
            )
        logger.info(
            "gdpr.export_requested project=%s by=%s",
            project_id, requester_email or "anonymous",
        )
        return {"request_id": str(row["request_id"])}

    async def request_erasure(
        self, project_id: UUID, *, reason: str,
        requester_email: str | None,
    ) -> dict[str, str]:
        """Delegue a GDPREraser.request_erasure (cf. ADR-26)."""
        rec = await self._eraser.request_erasure(
            project_id=project_id,
            reason=reason,
            requester_email=requester_email,
        )
        return {
            "request_id": str(rec.request_id),
            "executable_after": rec.executable_after.isoformat(),
        }
