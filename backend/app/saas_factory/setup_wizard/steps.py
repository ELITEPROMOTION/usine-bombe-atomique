"""Schemas Pydantic v2 pour les 4 etapes du Setup Wizard Ahmed.

Chaque etape est une `BaseModel` autonome. Le `WizardEngine` les compose
mais chacune peut etre validee/serialisee independamment, ce qui simplifie
l'API HTTP (1 endpoint POST par etape).
"""
from __future__ import annotations

import enum
from typing import Final, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Devises supportees par defaut. Liste extensible plus tard, mais on bornne
# pour eviter qu'Ahmed configure de l'XBT par megarde.
SupportedCurrency = Literal["EUR", "USD", "GBP", "DZD", "MAD", "TND", "CHF"]
SupportedLocale = Literal["en", "fr", "ar", "es"]
SupportedTimezone = Literal[
    "UTC",
    "Europe/Paris", "Europe/London", "Europe/Madrid",
    "Africa/Algiers", "Africa/Casablanca", "Africa/Tunis",
    "America/New_York", "America/Los_Angeles",
]

MIN_MARGIN_PCT: Final[int] = 50  # CDC : marge >= 50%
MAX_MARGIN_PCT: Final[int] = 95
MIN_BACKUP_DAYS: Final[int] = 7
MAX_BACKUP_DAYS: Final[int] = 365
MIN_REFUND_HOURS: Final[int] = 1
MAX_REFUND_HOURS: Final[int] = 168


class StepKey(str, enum.Enum):
    BRAND_IDENTITY = "brand_identity"
    PRICING_BASELINE = "pricing_baseline"
    SERVICE_CATALOG = "service_catalog"
    OPERATIONS_DEFAULTS = "operations_defaults"


WIZARD_STEP_ORDER: tuple[StepKey, ...] = (
    StepKey.BRAND_IDENTITY,
    StepKey.PRICING_BASELINE,
    StepKey.SERVICE_CATALOG,
    StepKey.OPERATIONS_DEFAULTS,
)


# ---------------------------------------------------------------------------
# Step 1 — Brand & Identity
# ---------------------------------------------------------------------------
class BrandIdentityStep(BaseModel):
    platform_name: str = Field(min_length=2, max_length=80)
    logo_url: str = Field(pattern=r"^https://[^\s]+$")
    primary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    support_email: EmailStr
    default_locale: SupportedLocale
    default_timezone: SupportedTimezone
    default_currency: SupportedCurrency


# ---------------------------------------------------------------------------
# Step 2 — Pricing Baseline (15 coefficients prep pour 9C)
# ---------------------------------------------------------------------------
# Le master plan dit "15 coefficients, marge >= 50%". On documente les
# coefficients ici comme cles + bornes. Le pricing_engine 9C lira ces valeurs.
COEFFICIENT_KEYS: Final[tuple[str, ...]] = (
    "complexity",          # complexite technique du projet
    "domain_specialty",    # specialite metier rare
    "urgency",             # urgence client
    "support_level",       # niveau de support inclus
    "compliance_overhead", # GDPR / SOC 2 / norme nationale
    "i18n_locales",        # nombre de langues
    "integration_count",   # nb. integrations tierces
    "design_intensity",    # design custom vs template
    "data_migration",      # complexite migration de donnees
    "training_included",   # heures de formation
    "sla_tier",            # tier SLA (basic, premium, platinum)
    "scaling_factor",      # capacite scale prevue
    "geographic_spread",   # multi-region cloud
    "audit_required",      # audit externe inclus
    "post_launch_window",  # mois de support post-launch
)


