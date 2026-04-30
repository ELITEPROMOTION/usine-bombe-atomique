"""Phase 9F : Client Onboarding 6 etapes (5 min target).

Pendant client du `setup_wizard` 9B (admin). Cree la table canonique
`projects` que les phases 9C/9D/9E reverenceront a posteriori (FK
retroactives ajoutees en Phase 9P, voir ADR-15).

Etapes (ordre impose) :

1. identity              — email, full_name, company_name, country, locale, currency
2. project_brief         — title, description (CDC seed), urgency_level
3. pack_selection        — pack_id parmi enabled_packs (du platform_config), accept_estimate
4. branding              — logo_url optional, primary_color, target_audience, sample_copy
5. technical_preferences — preferred_stack, locales_needed, custom_domain
6. review_submit         — tos_accepted (obligatoire), terms_version
"""
from app.saas_factory.client_onboarding.onboarding_engine import (
    OnboardingEngine,
    OnboardingNotReadyError,
    OnboardingSession,
    OnboardingStatus,
)
from app.saas_factory.client_onboarding.project_factory import (
    NoopQualificationTrigger,
    ProjectFactory,
    ProjectRecord,
    QualificationTrigger,
)
from app.saas_factory.client_onboarding.steps import (
    ALL_LOCALES,
    ONBOARDING_STEP_ORDER,
    BrandingStep,
    ClientStepKey,
    IdentityStep,
    PackSelectionStep,
    ProjectBriefStep,
    ReviewSubmitStep,
    TechnicalPreferencesStep,
)

__all__ = [
    "ALL_LOCALES",
    "BrandingStep",
    "ClientStepKey",
    "IdentityStep",
    "NoopQualificationTrigger",
    "ONBOARDING_STEP_ORDER",
    "OnboardingEngine",
    "OnboardingNotReadyError",
    "OnboardingSession",
    "OnboardingStatus",
    "PackSelectionStep",
    "ProjectBriefStep",
    "ProjectFactory",
    "ProjectRecord",
    "QualificationTrigger",
    "ReviewSubmitStep",
    "TechnicalPreferencesStep",
]
