"""Generateur de liens directs vers les livrables d'un projet.

API minimaliste :
- `inject_for_project(project_id, deliverables)` cree N liens directs
  (un par deliverable) avec action_type='deliverable_download', target_id
  = project_id, metadata = {project_name, deliverable_name, ...}.
- Verifie que le projet existe ET est dans un etat permettant la livraison
  (status in {delivered, in_production}).

Le DirectLinkGenerator (9A) gere la persistance + audit. Ce module est
un orchestrateur leger qui ajoute une garde metier (state du projet).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field

from app.saas_factory.direct_links.direct_link_generator import (
    DirectLinkGenerator,
    IssuedLink,
)

logger = logging.getLogger(__name__)


DEFAULT_DELIVERABLE_TTL = timedelta(days=7)
ELIGIBLE_PROJECT_STATUSES: frozenset[str] = frozenset({
    "delivered", "in_production",
})


class ProjectNotDeliverableError(RuntimeError):
    """Le projet n'existe pas ou n'est pas dans un etat livrable."""


class DeliverableMetadata(BaseModel):
    """1 ligne par fichier/livrable a generer."""
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=40)        # 'frontend', 'admin', 'api', ...
    description: str = Field(default="", max_length=500)


@dataclass(frozen=True)
class InjectedDeliverable:
    project_id: UUID
    deliverable_name: str
    direct_link_id: UUID
    url: str
    expires_at: datetime
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DeliverableLinkInjector:
    """Genere des direct_links pour les livrables d'un projet."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        link_generator: DirectLinkGenerator,
    ) -> None:
        self._pool = pool
        self._gen = link_generator

    async def inject_for_project(
        self,
        project_id: UUID,
        *,
        deliverables: list[DeliverableMetadata],
        ttl: timedelta = DEFAULT_DELIVERABLE_TTL,
        owner_email_override: str | None = None,
    ) -> list[InjectedDeliverable]:
        """Cree N liens (un par deliverable). Echoue si projet invalide."""
        if not deliverables:
            raise ValueError("deliverables non vide requis")

        # 1. Verifier eligibilite du projet
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT project_id, owner_email, title, status
                  FROM projects
                 WHERE project_id = $1
                """,
                project_id,
            )
        if row is None:
            raise ProjectNotDeliverableError(
                f"project {project_id} introuvable"
            )
        if row["status"] not in ELIGIBLE_PROJECT_STATUSES:
            raise ProjectNotDeliverableError(
                f"project {project_id} status={row['status']!r} "
                f"hors {sorted(ELIGIBLE_PROJECT_STATUSES)}",
            )

        owner_email = owner_email_override or row["owner_email"]
        project_title = row["title"]

        # 2. Creer un direct_link par deliverable
        injected: list[InjectedDeliverable] = []
        for d in deliverables:
            metadata: dict[str, Any] = {
                "project_name": project_title,
                "deliverable_name": d.name,
                "deliverable_kind": d.kind,
                "deliverable_description": d.description,
                "owner_email": owner_email,
            }
            link: IssuedLink = await self._gen.issue(
                action_type="deliverable_download",
                target_id=str(project_id),
                principal_id=owner_email,
                metadata=metadata,
                ttl=ttl,
            )
            injected.append(InjectedDeliverable(
                project_id=project_id,
                deliverable_name=d.name,
                direct_link_id=link.link_id,
                url=link.url,
                expires_at=link.expires_at,
            ))

        logger.info(
            "deliverables.injected project=%s count=%d ttl_days=%d",
            project_id, len(injected), ttl.days,
        )
        return injected

    async def list_active_for_project(
        self, project_id: UUID,
    ) -> list[dict[str, Any]]:
        """Liste les liens deliverable_download actifs pour un projet."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT link_id, target_id, principal_id, expires_at, created_at,
                       metadata_json
                  FROM direct_links
                 WHERE action_type = 'deliverable_download'
                   AND target_id = $1
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                   AND expires_at > NOW()
                 ORDER BY created_at DESC
                """,
                str(project_id),
            )
        return [dict(r) for r in rows]
