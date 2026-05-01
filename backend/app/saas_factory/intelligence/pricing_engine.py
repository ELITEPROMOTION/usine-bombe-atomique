"""Moteur de tarification : 15 coefficients x facettes projet -> prix final.

Lit ses parametres depuis `platform_config` (Phase 9B) :
- les 15 coefficients (weights, bornes optionnelles)
- la marge minimum (>= 50% per CDC)
- la TVA par defaut

Calcul deterministe en 4 etapes :

1. Pour chaque cle k de COEFFICIENT_KEYS :
       contribution[k] = clamp(facets[k], min, max) * weight[k]
2. raw_factor = 1.0 + sum(contributions) / NORMALIZER
3. effective_factor = min(raw_factor, pack.max_complexity_factor)
4. price = pack.base_price * effective_factor
   cost  = pack.estimated_cost * effective_factor
   if margin < min : on releve price pour atteindre la marge plancher.

Le pack `custom` (manual_quote_required=true) bypasse le calcul : on
retourne PricingResult avec status='REQUIRES_MANUAL_QUOTE' et price=0,
en indiquant qu'Ahmed doit etablir un devis manuel.
"""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field, model_validator

from app.saas_factory.intelligence.packs.catalog import PackCatalog
from app.saas_factory.setup_wizard.steps import COEFFICIENT_KEYS

logger = logging.getLogger(__name__)

# Avec NORMALIZER=30, 15 facettes a la valeur 2 et weight 1.0 -> raw_factor = 2.0
# (une charge "moyenne haute" double le prix).
NORMALIZER: Final[float] = 30.0


class PricingStatus(str, enum.Enum):
    OK = "ok"
    REQUIRES_MANUAL_QUOTE = "requires_manual_quote"


class ProjectFacets(BaseModel):
    """15 valeurs entieres [0..N] qui caracterisent un projet."""
    complexity: int = Field(ge=0, le=10)
    domain_specialty: int = Field(ge=0, le=10)
    urgency: int = Field(ge=0, le=10)
    support_level: int = Field(ge=0, le=10)
    compliance_overhead: int = Field(ge=0, le=10)
    i18n_locales: int = Field(ge=0, le=10)
    integration_count: int = Field(ge=0, le=20)
    design_intensity: int = Field(ge=0, le=10)
    data_migration: int = Field(ge=0, le=10)
    training_included: int = Field(ge=0, le=10)
    sla_tier: int = Field(ge=0, le=3)
    scaling_factor: int = Field(ge=0, le=10)
    geographic_spread: int = Field(ge=0, le=5)
    audit_required: int = Field(ge=0, le=3)
    post_launch_window: int = Field(ge=0, le=12)

    def as_dict(self) -> dict[str, int]:
        return self.model_dump()

    @model_validator(mode="after")
    def _all_keys_present(self) -> ProjectFacets:
        # Les noms d'attributs doivent etre exactement COEFFICIENT_KEYS.
        attrs = set(self.__class__.model_fields.keys())
        missing = set(COEFFICIENT_KEYS) - attrs
        if missing:
            raise ValueError(f"facets manquantes: {sorted(missing)}")
        return self


@dataclass(frozen=True)
class PricingBreakdown:
    facets: dict[str, int]
    coefficients_used: dict[str, float]
    contributions: dict[str, float]
    raw_factor: float
    effective_factor: float
    capped_at_max: bool
    margin_floor_applied: bool
    base_price_eur: int
    estimated_cost_eur: int
    margin_pct_actual: float


@dataclass(frozen=True)
class PricingResult:
    status: PricingStatus
    pack_id: str
    currency: str
    net_price: float                    # prix HT
    tax_amount: float
    gross_price: float                  # prix TTC
    breakdown: PricingBreakdown | None
    pricing_id: UUID | None
    computed_at: datetime
    notes: list[str] = field(default_factory=list)


