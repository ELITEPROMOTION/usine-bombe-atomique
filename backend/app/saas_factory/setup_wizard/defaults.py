"""Valeurs recommandees par defaut pour chaque etape du wizard.

L'UI les pre-remplit. Ahmed peut les ajuster avant de valider chaque etape.
Les defauts respectent les contraintes du CDC (marge >= 50%, etc.).
"""
from __future__ import annotations

from app.saas_factory.setup_wizard.steps import (
    ALL_PACKS,
    COEFFICIENT_KEYS,
    BrandIdentityStep,
    OperationsDefaultsStep,
    PricingBaselineStep,
    PricingCoefficient,
    ServiceCatalogStep,
)


def default_brand_identity() -> BrandIdentityStep:
    return BrandIdentityStep(
        platform_name="UBA Studio Platform",
        logo_url="https://app.uba.studio/static/logo.svg",
        primary_color="#0F172A",
        support_email="support@uba.studio",
        default_locale="en",
        default_timezone="Europe/Paris",
        default_currency="EUR",
    )


def default_pricing_baseline() -> PricingBaselineStep:
    coefficients = [PricingCoefficient(key=k, weight=1.0) for k in COEFFICIENT_KEYS]
    return PricingBaselineStep(
        base_currency="EUR",
        minimum_margin_pct=55,    # legerement au-dessus du minimum CDC (50%)
        default_vat_pct=20.0,
        coefficients=coefficients,
    )


def default_service_catalog() -> ServiceCatalogStep:
    return ServiceCatalogStep(
        enabled_packs=list(ALL_PACKS),
        featured_pack="saas_medium",
        accept_custom_briefs=True,
    )


def default_operations() -> OperationsDefaultsStep:
    return OperationsDefaultsStep(
        hostinger_default_plan="kvm2",
        backup_retention_days=30,
        refund_sla_hours=72,
        ai_router_claude_pct=80,
        ai_router_perplexity_pct=15,
        ai_router_manus_pct=5,
        ai_router_internal_pct=0,
    )
