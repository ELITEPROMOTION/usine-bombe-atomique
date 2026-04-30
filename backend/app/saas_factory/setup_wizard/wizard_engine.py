"""Moteur d'etat du Setup Wizard Ahmed.

Le wizard avance pas-a-pas : Ahmed sauve l'etape courante (`save_step`),
le moteur valide via Pydantic, persiste le JSON partiel dans
`setup_wizard_state`, puis avance le pointeur `current_step`.

Quand les 4 etapes sont valides, `commit()` ecrit le `platform_config`
singleton dans une transaction unique. Si l'une des etapes manque,
`WizardNotReadyError` est levee — pas de commit partiel.

Invariants :
- `setup_wizard_state` peut contenir plusieurs lignes (historique des
  tentatives) ; c'est `wizard_id` qui isole une session.
- `platform_config` est un singleton (id=1, contrainte CHECK).
- Toute ecriture dans `platform_config` cree une ligne `evidence_ledger`
  (audit trail SOC 2).
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

from app.saas_factory.setup_wizard.steps import (
    WIZARD_STEP_ORDER,
    BrandIdentityStep,
    OperationsDefaultsStep,
    PricingBaselineStep,
    ServiceCatalogStep,
    StepKey,
)

logger = logging.getLogger(__name__)


class WizardStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ABANDONED = "abandoned"


class WizardNotReadyError(RuntimeError):
    """Levee si commit() est appelee avant que les 4 etapes soient validees."""


@dataclass
class WizardState:
    wizard_id: UUID
    current_step: StepKey
    completed_steps: list[StepKey]
    partial_config: dict[str, Any]      # {step_key: validated_payload}
    status: WizardStatus
    started_at: datetime
    committed_at: datetime | None

    @property
    def is_complete(self) -> bool:
        return set(self.completed_steps) == set(WIZARD_STEP_ORDER)


@dataclass(frozen=True)
class PlatformConfig:
    version: int
    identity: BrandIdentityStep
    pricing: PricingBaselineStep
    services: ServiceCatalogStep
    operations: OperationsDefaultsStep
    committed_at: datetime
    committed_by: str


_STEP_MODELS = {
    StepKey.BRAND_IDENTITY: BrandIdentityStep,
    StepKey.PRICING_BASELINE: PricingBaselineStep,
    StepKey.SERVICE_CATALOG: ServiceCatalogStep,
    StepKey.OPERATIONS_DEFAULTS: OperationsDefaultsStep,
}


def _next_step(completed: set[StepKey]) -> StepKey:
    """Premier step non encore complete dans l'ordre canonique."""
    for s in WIZARD_STEP_ORDER:
        if s not in completed:
            return s
    return WIZARD_STEP_ORDER[-1]


