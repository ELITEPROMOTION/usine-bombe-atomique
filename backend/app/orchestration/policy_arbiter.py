"""Policy Arbiter V4.1 - moteur deterministe avant toute execution LLM.

Kill-switch Python pur (zero override LLM possible). Chaque regle retourne :
- `allow` : verdict binaire
- `rationale` : justification textuelle
- `rule_id` : code stable pour traceability

Les regles sont ordonnees par criticite. La premiere regle DENY gagne et
stoppe la chaine. Un evidence_ledger event est ecrit par chaque decision.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ArbiterRequest:
    spec: str
    priority: str = "high"
    estimated_cost_usd: float = 0.0
    budget_cap_usd: float = 2.0
    has_validated_artifacts: bool = False
    is_deploy_request: bool = False
    evidences_incomplete: bool = False
    tenant_code: str | None = None


@dataclass
class ArbiterDecision:
    allow: bool
    rule_id: str
    rationale: str
    severity: str = "info"  # info | warn | critical
    signals: dict[str, Any] = field(default_factory=dict)


# Patterns refuses : demandes de construction d'outils offensifs
DENY_PATTERNS = [
    re.compile(r"(?i)\b(exfiltr|ransomware|backdoor|rootkit|keylogger)\b"),
    re.compile(r"(?i)\b(contourne|bypass)\s+(?:auth|securite|jwt)\b"),
    re.compile(r"(?i)\b(mass[- ]spam|phishing kit|credential stuff(ing|er))\b"),
]

# Conformite DZ : signaux incompatibles avec le cadre algerien
FOREIGN_ONLY_PATTERNS = [
    re.compile(r"(?i)\b(HIPAA|FDA 21 CFR Part 11|GDPR only|SOX section)\b"),
]


def _rule_offensive(req: ArbiterRequest) -> ArbiterDecision | None:
    for pat in DENY_PATTERNS:
        m = pat.search(req.spec or "")
        if m:
            return ArbiterDecision(
                allow=False, rule_id="R1_OFFENSIVE",
                rationale=f"Motif offensif detecte: '{m.group(0)}'. Refus categorique.",
                severity="critical", signals={"match": m.group(0)},
            )
    return None


def _rule_deploy_without_evidence(req: ArbiterRequest) -> ArbiterDecision | None:
    if req.is_deploy_request and (req.evidences_incomplete or not req.has_validated_artifacts):
        return ArbiterDecision(
            allow=False, rule_id="R2_DEPLOY_WITHOUT_EVIDENCE",
            rationale="Deploiement refuse : artefacts non valides ou preuves incompletes.",
            severity="critical",
            signals={"has_validated_artifacts": req.has_validated_artifacts,
                     "evidences_incomplete": req.evidences_incomplete},
        )
    return None


def _rule_budget(req: ArbiterRequest) -> ArbiterDecision | None:
    if req.budget_cap_usd > 0 and req.estimated_cost_usd > req.budget_cap_usd:
        return ArbiterDecision(
            allow=False, rule_id="R3_BUDGET_EXCEEDED",
            rationale=(f"Budget depasse : estime ${req.estimated_cost_usd:.3f} > "
                       f"cap ${req.budget_cap_usd:.3f}."),
            severity="critical",
            signals={"estimated": req.estimated_cost_usd, "cap": req.budget_cap_usd},
        )
    return None


def _rule_foreign_regs(req: ArbiterRequest) -> ArbiterDecision | None:
    foreign_hits: list[str] = []
    for pat in FOREIGN_ONLY_PATTERNS:
        foreign_hits.extend(pat.findall(req.spec or ""))
    if not foreign_hits:
        return None
    mentions_dz = bool(re.search(
        r"(?i)\b(algerie|dzd|dinar|tva 19|tap 2|cnas|irg)\b", req.spec or "",
    ))
    if mentions_dz:
        return None
    return ArbiterDecision(
        allow=False, rule_id="R4_FOREIGN_REGULATIONS_ONLY",
        rationale=(f"Regulations non-algeriennes exclusives: {foreign_hits}. "
                   "Le Groupe Dendani requiert une reference DZ."),
        severity="critical", signals={"foreign": foreign_hits},
    )


def _rule_critical_thin(req: ArbiterRequest) -> ArbiterDecision | None:
    if req.priority == "critical" and len(req.spec or "") < 40:
        return ArbiterDecision(
            allow=False, rule_id="R5_CRITICAL_SPEC_TOO_THIN",
            rationale=f"Spec critique de {len(req.spec or '')}c < seuil minimal 40c.",
            severity="warn", signals={"spec_length": len(req.spec or "")},
        )
    return None


FABRICATED_FIELD_HINTS = (
    re.compile(r"(?i)invent[eé]e?\s+(?:une\s+)?(?:cle|token|password|mot de passe)"),
    re.compile(r"(?i)suppose\s+(?:un\s+)?(?:utilisateur|email|iban|carte)"),
    re.compile(r"(?i)hallucin|fictif|imaginaire"),
)

LEGAL_HINTS = re.compile(
    r"(?i)\b(rgpd|gdpr|hipaa|sox|pci[- ]dss|ccpa|conformite|compliance|"
    r"loi\s+\w+|article\s+\d+|directive\s+\d+)\b",
)


def _rule_forbid_fabrication(req: ArbiterRequest) -> ArbiterDecision | None:
    """Interdit formellement d'inventer une donnee sensible / conclure conformite."""
    for pat in FABRICATED_FIELD_HINTS:
        m = pat.search(req.spec or "")
        if m:
            return ArbiterDecision(
                allow=False, rule_id="R6_NO_FABRICATION",
                rationale=(f"Motif d'invention detecte: '{m.group(0)}'. "
                           "Le systeme ne doit JAMAIS inventer une donnee sensible "
                           "(cle, OTP, password). Demander a l'utilisateur via field_collector."),
                severity="critical", signals={"match": m.group(0)},
            )
    return None


def _rule_legal_without_evidence(req: ArbiterRequest) -> ArbiterDecision | None:
    """Refuse de conclure sur la conformite legale sans preuve explicite."""
    if LEGAL_HINTS.search(req.spec or "") \
            and not req.has_validated_artifacts \
            and req.evidences_incomplete:
        return ArbiterDecision(
            allow=False, rule_id="R7_LEGAL_WITHOUT_EVIDENCE",
            rationale=("Spec evoque conformite legale mais aucune preuve "
                        "n'a ete collectee. Exiger les textes de loi + test."),
            severity="critical", signals={"has_validated_artifacts": req.has_validated_artifacts},
        )
    return None


_RULES = (
    _rule_offensive, _rule_deploy_without_evidence, _rule_budget,
    _rule_foreign_regs, _rule_critical_thin,
    _rule_forbid_fabrication, _rule_legal_without_evidence,
)


def evaluate(req: ArbiterRequest) -> ArbiterDecision:
    """Evalue toutes les regles. Premiere regle DENY gagne."""
    for rule in _RULES:
        decision = rule(req)
        if decision is not None:
            return decision
    return ArbiterDecision(
        allow=True, rule_id="R0_ALLOW",
        rationale="Aucune regle bloquante declenchee.",
        severity="info",
    )
