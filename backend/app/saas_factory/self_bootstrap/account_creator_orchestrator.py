"""Module B : orchestrateur (planificateur) des comptes Dendani.

Phase 9-BOOT = orchestrateur PRET, mais sans execution reelle. Aucun appel
Manus / Cloudflare / GitHub n'est emis ici. La methode `plan_all` produit
un `AccountPlan` (liste ordonnee d'`AccountStep`) que la phase 9-A et au-dela
exploiteront pour declencher les creations.

Cette classe :
- s'appuie sur `ServicePriorityQueue` pour l'ordre tier 1 -> 3
- emet un `Mandate` pour chaque service avant de planifier sa creation
- prepare un `HandoffEnvelope` quand un service requiert carte ou KYC
- persiste les rangs dans `service_activations`

Le Vault est utilise plus tard (lors de l'execution reelle) pour stocker
les credentials retournes par chaque provider.
"""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.self_bootstrap.handoff_kyc_orchestrator import (
    HandoffKycOrchestrator,
    HandoffType,
)
from app.saas_factory.self_bootstrap.mandate_engine import (
    MandateEngine,
    MandateType,
)
from app.saas_factory.self_bootstrap.service_priority_queue import (
    DEFAULT_CATALOG,
    ServiceDescriptor,
    ServicePriorityQueue,
    ServiceTier,
)

logger = logging.getLogger(__name__)


class StepKind(str, enum.Enum):
    AUTOMATED = "automated"          # creation 100% via API/Manus
    REQUIRES_CARD = "requires_card"   # handoff carte
    REQUIRES_KYC = "requires_kyc"     # handoff KYC


@dataclass
class AccountStep:
    service: str
    tier: ServiceTier
    kind: StepKind
    depends_on: list[str]
    mandate_id: UUID | None = None
    handoff_id: UUID | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "tier": int(self.tier),
            "kind": self.kind.value,
            "depends_on": self.depends_on,
            "mandate_id": str(self.mandate_id) if self.mandate_id else None,
            "handoff_id": str(self.handoff_id) if self.handoff_id else None,
            "notes": self.notes,
        }


@dataclass
class AccountPlan:
    principal_id: str
    agent_identity: str
    target_email: str
    locale: str
    steps: list[AccountStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "agent_identity": self.agent_identity,
            "target_email": self.target_email,
            "locale": self.locale,
            "steps": [s.to_dict() for s in self.steps],
        }


class AccountCreatorOrchestrator:
    """Planifie (sans executer) la creation de tous les comptes Dendani."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        mandate_engine: MandateEngine,
        handoff: HandoffKycOrchestrator,
        *,
        catalog: tuple[ServiceDescriptor, ...] = DEFAULT_CATALOG,
    ) -> None:
        self._pool = pool
        self._mandates = mandate_engine
        self._handoff = handoff
        self._catalog = catalog

    @staticmethod
    def _kind_for(service: ServiceDescriptor) -> StepKind:
        if service.tier is ServiceTier.NO_KYC:
            return StepKind.AUTOMATED
        if service.tier is ServiceTier.CARD_REQUIRED:
            return StepKind.REQUIRES_CARD
        return StepKind.REQUIRES_KYC

    @staticmethod
    def _handoff_type_for(kind: StepKind) -> HandoffType | None:
        if kind is StepKind.REQUIRES_CARD:
            return HandoffType.CARD
        if kind is StepKind.REQUIRES_KYC:
            return HandoffType.KYC
        return None

    async def _persist_step(
        self,
        *,
        service: str,
        tier: ServiceTier,
        plan_payload: dict[str, Any],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO service_activations (
                    service_name, tier, activation_status, plan_json
                ) VALUES ($1, $2, 'planning', $3::jsonb)
                ON CONFLICT (service_name) DO UPDATE
                   SET tier = EXCLUDED.tier,
                       activation_status = 'planning',
                       plan_json = EXCLUDED.plan_json
                """,
                service,
                int(tier),
                json.dumps(plan_payload, sort_keys=True, ensure_ascii=False, default=str),
            )

    async def plan_all(
        self,
        *,
        principal_id: str,
        agent_identity: str = "uba_platform",
        target_email: str,
        locale: str = "en",
    ) -> AccountPlan:
        """Construit le plan complet, emet les mandats, prepare les handoffs."""
        queue = ServicePriorityQueue(self._catalog)
        plan = AccountPlan(
            principal_id=principal_id,
            agent_identity=agent_identity,
            target_email=target_email,
            locale=locale,
        )

        # On parcourt la queue dans l'ordre et on planifie chaque service
        # comme s'il avait reussi (le but est juste de produire la sequence).
        while True:
            svc = queue.next()
            if svc is None:
                break

            kind = self._kind_for(svc)
            mandate = await self._mandates.issue(
                mandate_type=MandateType.ACCOUNT_CREATION,
                principal_id=principal_id,
                agent_identity=agent_identity,
                scope={
                    "service": svc.name,
                    "tier": int(svc.tier),
                    "kind": kind.value,
                },
                ttl=timedelta(days=365),
            )

            handoff_id: UUID | None = None
            handoff_type = self._handoff_type_for(kind)
            if handoff_type is not None:
                envelope = await self._handoff.open_handoff(
                    handoff_type=handoff_type,
                    target_email=target_email,
                    service=svc.name,
                    locale=locale,
                    instructions={"mandate_id": str(mandate.mandate_id)},
                )
                handoff_id = envelope.handoff_id

            step = AccountStep(
                service=svc.name,
                tier=svc.tier,
                kind=kind,
                depends_on=list(svc.depends_on),
                mandate_id=mandate.mandate_id,
                handoff_id=handoff_id,
            )
            plan.steps.append(step)

            await self._persist_step(
                service=svc.name,
                tier=svc.tier,
                plan_payload=step.to_dict(),
            )

            # On marque comme reussi pour debloquer les services dependants —
            # cela ne represente pas une activation reelle, juste l'avancement
            # logique du planificateur.
            queue.mark_success(svc.name)

        logger.info(
            "account_plan generated principal=%s steps=%d",
            principal_id, len(plan.steps),
        )
        return plan
