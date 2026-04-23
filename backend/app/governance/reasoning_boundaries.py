"""V5.2 BLOC 5 - Reasoning Boundaries.

Whitelist stricte des domaines ou un LLM peut decider. Hors whitelist :
  - le domaine est "FISCAL", "PAYMENT", "SCHEMA" -> moteur deterministe
  - ou "UNKNOWN" -> escalade humaine type C

Interface :
  - is_reasoning_allowed(domain) -> bool
  - guard(domain) -> raise ReasoningBlocked si hors whitelist
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ReasoningBlocked(Exception):
    """Leve quand un LLM tente un reasoning dans un domaine interdit."""


# Domaines AUTORISES
REASONING_WHITELIST = {
    "architecture",              # React/Vue/Svelte, micro/monolithe
    "design_pattern",            # factory, strategy, observer
    "naming",                    # classes/fonctions/fichiers
    "documentation",             # structure, section order
    "non_critical_ordering",     # ordre etapes non-contraintes
    "response_format",           # JSON vs text, verbosity
    "example_generation",        # code samples
    "query_composition",         # non-fiscal SQL/GraphQL
    "translation",               # multi-lingue
    "reformulation",             # paraphrase besoins
    "template_selection",        # choix parmi templates valides
    "ux_copywriting",            # messages utilisateur
}

# Domaines STRICTEMENT INTERDITS (moteur deterministe obligatoire)
REASONING_BLACKLIST = {
    "fiscal_calculation",        # TVA/TAP/CNAS/IRG
    "financial_amount",          # montants
    "legal_deadline",            # echeances legales
    "compliance_validation",     # conformite reglementaire
    "permissions_attribution",   # droits/roles
    "schema_modification",       # ALTER TABLE
    "data_deletion",             # DELETE / TRUNCATE
    "payment_execution",         # tout paiement
    "contract_signature",        # signature contractuelle
    "secret_access",             # Vault secrets
    "policy_arbiter_modification",
    "rollback_production",
    "invariant_override",
}


@dataclass
class DomainVerdict:
    domain: str
    allowed: bool
    reason: str
    route_to: str              # "reasoning_engine" | "deterministic" | "escalate_C"


def verdict(domain: str) -> DomainVerdict:
    d = (domain or "").lower().strip()
    if d in REASONING_WHITELIST:
        return DomainVerdict(
            d, True, "domaine dans la whitelist", "reasoning_engine")
    if d in REASONING_BLACKLIST:
        # Payment/fiscal -> deterministic, other -> escalate
        if d in ("fiscal_calculation", "financial_amount",
                 "compliance_validation", "schema_modification",
                 "data_deletion", "secret_access"):
            return DomainVerdict(
                d, False, "domaine blacklist -> moteur deterministe obligatoire",
                "deterministic")
        return DomainVerdict(
            d, False, "domaine blacklist critique -> escalade humaine",
            "escalate_C")
    # Ni whitelist ni blacklist -> UNKNOWN : par defaut refuse + escalade
    return DomainVerdict(
        d, False, f"domaine '{d}' inconnu -> escalation C par prudence",
        "escalate_C")


def is_reasoning_allowed(domain: str) -> bool:
    return verdict(domain).allowed


def guard(domain: str) -> DomainVerdict:
    """Raise ReasoningBlocked si le domaine n'est pas autorise."""
    v = verdict(domain)
    if not v.allowed:
        raise ReasoningBlocked(
            f"reasoning bloque pour '{domain}' : {v.reason} "
            f"(route_to={v.route_to})")
    return v


def catalog() -> dict[str, Any]:
    """Snapshot pour dashboard."""
    return {
        "whitelist": sorted(REASONING_WHITELIST),
        "blacklist": sorted(REASONING_BLACKLIST),
        "whitelist_count": len(REASONING_WHITELIST),
        "blacklist_count": len(REASONING_BLACKLIST),
    }
