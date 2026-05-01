"""Catalog statique de milestones par status DB.

Plutot que de creer une table `client_milestones` (overkill V9), on
genere les 5 etapes standard cote service en marquant chacune
done/in_progress/pending selon `projects.status`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID


@dataclass(frozen=True)
class MilestoneTemplate:
    id: str
    label: str
    description: str
    days_offset: int     # jours apres `created_at`
    fully_done_after_status: str
    in_progress_at_status: str


_TEMPLATES: Final[tuple[MilestoneTemplate, ...]] = (
    MilestoneTemplate(
        id="m-qualif",
        label="Qualification",
        description="Brief signe + perimetre valide",
        days_offset=2,
        fully_done_after_status="qualifying",
        in_progress_at_status="submitted",
    ),
    MilestoneTemplate(
        id="m-arch",
        label="Architecture",
        description="Stack + modeles de donnees + API",
        days_offset=8,
        fully_done_after_status="assembled",
        in_progress_at_status="qualifying",
    ),
    MilestoneTemplate(
        id="m-build",
        label="Build interne",
        description="Generation modules + tests automatises",
        days_offset=24,
        fully_done_after_status="delivered",
        in_progress_at_status="in_production",
    ),
    MilestoneTemplate(
        id="m-review",
        label="Revue UI Premium",
        description="Walkthrough design system + interactions",
        days_offset=30,
        fully_done_after_status="delivered",
        in_progress_at_status="in_production",
    ),
    MilestoneTemplate(
        id="m-delivery",
        label="Livraison",
        description="Package final + acces deploiement",
        days_offset=38,
        fully_done_after_status="archived",
        in_progress_at_status="delivered",
    ),
)


_STATUS_ORDER: Final[tuple[str, ...]] = (
    "submitted", "qualifying", "assembled", "paywall_pending",
    "in_production", "delivered", "archived", "cancelled",
)


def _idx(status: str) -> int:
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return 0


def derive_milestones(
    project_id: UUID,
    db_status: str,
    created_at: datetime,
) -> list[dict]:
    """Renvoie la liste des 5 milestones avec status done/in_progress/pending."""
    cur_idx = _idx(db_status)
    out: list[dict] = []
    for tpl in _TEMPLATES:
        done_idx = _idx(tpl.fully_done_after_status)
        prog_idx = _idx(tpl.in_progress_at_status)
        if cur_idx >= done_idx:
            mstatus = "done"
        elif cur_idx >= prog_idx:
            mstatus = "in_progress"
        else:
            mstatus = "pending"
        out.append({
            "id": f"{tpl.id}-{str(project_id)[:8]}",
            "label": tpl.label,
            "description": tpl.description,
            "due_at": (created_at + timedelta(days=tpl.days_offset)).isoformat(),
            "status": mstatus,
        })
    return out


def derive_next_milestone(
    db_status: str, created_at: datetime,
) -> tuple[str, datetime] | None:
    """Retourne (label, due_at) du prochain milestone non termine."""
    cur_idx = _idx(db_status)
    for tpl in _TEMPLATES:
        done_idx = _idx(tpl.fully_done_after_status)
        if cur_idx < done_idx:
            return tpl.label, created_at + timedelta(days=tpl.days_offset)
    return None
