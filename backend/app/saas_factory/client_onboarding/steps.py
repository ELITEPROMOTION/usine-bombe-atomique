"""Schemas Pydantic v2 pour les 6 etapes du Client Onboarding.

Chaque etape est une `BaseModel` autonome — l'API HTTP (Phase 9N) y dedie
un endpoint POST.
"""
from __future__ import annotations

import enum
from typing import Final, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Locales et devises supportees (alignees sur 9B pour coherence).
ALL_LOCALES: Final[tuple[str, ...]] = ("en", "fr", "ar", "es")
_SupportedLocale = Literal["en", "fr", "ar", "es"]
_SupportedCurrency = Literal["EUR", "USD", "GBP", "DZD", "MAD", "TND", "CHF"]
_UrgencyLevel = Literal["low", "normal", "high", "urgent"]
_PreferredStack = Literal[
    "auto", "python_fastapi", "node_nextjs", "ruby_rails",
    "php_laravel", "go_gin", "java_spring",
]


class ClientStepKey(str, enum.Enum):
    IDENTITY = "identity"
    PROJECT_BRIEF = "project_brief"
    PACK_SELECTION = "pack_selection"
    BRANDING = "branding"
    TECHNICAL_PREFERENCES = "technical_preferences"
    REVIEW_SUBMIT = "review_submit"


ONBOARDING_STEP_ORDER: tuple[ClientStepKey, ...] = (
    ClientStepKey.IDENTITY,
    ClientStepKey.PROJECT_BRIEF,
    ClientStepKey.PACK_SELECTION,
    ClientStepKey.BRANDING,
    ClientStepKey.TECHNICAL_PREFERENCES,
    ClientStepKey.REVIEW_SUBMIT,
)


# ---------------------------------------------------------------------------
# Step 1 — Identity
# ---------------------------------------------------------------------------
class IdentityStep(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    company_name: str = Field(min_length=1, max_length=120)
    # ISO 3166-1 alpha-2 (DZ, FR, US, ...).
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    locale: _SupportedLocale
    currency: _SupportedCurrency


# ---------------------------------------------------------------------------
# Step 2 — Project Brief (CDC seed)
# ---------------------------------------------------------------------------
class ProjectBriefStep(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=30, max_length=10_000)
    urgency_level: _UrgencyLevel = "normal"


# ---------------------------------------------------------------------------
# Step 3 — Pack Selection
# ---------------------------------------------------------------------------
class PackSelectionStep(BaseModel):
    """Le pack_id doit etre dans la liste passee au moteur via
    `OnboardingEngine.__init__(enabled_packs=...)`. La validation finale
    est faite cote engine, pas Pydantic (dependance d'env runtime).
    """
    pack_id: str = Field(min_length=1, max_length=50)
    accept_estimate: bool


# ---------------------------------------------------------------------------
# Step 4 — Branding
# ---------------------------------------------------------------------------
class BrandingStep(BaseModel):
    logo_url: str | None = Field(default=None, pattern=r"^https://[^\s]+$")
    primary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    target_audience: str = Field(min_length=3, max_length=500)
    sample_copy: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Step 5 — Technical Preferences
# ---------------------------------------------------------------------------
class TechnicalPreferencesStep(BaseModel):
    preferred_stack: _PreferredStack = "auto"
    locales_needed: list[_SupportedLocale] = Field(min_length=1, max_length=4)
    custom_domain: bool = False
    domain_hint: str | None = Field(
        default=None, pattern=r"^[a-zA-Z0-9.\-]+$", max_length=253,
    )

    @field_validator("locales_needed")
    @classmethod
    def _no_duplicates(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("locales_needed contient des doublons")
        return v

    @model_validator(mode="after")
    def _domain_hint_only_when_custom(self) -> TechnicalPreferencesStep:
        if self.domain_hint and not self.custom_domain:
            raise ValueError(
                "domain_hint requiert custom_domain=True"
            )
        return self


# ---------------------------------------------------------------------------
# Step 6 — Review & Submit
# ---------------------------------------------------------------------------
class ReviewSubmitStep(BaseModel):
    tos_accepted: bool
    terms_version: str = Field(min_length=1, max_length=20)
    marketing_opt_in: bool = False

    @model_validator(mode="after")
    def _tos_must_be_accepted(self) -> ReviewSubmitStep:
        if not self.tos_accepted:
            raise ValueError(
                "tos_accepted obligatoire pour soumettre l'onboarding"
            )
        return self
