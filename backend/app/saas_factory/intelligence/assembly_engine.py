"""Moteur d'assemblage : compose une `AssembledProject` a partir de :
- une `Qualification` (CDC analyse)
- un `PricingResult`        (prix calcule)
- la `PackDefinition`        (modules / livrables / phases du pack)
- (optionnel) une liste d'addons selectionnes

Le pack `custom` (REQUIRES_MANUAL_QUOTE) est traite a part : on retourne
une `AssemblyOutcome.MANUAL_QUOTE` qui invite l'orchestrateur a router la
demande vers Ahmed.
"""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.intelligence.packs.catalog import PackCatalog
from app.saas_factory.intelligence.pricing_engine import PricingResult, PricingStatus
from app.saas_factory.intelligence.qualification_engine import Qualification

logger = logging.getLogger(__name__)


class AssemblyOutcome(str, enum.Enum):
    AUTO = "auto"                    # pack assemble automatiquement
    MANUAL_QUOTE = "manual_quote"    # pack 'custom' -> Ahmed
    DEGRADED = "degraded"            # qualification confidence=low -> handoff


@dataclass(frozen=True)
class AssembledProject:
    assembly_id: UUID
    project_id: str
    pack_id: str
    outcome: AssemblyOutcome
    modules: tuple[str, ...]
    deliverables: tuple[str, ...]
    selected_addons: tuple[str, ...]
    phase_weights: dict[str, int]    # copie de PackDefinition.phases.as_ordered_pairs()
    qualification_id: UUID
    pricing_id: UUID | None
    notes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AssemblyEngine:
    def __init__(self, pool: asyncpg.Pool, pack_catalog: PackCatalog) -> None:
        self._pool = pool
        self._packs = pack_catalog

    async def assemble(
        self,
        *,
        qualification: Qualification,
        pricing: PricingResult,
        selected_addons: list[str] | None = None,
    ) -> AssembledProject:
        if qualification.project_id != qualification.project_id:
            # Tautologie : juste pour le linter — on accepte n'importe quel
            # project_id, on le copie de la qualification.
            pass
        if pricing.pack_id != qualification.pack_hint:
            # Le pricing peut diverger de la suggestion Claude (Ahmed override).
            # On loggue mais on n'echoue pas.
            logger.info(
                "assembly: pack mismatch (qual=%s pricing=%s) — pricing wins",
                qualification.pack_hint, pricing.pack_id,
            )

        pack = self._packs.get(pricing.pack_id)

        # Determination du outcome
        if pricing.status is PricingStatus.REQUIRES_MANUAL_QUOTE:
            outcome = AssemblyOutcome.MANUAL_QUOTE
        elif qualification.confidence.value == "low":
            outcome = AssemblyOutcome.DEGRADED
        else:
            outcome = AssemblyOutcome.AUTO

        # Filtrage des addons : on ne garde que ceux suggeres par le pack.
        wanted = list(selected_addons or [])
        valid_addons = tuple(a for a in wanted if a in pack.suggested_addons)
        skipped = [a for a in wanted if a not in pack.suggested_addons]

        notes: list[str] = []
        if skipped:
            notes.append(
                f"addons ignores (non suggeres par le pack): {sorted(skipped)}"
            )
        if outcome is AssemblyOutcome.DEGRADED:
            notes.append(
                "qualification confidence=low : handoff Ahmed recommande "
                "avant lancement production."
            )
        if outcome is AssemblyOutcome.MANUAL_QUOTE:
            notes.append("pack 'custom' : devis manuel Ahmed requis.")

        phase_weights = dict(pack.phases.as_ordered_pairs())

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO intelligence_assemblies (
                    project_id, qualification_id, pricing_id,
                    pack_id, outcome, modules, deliverables,
                    selected_addons, phase_weights_json, notes_json
                ) VALUES (
                    $1, $2, $3,
                    $4, $5, $6, $7,
                    $8, $9::jsonb, $10::jsonb
                ) RETURNING assembly_id, created_at
                """,
                qualification.project_id,
                qualification.qualification_id,
                pricing.pricing_id,
                pricing.pack_id,
                outcome.value,
                list(pack.base_modules),
                list(pack.base_deliverables),
                list(valid_addons),
                json.dumps(phase_weights, sort_keys=True),
                json.dumps(notes, sort_keys=True),
            )

        logger.info(
            "assembly.done project=%s pack=%s outcome=%s addons=%d",
            qualification.project_id, pricing.pack_id,
            outcome.value, len(valid_addons),
        )

        return AssembledProject(
            assembly_id=row["assembly_id"],
            project_id=qualification.project_id,
            pack_id=pricing.pack_id,
            outcome=outcome,
            modules=pack.base_modules,
            deliverables=pack.base_deliverables,
            selected_addons=valid_addons,
            phase_weights=phase_weights,
            qualification_id=qualification.qualification_id,
            pricing_id=pricing.pricing_id,
            notes=notes,
            created_at=row["created_at"],
        )

    @staticmethod
    def serialize_assembled(p: AssembledProject) -> dict[str, Any]:
        """Helper de debogage : produit un dict serialisable du resultat."""
        return {
            "assembly_id": str(p.assembly_id),
            "project_id": p.project_id,
            "pack_id": p.pack_id,
            "outcome": p.outcome.value,
            "modules": list(p.modules),
            "deliverables": list(p.deliverables),
            "selected_addons": list(p.selected_addons),
            "phase_weights": p.phase_weights,
            "qualification_id": str(p.qualification_id),
            "pricing_id": str(p.pricing_id) if p.pricing_id else None,
            "notes": list(p.notes),
            "created_at": p.created_at.isoformat(),
        }
