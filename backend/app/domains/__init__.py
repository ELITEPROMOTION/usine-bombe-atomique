"""5 domaines metier UBA V5.6 - auto-register.

Import side-effect : enregistre les 5 domaines au premier import.
Utilise par app.main au lifespan startup.

Ordre d'enregistrement :
    1. fiscal_dz    - fiscalite Algerie
    2. juridique    - contrats + baux + actes
    3. logistique   - stocks + import/export
    4. rh           - paie + conges + declarations
    5. comptabilite - SCF DZ + ecritures + bilans
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.core import DomainRegistry
from app.core.rules_engine import RulesEngine, load_rules_from_dir
from app.domains.comptabilite import ComptabiliteDomain
from app.domains.fiscal_dz import FiscalDZDomain
from app.domains.juridique import JuridiqueDomain
from app.domains.logistique import LogistiqueDomain
from app.domains.rh import RHDomain

logger = logging.getLogger("uba.domains")

# Single global RulesEngine partage par tous les domaines
RULES_ENGINE = RulesEngine()


def _rules_dir() -> Path:
    """Retourne le chemin du dossier rules/ selon container vs host."""
    candidates = [
        Path("/app/rules"),
        Path("/repo/backend/rules"),
        Path(__file__).parent.parent.parent / "rules",
        Path("backend/rules"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _load_all_rules() -> None:
    """Charge toutes les rules YAML dans le RULES_ENGINE global."""
    rules_by_domain = load_rules_from_dir(_rules_dir())
    for domain, rules in rules_by_domain.items():
        RULES_ENGINE.load_bundle(domain, rules)


def register_all() -> DomainRegistry:
    """Enregistre les 5 domaines dans le registry singleton."""
    registry = DomainRegistry.instance()
    # Idempotent : si deja enregistre, skip (pour tests)
    try:
        for cls in (FiscalDZDomain, JuridiqueDomain, LogistiqueDomain,
                    RHDomain, ComptabiliteDomain):
            if cls.domain_id not in {d["domain_id"]
                                       for d in registry.list_domains()}:
                registry.register(cls(rules_engine=RULES_ENGINE))
    except ValueError as exc:
        logger.warning("domain register skipped (already registered?): %s", exc)
    _load_all_rules()
    logger.info("registered %d domains", len(registry.list_domains()))
    return registry


__all__ = ["register_all", "RULES_ENGINE"]
