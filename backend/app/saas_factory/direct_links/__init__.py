"""Phase 9A : Direct-Link Framework.

Genere des liens d'action a usage unique ou multi-usage, signes par
chaine cryptographique (token urlsafe 32 octets, hash SHA-256 stocke en
DB), avec catalogue d'actions versionne en JSON et rendu i18n.

Modules :
- catalog            : chargement et validation de `catalog.json`
- direct_link_generator : emission de liens (token + persistance hash)
- validation_engine  : validate / consume / revoke + audit
- action_card_generator : rendu i18n vers une card (subject, body, CTA)
"""
from app.saas_factory.direct_links.action_card_generator import (
    ActionCard,
    ActionCardGenerator,
)
from app.saas_factory.direct_links.catalog import (
    Catalog,
    CatalogEntry,
    CatalogValidationError,
    LocaleStrings,
    load_default_catalog,
)
from app.saas_factory.direct_links.direct_link_generator import (
    DirectLinkGenerator,
    IssuedLink,
)
from app.saas_factory.direct_links.validation_engine import (
    LinkResolution,
    LinkStatus,
    ValidationEngine,
)

__all__ = [
    "ActionCard",
    "ActionCardGenerator",
    "Catalog",
    "CatalogEntry",
    "CatalogValidationError",
    "DirectLinkGenerator",
    "IssuedLink",
    "LinkResolution",
    "LinkStatus",
    "LocaleStrings",
    "ValidationEngine",
    "load_default_catalog",
]
