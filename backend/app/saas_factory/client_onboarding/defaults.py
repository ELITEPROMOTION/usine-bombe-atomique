"""Valeurs sample/defaut utiles aux tests et aux placeholders UI."""
from __future__ import annotations

from app.saas_factory.client_onboarding.steps import (
    BrandingStep,
    IdentityStep,
    PackSelectionStep,
    ProjectBriefStep,
    ReviewSubmitStep,
    TechnicalPreferencesStep,
)


def sample_identity() -> IdentityStep:
    return IdentityStep(
        email="founder@example.com",
        full_name="Dendani Sample",
        company_name="UBA Sample SAS",
        country="FR",
        locale="fr",
        currency="EUR",
    )


def sample_project_brief() -> ProjectBriefStep:
    return ProjectBriefStep(
        title="Tableau de bord SaaS interne",
        description=(
            "Outil de tableau de bord interne pour une equipe de 12 personnes,"
            " avec auth SSO, billing recurrent simple, et 2 langues (en+fr)."
        ),
        urgency_level="normal",
    )


def sample_pack_selection(pack_id: str = "saas_small") -> PackSelectionStep:
    return PackSelectionStep(pack_id=pack_id, accept_estimate=True)


def sample_branding() -> BrandingStep:
    return BrandingStep(
        logo_url="https://example.com/logo.svg",
        primary_color="#2563EB",
        target_audience="PME francophones, 5-50 employes, secteur services",
        sample_copy=None,
    )


def sample_technical() -> TechnicalPreferencesStep:
    return TechnicalPreferencesStep(
        preferred_stack="auto",
        locales_needed=["en", "fr"],
        custom_domain=False,
        domain_hint=None,
    )


def sample_review() -> ReviewSubmitStep:
    return ReviewSubmitStep(
        tos_accepted=True,
        terms_version="2026-04-30",
        marketing_opt_in=False,
    )
