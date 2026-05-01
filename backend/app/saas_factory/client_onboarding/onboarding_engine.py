"""Moteur de session d'onboarding client (6 etapes).

Reprend les patterns du `WizardEngine` 9B : start, save_step (validation
Pydantic + persistance partial_data), get_state, submit (delegue a
ProjectFactory), abandon. Les 6 etapes doivent toutes etre completees
pour que `submit()` reussisse — les transitions sont strictes.

`pack_selection.pack_id` est valide cote engine contre la liste
`enabled_packs` (typiquement issue de `platform_config.services_json`
de 9B).
"""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.client_onboarding.steps import (
    ONBOARDING_STEP_ORDER,
    BrandingStep,
    ClientStepKey,
    IdentityStep,
    PackSelectionStep,
    ProjectBriefStep,
    ReviewSubmitStep,
    TechnicalPreferencesStep,
)

logger = logging.getLogger(__name__)


class OnboardingStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    ABANDONED = "abandoned"


class OnboardingNotReadyError(RuntimeError):
    """Soulieve si submit() est appele avant que les 6 etapes soient remplies."""


_STEP_MODELS = {
    ClientStepKey.IDENTITY: IdentityStep,
    ClientStepKey.PROJECT_BRIEF: ProjectBriefStep,
    ClientStepKey.PACK_SELECTION: PackSelectionStep,
    ClientStepKey.BRANDING: BrandingStep,
    ClientStepKey.TECHNICAL_PREFERENCES: TechnicalPreferencesStep,
    ClientStepKey.REVIEW_SUBMIT: ReviewSubmitStep,
}


@dataclass
class OnboardingSession:
    session_id: UUID
    current_step: ClientStepKey
    completed_steps: list[ClientStepKey]
    partial_data: dict[str, Any]
    status: OnboardingStatus
    started_at: datetime
    submitted_at: datetime | None
    project_id: UUID | None

    @property
    def is_complete(self) -> bool:
        return set(self.completed_steps) == set(ONBOARDING_STEP_ORDER)


def _next_step(completed: set[ClientStepKey]) -> ClientStepKey:
    for s in ONBOARDING_STEP_ORDER:
        if s not in completed:
            return s
    return ONBOARDING_STEP_ORDER[-1]


class OnboardingEngine:
    """Pendant client du WizardEngine 9B."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        enabled_packs: tuple[str, ...] = (),
    ) -> None:
        self._pool = pool
        self._enabled_packs = frozenset(enabled_packs)

    async def start(self, *, owner_email: str | None = None) -> OnboardingSession:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO client_onboarding_sessions
                    (current_step, completed_steps, partial_data_json,
                     status, owner_email)
                VALUES ($1, ARRAY[]::TEXT[], '{}'::jsonb,
                        'in_progress', $2)
                RETURNING session_id, started_at
                """,
                ClientStepKey.IDENTITY.value,
                (owner_email or "")[:120] or None,
            )
        logger.info("onboarding.started session=%s", row["session_id"])
        return OnboardingSession(
            session_id=row["session_id"],
            current_step=ClientStepKey.IDENTITY,
            completed_steps=[],
            partial_data={},
            status=OnboardingStatus.IN_PROGRESS,
            started_at=row["started_at"],
            submitted_at=None,
            project_id=None,
        )

    async def save_step(
        self,
        session_id: UUID,
        step: ClientStepKey,
        payload: dict[str, Any],
    ) -> OnboardingSession:
        model_cls = _STEP_MODELS[step]
        validated = model_cls.model_validate(payload)

        # Validation supplementaire pack_selection : pack ∈ enabled_packs
        if (
            isinstance(validated, PackSelectionStep)
            and self._enabled_packs
            and validated.pack_id not in self._enabled_packs
        ):
            raise ValueError(
                f"pack_id {validated.pack_id!r} pas dans enabled_packs"
            )

        async with self._pool.acquire() as conn, conn.transaction():
            current = await self._fetch(conn, session_id)
            if current is None:
                raise LookupError(f"session {session_id} introuvable")
            if current.status is not OnboardingStatus.IN_PROGRESS:
                raise RuntimeError(
                    f"session {session_id} dans l'etat {current.status.value}"
                )

            partial = dict(current.partial_data)
            partial[step.value] = validated.model_dump(mode="json")
            completed = set(current.completed_steps) | {step}
            next_step = _next_step(completed)

            await conn.execute(
                """
                UPDATE client_onboarding_sessions
                   SET current_step = $2,
                       completed_steps = $3,
                       partial_data_json = $4::jsonb,
                       updated_at = NOW()
                 WHERE session_id = $1
                """,
                session_id,
                next_step.value,
                [s.value for s in sorted(completed, key=lambda x: x.value)],
                json.dumps(partial, sort_keys=True, ensure_ascii=False, default=str),
            )

        logger.info(
            "onboarding.save_step session=%s step=%s next=%s",
            session_id, step.value, next_step.value,
        )
        return OnboardingSession(
            session_id=session_id,
            current_step=next_step,
            completed_steps=sorted(completed, key=lambda x: x.value),
            partial_data=partial,
            status=current.status,
            started_at=current.started_at,
            submitted_at=current.submitted_at,
            project_id=current.project_id,
        )

    async def get_state(self, session_id: UUID) -> OnboardingSession | None:
        async with self._pool.acquire() as conn:
            return await self._fetch(conn, session_id)

    async def abandon(self, session_id: UUID, *, reason: str = "") -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE client_onboarding_sessions
                   SET status = 'abandoned',
                       partial_data_json = partial_data_json || $2::jsonb,
                       updated_at = NOW()
                 WHERE session_id = $1 AND status = 'in_progress'
                RETURNING session_id
                """,
                session_id,
                json.dumps({"_abandon_reason": reason[:500]},
                           sort_keys=True, ensure_ascii=False),
            )
        return row is not None

    async def mark_submitted(
        self,
        session_id: UUID,
        *,
        project_id: UUID,
    ) -> None:
        """Appele par le ProjectFactory apres creation du projet."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE client_onboarding_sessions
                   SET status = 'submitted',
                       submitted_at = $2,
                       project_id = $3,
                       updated_at = NOW()
                 WHERE session_id = $1
                """,
                session_id, now, project_id,
            )

    # --- private ---
    async def _fetch(
        self, conn: asyncpg.Connection, session_id: UUID,
    ) -> OnboardingSession | None:
        row = await conn.fetchrow(
            """
            SELECT session_id, current_step, completed_steps,
                   partial_data_json, status, started_at,
                   submitted_at, project_id
              FROM client_onboarding_sessions
             WHERE session_id = $1
            """,
            session_id,
        )
        if row is None:
            return None
        partial = row["partial_data_json"]
        if isinstance(partial, str):
            partial = json.loads(partial)
        return OnboardingSession(
            session_id=row["session_id"],
            current_step=ClientStepKey(row["current_step"]),
            completed_steps=[ClientStepKey(s) for s in (row["completed_steps"] or [])],
            partial_data=partial or {},
            status=OnboardingStatus(row["status"]),
            started_at=row["started_at"],
            submitted_at=row["submitted_at"],
            project_id=row["project_id"],
        )
