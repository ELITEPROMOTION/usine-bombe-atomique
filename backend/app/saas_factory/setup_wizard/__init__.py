"""Phase 9B : Setup Wizard Ahmed (admin bootstrap, 4 etapes).

Etapes (ordre impose) :
1. brand_identity        — nom, logo, couleur, locale, timezone, devise
2. pricing_baseline      — devise, marge min, 15 coefficients, TVA
3. service_catalog       — packs activables (E-Commerce/SaaS/Mobile/...)
4. operations_defaults   — Hostinger plan, backups, refund SLA, AI router

Le wizard ne peut pas etre commit tant que les 4 etapes ne sont pas
remplies *et* validees Pydantic. Pas de validation = pas de commit.
"""
from app.saas_factory.setup_wizard.steps import (
    WIZARD_STEP_ORDER,
    BrandIdentityStep,
    OperationsDefaultsStep,
    PricingBaselineStep,
    PricingCoefficient,
    ServiceCatalogStep,
    StepKey,
)
from app.saas_factory.setup_wizard.wizard_engine import (
    PlatformConfig,
    WizardEngine,
    WizardNotReadyError,
    WizardState,
    WizardStatus,
)

__all__ = [
    "BrandIdentityStep",
    "OperationsDefaultsStep",
    "PlatformConfig",
    "PricingBaselineStep",
    "PricingCoefficient",
    "ServiceCatalogStep",
    "StepKey",
    "WIZARD_STEP_ORDER",
    "WizardEngine",
    "WizardNotReadyError",
    "WizardState",
    "WizardStatus",
]