class PricingCoefficient(BaseModel):
    key: str
    weight: float = Field(ge=0.0, le=5.0)        # multiplicateur 0..5x
    bounded_min: float | None = Field(default=None, ge=0.0, le=10.0)
    bounded_max: float | None = Field(default=None, ge=0.0, le=10.0)

    @field_validator("key")
    @classmethod
    def _key_in_catalog(cls, v: str) -> str:
        if v not in COEFFICIENT_KEYS:
            raise ValueError(f"unknown coefficient key: {v!r}")
        return v

    @model_validator(mode="after")
    def _bounds_consistent(self) -> PricingCoefficient:
        if (
            self.bounded_min is not None
            and self.bounded_max is not None
            and self.bounded_min > self.bounded_max
        ):
            raise ValueError("bounded_min > bounded_max")
        return self


class PricingBaselineStep(BaseModel):
    base_currency: SupportedCurrency
    minimum_margin_pct: int = Field(ge=MIN_MARGIN_PCT, le=MAX_MARGIN_PCT)
    default_vat_pct: float = Field(ge=0.0, le=30.0)
    coefficients: list[PricingCoefficient] = Field(min_length=15, max_length=15)

    @model_validator(mode="after")
    def _all_coefficients_present_unique(self) -> PricingBaselineStep:
        seen: set[str] = set()
        for c in self.coefficients:
            if c.key in seen:
                raise ValueError(f"coefficient duplique: {c.key}")
            seen.add(c.key)
        missing = set(COEFFICIENT_KEYS) - seen
        if missing:
            raise ValueError(
                f"coefficients manquants: {sorted(missing)} "
                f"(15 requis : {COEFFICIENT_KEYS})"
            )
        return self


# ---------------------------------------------------------------------------
# Step 3 — Service Catalog (quels packs activer)
# ---------------------------------------------------------------------------
PackId = Literal[
    "ecommerce_small", "ecommerce_medium", "ecommerce_large",
    "saas_small", "saas_medium", "saas_large",
    "mobile_app", "api_b2b", "custom",
]

ALL_PACKS: Final[tuple[PackId, ...]] = (
    "ecommerce_small", "ecommerce_medium", "ecommerce_large",
    "saas_small", "saas_medium", "saas_large",
    "mobile_app", "api_b2b", "custom",
)


class ServiceCatalogStep(BaseModel):
    enabled_packs: list[PackId] = Field(min_length=1)
    featured_pack: PackId | None = None
    accept_custom_briefs: bool = True

    @field_validator("enabled_packs")
    @classmethod
    def _no_duplicates(cls, v: list[PackId]) -> list[PackId]:
        if len(set(v)) != len(v):
            raise ValueError("enabled_packs contient des doublons")
        return v

    @model_validator(mode="after")
    def _featured_must_be_enabled(self) -> ServiceCatalogStep:
        if self.featured_pack is not None and self.featured_pack not in self.enabled_packs:
            raise ValueError("featured_pack doit faire partie de enabled_packs")
        return self


# ---------------------------------------------------------------------------
# Step 4 — Operations Defaults
# ---------------------------------------------------------------------------
HostingerPlan = Literal["kvm1", "kvm2", "kvm4", "kvm8"]


class OperationsDefaultsStep(BaseModel):
    hostinger_default_plan: HostingerPlan
    backup_retention_days: int = Field(ge=MIN_BACKUP_DAYS, le=MAX_BACKUP_DAYS)
    refund_sla_hours: int = Field(ge=MIN_REFUND_HOURS, le=MAX_REFUND_HOURS)
    ai_router_claude_pct: int = Field(ge=0, le=100)
    ai_router_perplexity_pct: int = Field(ge=0, le=100)
    ai_router_manus_pct: int = Field(ge=0, le=100)
    ai_router_internal_pct: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ai_router_sums_to_100(self) -> OperationsDefaultsStep:
        total = (
            self.ai_router_claude_pct
            + self.ai_router_perplexity_pct
            + self.ai_router_manus_pct
            + self.ai_router_internal_pct
        )
        if total != 100:
            raise ValueError(
                f"ai_router_*_pct doit sommer a 100 (actuel: {total})"
            )
        return self
