"""Types Phase 9I : enums + locales supportees."""
from __future__ import annotations

import enum
from typing import Final

SUPPORTED_LEGAL_LOCALES: Final[tuple[str, ...]] = ("en", "fr", "ar", "es")


class DocumentType(str, enum.Enum):
    TOS = "tos"                          # Terms of Service
    PRIVACY = "privacy"                  # Privacy Policy
    COOKIE_POLICY = "cookie_policy"      # Cookie Policy
    DATA_PROCESSING_ADDENDUM = "dpa"     # DPA pour clients B2B


class ConsentScope(str, enum.Enum):
    TOS_ACCEPTANCE = "tos_acceptance"           # acceptation des CGV
    PRIVACY_POLICY = "privacy_policy"           # acknowledgment privacy
    COOKIE_FUNCTIONAL = "cookie_functional"     # cookies necessaires
    COOKIE_ANALYTICS = "cookie_analytics"       # cookies analytics opt-in
    COOKIE_MARKETING = "cookie_marketing"       # cookies marketing opt-in
    DATA_PROCESSING = "data_processing"         # traitement donnees (Art 6.1.a)
    MARKETING_OPT_IN = "marketing_opt_in"       # emails marketing
