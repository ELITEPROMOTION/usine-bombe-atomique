"""Cree un `projects` row depuis une `OnboardingSession` complete.

Le ProjectFactory orchestre :
1. Validation que les 6 etapes sont remplies + tos_accepted
2. INSERT projects (owner_email, company_name, country, locale, currency,
   summary_json contenant brief + pack + branding + technical)
3. UPDATE session.status = submitted, project_id = ...
4. Appel optionnel `QualificationTrigger` (defaut : noop)

Le QualificationTrigger est un Protocol injectable. En production il sera
relié au `QualificationEngine` (9C) via le `RouterBackedClaudeProvider`
(9D adapter), mais cela necessite un GO Ahmed pour les appels facturables.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from app.saas_factory.client_onboarding.onboarding_engine import (
    OnboardingEngine,
    OnboardingNotReadyError,
    OnboardingSession,
)
from app.saas_factory.client_onboarding.steps import (
    ClientStepKey,
    IdentityStep,
    PackSelectionStep,
    ProjectBriefStep,
    ReviewSubmitStep,
)

logger = logging.getLogger(__name__)


class QualificationTrigger(Protocol):
    """Appele apres creation du projet pour declencher la qualification IA.

    Implementations possibles :
    - `NoopQualificationTrigger`           : log seul (default safe)
    - `RouterBackedQualificationTrigger`  : Phase 9R, vrai LLM
    - `ArqQueueQualificationTrigger`       : Phase 9Q, file de jobs
    """

    async def __call__(
        self,
        *,
        project_id: UUID,
        cdc_text: str,
        owner_email: str,
        metadata: dict[str, Any],
    ) -> None: ...


class NoopQualificationTrigger:
    """Trigger par defaut : ne fait rien d'externe, journalise seulement."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        project_id: UUID,
        cdc_text: str,
        owner_email: str,
        metadata: dict[str, Any],
    ) -> None:
        self.calls.append({
            "project_id": str(project_id),
            "cdc_text_len": len(cdc_text),
            "owner_email": owner_email,
            "metadata": metadata,
        })
        logger.info(
            "qualification.deferred project=%s len=%d (NoopQualificationTrigger)",
            project_id, len(cdc_text),
        )


@dataclass(frozen=True)
class ProjectRecord:
    project_id: UUID
    owner_email: str
    company_name: str
    country: str
    locale: str
    currency: str
    pack_id_hint: str
    title: str
    status: str
    created_at: datetime
    summary: dict[str, Any] = field(default_factory=dict)


class ProjectFactory:
    def __init__(
        self,
        pool: asyncpg.Pool,
        engine: OnboardingEngine,
        *,
        qualification_trigger: QualificationTrigger | None = None,
    ) -> None:
        self._pool = pool
        self._engine = engine
        self._trigger: QualificationTrigger = (
            qualification_trigger or NoopQualificationTrigger()
        )

    async def create_from_session(self, session_id: UUID) -> ProjectRecord:
        session = await self._engine.get_state(session_id)
        if session is None:
            raise LookupError(f"session {session_id} introuvable")
        if not session.is_complete:
            missing = sorted(
                {s.value for s in self._missing_steps(session)},
            )
            raise OnboardingNotReadyError(
                f"etapes manquantes: {missing}"
            )
        if session.project_id is not None:
            raise RuntimeError(
                f"session {session_id} a deja un projet ({session.project_id})"
            )

        identity = IdentityStep.model_validate(
            session.partial_data[ClientStepKey.IDENTITY.value]
        )
        brief = ProjectBriefStep.model_validate(
            session.partial_data[ClientStepKey.PROJECT_BRIEF.value]
        )
        pack = PackSelectionStep.model_validate(
            session.partial_data[ClientStepKey.PACK_SELECTION.value]
        )
        review = ReviewSubmitStep.model_validate(
            session.partial_data[ClientStepKey.REVIEW_SUBMIT.value]
        )
        if not review.tos_accepted:                  # pragma: no cover
            # Defense en profondeur : Pydantic le bloque deja en amont.
            raise OnboardingNotReadyError("tos_accepted manquant")

        summary = {
            "identity": identity.model_dump(mode="json"),
            "brief": brief.model_dump(mode="json"),
            "pack": pack.model_dump(mode="json"),
            "branding": session.partial_data.get(ClientStepKey.BRANDING.value, {}),
            "technical": session.partial_data.get(
                ClientStepKey.TECHNICAL_PREFERENCES.value, {},
            ),
            "review": review.model_dump(mode="json"),
        }

        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO projects (
                    owner_email, company_name, country, locale, currency,
                    pack_id_hint, title, status, summary_json
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, 'submitted', $8::jsonb
                ) RETURNING project_id, created_at
                """,
                identity.email, identity.company_name, identity.country,
                identity.locale, identity.currency,
                pack.pack_id, brief.title,
                json.dumps(summary, sort_keys=True, ensure_ascii=False, default=str),
            )
            project_id: UUID = row["project_id"]

        # Marque la session comme submittee + lie le project_id (apres
        # le commit du projet pour ne pas avoir d'inconsistance si la
        # mise a jour echoue).
        await self._engine.mark_submitted(session_id, project_id=project_id)

        # Declenche la qualification (no-op safe par defaut).
        await self._trigger(
            project_id=project_id,
            cdc_text=brief.description,
            owner_email=identity.email,
            metadata={
                "pack_id_hint": pack.pack_id,
                "country": identity.country,
                "locale": identity.locale,
                "urgency": brief.urgency_level,
            },
        )

        logger.info(
            "project.created id=%s pack=%s owner=%s",
            project_id, pack.pack_id, identity.email,
        )

        return ProjectRecord(
            project_id=project_id,
            owner_email=identity.email,
            company_name=identity.company_name,
            country=identity.country,
            locale=identity.locale,
            currency=identity.currency,
            pack_id_hint=pack.pack_id,
            title=brief.title,
            status="submitted",
            created_at=row["created_at"],
            summary=summary,
        )

    @staticmethod
    def _missing_steps(session: OnboardingSession) -> set[ClientStepKey]:
        from app.saas_factory.client_onboarding.steps import (
            ONBOARDING_STEP_ORDER,
        )
        return set(ONBOARDING_STEP_ORDER) - set(session.completed_steps)