class WizardEngine:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def start(self, *, started_by: str = "ahmed") -> WizardState:
        """Cree un nouveau wizard. Plusieurs simultanes sont autorises (hist.)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO setup_wizard_state
                    (current_step, completed_steps, partial_config_json,
                     status, started_by)
                VALUES ($1, ARRAY[]::TEXT[], '{}'::jsonb, 'in_progress', $2)
                RETURNING wizard_id, started_at
                """,
                StepKey.BRAND_IDENTITY.value,
                started_by[:80],
            )
        logger.info(
            "wizard.started id=%s by=%s", row["wizard_id"], started_by[:40],
        )
        return WizardState(
            wizard_id=row["wizard_id"],
            current_step=StepKey.BRAND_IDENTITY,
            completed_steps=[],
            partial_config={},
            status=WizardStatus.IN_PROGRESS,
            started_at=row["started_at"],
            committed_at=None,
        )

    async def save_step(
        self,
        wizard_id: UUID,
        step: StepKey,
        payload: dict[str, Any],
    ) -> WizardState:
        """Valide la payload via Pydantic, persiste, avance current_step.

        Lever de validation Pydantic est laissee remonter au caller : c'est
        l'API HTTP qui transforme en 422.
        """
        model_cls = _STEP_MODELS[step]
        validated = model_cls.model_validate(payload)  # peut lever ValidationError

        async with self._pool.acquire() as conn, conn.transaction():
            current = await self._fetch_state(conn, wizard_id)
            if current is None:
                raise LookupError(f"wizard {wizard_id} introuvable")
            if current.status is not WizardStatus.IN_PROGRESS:
                raise RuntimeError(
                    f"wizard {wizard_id} est dans l'etat {current.status.value}"
                )

            # Merge : on ajoute / remplace le step dans partial_config.
            partial = dict(current.partial_config)
            partial[step.value] = validated.model_dump(mode="json")
            completed = set(current.completed_steps) | {step}
            next_step = _next_step(completed)

            await conn.execute(
                """
                UPDATE setup_wizard_state
                   SET current_step = $2,
                       completed_steps = $3,
                       partial_config_json = $4::jsonb,
                       updated_at = NOW()
                 WHERE wizard_id = $1
                """,
                wizard_id,
                next_step.value,
                [s.value for s in sorted(completed, key=lambda x: x.value)],
                json.dumps(partial, sort_keys=True, ensure_ascii=False, default=str),
            )

        logger.info(
            "wizard.save_step id=%s step=%s next=%s",
            wizard_id, step.value, next_step.value,
        )
        return WizardState(
            wizard_id=wizard_id,
            current_step=next_step,
            completed_steps=sorted(completed, key=lambda x: x.value),
            partial_config=partial,
            status=current.status,
            started_at=current.started_at,
            committed_at=current.committed_at,
        )

    async def get_state(self, wizard_id: UUID) -> WizardState | None:
        async with self._pool.acquire() as conn:
            return await self._fetch_state(conn, wizard_id)

    async def commit(
        self,
        wizard_id: UUID,
        *,
        committed_by: str = "ahmed",
    ) -> PlatformConfig:
        async with self._pool.acquire() as conn, conn.transaction():
            current = await self._fetch_state(conn, wizard_id)
            if current is None:
                raise LookupError(f"wizard {wizard_id} introuvable")
            if not current.is_complete:
                missing = sorted(
                    set(WIZARD_STEP_ORDER) - set(current.completed_steps),
                    key=lambda s: s.value,
                )
                raise WizardNotReadyError(
                    f"etapes manquantes: {[s.value for s in missing]}"
                )
            if current.status is WizardStatus.COMMITTED:
                raise RuntimeError(f"wizard {wizard_id} est deja commit")

            # Reconstruire les modeles valides depuis le JSON persiste.
            identity = BrandIdentityStep.model_validate(
                current.partial_config[StepKey.BRAND_IDENTITY.value]
            )
            pricing = PricingBaselineStep.model_validate(
                current.partial_config[StepKey.PRICING_BASELINE.value]
            )
            services = ServiceCatalogStep.model_validate(
                current.partial_config[StepKey.SERVICE_CATALOG.value]
            )
            operations = OperationsDefaultsStep.model_validate(
                current.partial_config[StepKey.OPERATIONS_DEFAULTS.value]
            )

            now = datetime.now(UTC)
            row = await conn.fetchrow(
                """
                INSERT INTO platform_config
                    (id, identity_json, pricing_json, services_json,
                     operations_json, committed_by, committed_at)
                VALUES (1, $1::jsonb, $2::jsonb, $3::jsonb, $4::jsonb, $5, $6)
                ON CONFLICT (id) DO UPDATE
                   SET identity_json = EXCLUDED.identity_json,
                       pricing_json = EXCLUDED.pricing_json,
                       services_json = EXCLUDED.services_json,
                       operations_json = EXCLUDED.operations_json,
                       committed_by = EXCLUDED.committed_by,
                       committed_at = EXCLUDED.committed_at,
                       version = platform_config.version + 1
                RETURNING version
                """,
                json.dumps(identity.model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False, default=str),
                json.dumps(pricing.model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False, default=str),
                json.dumps(services.model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False, default=str),
                json.dumps(operations.model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False, default=str),
                committed_by[:80],
                now,
            )

            await conn.execute(
                """
                UPDATE setup_wizard_state
                   SET status = 'committed', committed_at = $2, updated_at = NOW()
                 WHERE wizard_id = $1
                """,
                wizard_id, now,
            )

        logger.info(
            "wizard.committed id=%s version=%d by=%s",
            wizard_id, row["version"], committed_by[:40],
        )
        return PlatformConfig(
            version=row["version"],
            identity=identity,
            pricing=pricing,
            services=services,
            operations=operations,
            committed_at=now,
            committed_by=committed_by,
        )

    async def abandon(self, wizard_id: UUID, *, reason: str = "") -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE setup_wizard_state
                   SET status = 'abandoned',
                       partial_config_json = partial_config_json
                                             || $2::jsonb,
                       updated_at = NOW()
                 WHERE wizard_id = $1 AND status = 'in_progress'
                RETURNING wizard_id
                """,
                wizard_id,
                json.dumps({"_abandon_reason": reason[:500]},
                           sort_keys=True, ensure_ascii=False),
            )
        return row is not None

    # --- internals ---
    async def _fetch_state(
        self, conn: asyncpg.Connection, wizard_id: UUID,
    ) -> WizardState | None:
        row = await conn.fetchrow(
            """
            SELECT wizard_id, current_step, completed_steps,
                   partial_config_json, status, started_at, committed_at
              FROM setup_wizard_state
             WHERE wizard_id = $1
            """,
            wizard_id,
        )
        if row is None:
            return None
        partial = row["partial_config_json"]
        if isinstance(partial, str):
            partial = json.loads(partial)
        return WizardState(
            wizard_id=row["wizard_id"],
            current_step=StepKey(row["current_step"]),
            completed_steps=[StepKey(s) for s in (row["completed_steps"] or [])],
            partial_config=partial or {},
            status=WizardStatus(row["status"]),
            started_at=row["started_at"],
            committed_at=row["committed_at"],
        )
