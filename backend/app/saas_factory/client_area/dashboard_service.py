"""ClientDashboardService : project + milestones + activity.

Sources :
- `projects` (V9F migration 047)
- `audit_events` (V8 migration 007) — filtre via `payload_json->>'project_id'`

Aucune nouvelle table. Cf. ADR-33.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

import asyncpg

from ._milestones import derive_milestones, derive_next_milestone
from ._status_mapping import derive_progress_pct, derive_ui_status

logger = logging.getLogger(__name__)


# Estimation duree projet bout-en-bout (cf. _milestones.py m-delivery)
DEFAULT_PROJECT_DURATION_DAYS: Final[int] = 38


class ProjectNotFoundError(LookupError):
    """Project demande introuvable."""


@dataclass(frozen=True)
class ClientProjectRow:
    project_id: UUID
    pack_id: str
    pack_name: str
    status: str
    progress_pct: int
    created_at: datetime
    estimated_delivery_at: datetime
    owner_email: str
    company_name: str
    next_milestone: str
    next_milestone_due_at: datetime


@dataclass(frozen=True)
class ClientMilestoneRow:
    id: str
    label: str
    description: str
    due_at: datetime
    status: str


@dataclass(frozen=True)
class ClientActivityRow:
    id: str
    at: datetime
    kind: str
    title: str
    detail: str | None


_ACTION_TO_KIND: Final[dict[str, str]] = {
    "project.assembled":     "build",
    "project.in_production": "build",
    "project.delivered":     "deliverable",
    "payment.succeeded":     "payment",
    "payment.failed":        "payment",
    "invoice.issued":        "payment",
    "deliverable.released":  "deliverable",
    "handoff.requested":     "handoff",
    "handoff.escalated":     "handoff",
    "client.notified":       "comms",
}


_PACK_NAME_CATALOG: Final[dict[str, str]] = {
    "ecommerce_s": "E-Commerce S",
    "ecommerce_m": "E-Commerce M",
    "ecommerce_l": "E-Commerce L",
    "saas_s":      "SaaS Studio S",
    "saas_m":      "SaaS Studio M",
    "saas_l":      "SaaS Studio L",
    "mobile_app":  "Mobile App",
    "api_b2b":     "API B2B",
    "custom":      "Pack Custom",
}


def _pack_name_for(pack_id: str) -> str:
    return _PACK_NAME_CATALOG.get(
        pack_id, pack_id.replace("_", " ").title(),
    )


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


class ClientDashboardService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_project(self, project_id: UUID) -> ClientProjectRow:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT project_id, owner_email, company_name,
                       pack_id_hint, status, created_at, updated_at
                  FROM projects
                 WHERE project_id = $1
                """,
                project_id,
            )
        if row is None:
            raise ProjectNotFoundError(
                f"project {project_id} introuvable",
            )
        next_m = derive_next_milestone(row["status"], row["created_at"])
        next_label, next_due = (
            next_m if next_m is not None
            else ("Cloture", row["updated_at"])
        )
        eta = row["created_at"] + timedelta(
            days=DEFAULT_PROJECT_DURATION_DAYS,
        )
        return ClientProjectRow(
            project_id=row["project_id"],
            pack_id=row["pack_id_hint"],
            pack_name=_pack_name_for(row["pack_id_hint"]),
            status=derive_ui_status(row["status"]),
            progress_pct=derive_progress_pct(row["status"]),
            created_at=row["created_at"],
            estimated_delivery_at=eta,
            owner_email=row["owner_email"],
            company_name=row["company_name"],
            next_milestone=next_label,
            next_milestone_due_at=next_due,
        )

    async def list_milestones(
        self, project_id: UUID,
    ) -> list[ClientMilestoneRow]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, created_at FROM projects WHERE project_id = $1",
                project_id,
            )
        if row is None:
            raise ProjectNotFoundError(
                f"project {project_id} introuvable",
            )
        items = derive_milestones(
            project_id, row["status"], row["created_at"],
        )
        return [
            ClientMilestoneRow(
                id=m["id"], label=m["label"], description=m["description"],
                due_at=datetime.fromisoformat(m["due_at"]),
                status=m["status"],
            )
            for m in items
        ]

    async def list_activity(
        self, project_id: UUID, limit: int = 10,
    ) -> list[ClientActivityRow]:
        if limit < 1 or limit > 100:
            raise ValueError("limit doit etre dans [1..100]")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, action, created_at, payload_json
                  FROM audit_events
                 WHERE payload_json->>'project_id' = $1
                 ORDER BY created_at DESC
                 LIMIT $2
                """,
                str(project_id), limit,
            )
        out: list[ClientActivityRow] = []
        for r in rows:
            payload = _to_dict(r["payload_json"])
            title = payload.get("title") or r["action"]
            detail = payload.get("detail")
            out.append(ClientActivityRow(
                id=str(r["event_id"]),
                at=r["created_at"],
                kind=_ACTION_TO_KIND.get(r["action"], "comms"),
                title=str(title),
                detail=str(detail) if detail else None,
            ))
        return out