def _round_2(x: float) -> float:
    return float(
        Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _compute_contributions(
    facets: ProjectFacets, coefficients: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    """Retourne (contributions, weights_used). Weights manquants -> 0."""
    facets_dict = facets.as_dict()
    weights_used: dict[str, float] = {}
    contributions: dict[str, float] = {}
    for k in COEFFICIENT_KEYS:
        w = float(coefficients.get(k, 0.0))
        weights_used[k] = w
        contributions[k] = facets_dict[k] * w
    return contributions, weights_used


def _apply_margin_floor(
    *,
    raw_price: float,
    cost: float,
    minimum_margin_pct: int,
) -> tuple[float, bool, float]:
    """Si margin < min, releve raw_price. Retourne (final, applied?, margin_actual_pct)."""
    if raw_price <= 0:
        return 0.0, False, 0.0
    actual_margin = (raw_price - cost) / raw_price
    floor = minimum_margin_pct / 100.0
    if actual_margin >= floor:
        return raw_price, False, actual_margin * 100.0
    # Releve le prix : floor = (P - cost) / P  =>  P = cost / (1 - floor)
    if floor >= 1.0:
        # Garde-fou : on ne peut pas avoir 100% de marge sur un cost > 0.
        return raw_price, False, actual_margin * 100.0
    new_price = cost / (1.0 - floor)
    return new_price, True, floor * 100.0


class PricingEngine:
    """Moteur de tarification deterministe."""

    def __init__(self, pool: asyncpg.Pool, pack_catalog: PackCatalog) -> None:
        self._pool = pool
        self._packs = pack_catalog

    async def quote(
        self,
        *,
        project_id: str,
        pack_id: str,
        facets: ProjectFacets,
        coefficients: dict[str, float],
        currency: str = "EUR",
        minimum_margin_pct: int = 50,
        default_vat_pct: float = 20.0,
    ) -> PricingResult:
        pack = self._packs.get(pack_id)

        if pack.manual_quote_required:
            res = PricingResult(
                status=PricingStatus.REQUIRES_MANUAL_QUOTE,
                pack_id=pack_id,
                currency=currency,
                net_price=0.0,
                tax_amount=0.0,
                gross_price=0.0,
                breakdown=None,
                pricing_id=None,
                computed_at=datetime.now(UTC),
                notes=[
                    "Pack 'custom' : devis manuel Ahmed requis.",
                    "Aucun calcul automatique applique.",
                ],
            )
            await self._persist(project_id=project_id, pack_id=pack_id, result=res,
                                facets=facets, coefficients=coefficients)
            return res

        # 1) contributions
        contributions, weights = _compute_contributions(facets, coefficients)
        # 2) raw factor
        raw_factor = 1.0 + sum(contributions.values()) / NORMALIZER
        # 3) cap
        capped = raw_factor > pack.max_complexity_factor
        eff_factor = min(raw_factor, pack.max_complexity_factor)
        # 4) raw price + cost scaling
        raw_price = pack.base_price_eur * eff_factor
        scaled_cost = pack.estimated_cost_eur * eff_factor
        # 5) margin floor
        net_price, margin_applied, margin_actual = _apply_margin_floor(
            raw_price=raw_price,
            cost=scaled_cost,
            minimum_margin_pct=minimum_margin_pct,
        )
        # 6) tax
        tax = net_price * (default_vat_pct / 100.0)
        gross = net_price + tax

        breakdown = PricingBreakdown(
            facets=facets.as_dict(),
            coefficients_used=weights,
            contributions=contributions,
            raw_factor=raw_factor,
            effective_factor=eff_factor,
            capped_at_max=capped,
            margin_floor_applied=margin_applied,
            base_price_eur=pack.base_price_eur,
            estimated_cost_eur=pack.estimated_cost_eur,
            margin_pct_actual=margin_actual,
        )

        res = PricingResult(
            status=PricingStatus.OK,
            pack_id=pack_id,
            currency=currency,
            net_price=_round_2(net_price),
            tax_amount=_round_2(tax),
            gross_price=_round_2(gross),
            breakdown=breakdown,
            pricing_id=None,
            computed_at=datetime.now(UTC),
        )
        pricing_id = await self._persist(
            project_id=project_id, pack_id=pack_id, result=res,
            facets=facets, coefficients=coefficients,
        )
        # On reconstruit avec l'id (dataclass frozen) ; alternative : remplacer
        # avant insertion.
        return PricingResult(
            status=res.status, pack_id=res.pack_id, currency=res.currency,
            net_price=res.net_price, tax_amount=res.tax_amount,
            gross_price=res.gross_price, breakdown=res.breakdown,
            pricing_id=pricing_id, computed_at=res.computed_at, notes=res.notes,
        )

    async def _persist(
        self,
        *,
        project_id: str,
        pack_id: str,
        result: PricingResult,
        facets: ProjectFacets,
        coefficients: dict[str, float],
    ) -> UUID:
        breakdown_json: dict = {}
        if result.breakdown is not None:
            b = result.breakdown
            breakdown_json = {
                "facets": b.facets,
                "coefficients_used": b.coefficients_used,
                "contributions": b.contributions,
                "raw_factor": b.raw_factor,
                "effective_factor": b.effective_factor,
                "capped_at_max": b.capped_at_max,
                "margin_floor_applied": b.margin_floor_applied,
                "base_price_eur": b.base_price_eur,
                "estimated_cost_eur": b.estimated_cost_eur,
                "margin_pct_actual": b.margin_pct_actual,
            }
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO intelligence_pricings (
                    project_id, pack_id, status, currency,
                    net_price, tax_amount, gross_price,
                    facets_json, coefficients_json, breakdown_json, notes_json
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7,
                    $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb
                ) RETURNING pricing_id
                """,
                project_id,
                pack_id,
                result.status.value,
                result.currency,
                result.net_price,
                result.tax_amount,
                result.gross_price,
                json.dumps(facets.as_dict(), sort_keys=True),
                json.dumps(coefficients, sort_keys=True),
                json.dumps(breakdown_json, sort_keys=True),
                json.dumps(result.notes, sort_keys=True),
            )
        logger.info(
            "pricing.computed project=%s pack=%s status=%s gross=%.2f%s",
            project_id, pack_id, result.status.value,
            result.gross_price, result.currency,
        )
        return row["pricing_id"]
