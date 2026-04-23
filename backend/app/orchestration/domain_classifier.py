"""Upgrade 15 - Classificateur domaine + juridiction (auto).

Detecte le domaine metier (Immobilier/FinTech/Sante/Logistique/Paie/etc.)
ET la juridiction (DZ/FR/US/EU) depuis le prompt pour adapter le jeu de
regles de conformite applique par l'agent #18.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DOMAIN_MAP: dict[str, tuple[str, ...]] = {
    "immobilier":  ("vefa", "residence", "palier", "appartement", "promotion immobiliere"),
    "fintech":     ("paiement", "wallet", "kyc", "ledger", "swift", "iban", "bic"),
    "sante":       ("patient", "dossier medical", "hipaa", "dsp", "medicament"),
    "logistique":  ("colis", "entrepot", "manifeste", "tracking", "livraison"),
    "paie_rh":     ("paie", "salaire", "cnas", "irg", "bulletin", "g50"),
    "comptabilite":("bilan", "ecriture", "journal", "scf", "debit", "credit"),
    "ecommerce":   ("produit", "catalogue", "panier", "commande"),
    "support":     ("ticket", "sla", "incident", "queue"),
}

JURISDICTION_MAP: dict[str, tuple[str, ...]] = {
    "DZ": ("algerie", "algerien", "dzd", "dinar", "tva 19", "tap 2", "cnas", "irg", "scf"),
    "FR": ("france", "urssaf", "code du travail", "tva 20", "tva 5.5", "sirene", "kbis"),
    "US": ("united states", "hipaa", "fda", "sox", "ein", "ssn", "irs"),
    "EU": ("rgpd", "gdpr", "directive", "bce", "european"),
}


@dataclass
class DomainReport:
    domain: str
    jurisdiction: str
    domain_confidence: float
    jurisdiction_confidence: float
    domain_hits: list[str]
    jurisdiction_hits: list[str]

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "jurisdiction": self.jurisdiction,
            "domain_confidence": round(self.domain_confidence, 3),
            "jurisdiction_confidence": round(self.jurisdiction_confidence, 3),
            "domain_hits": self.domain_hits[:6],
            "jurisdiction_hits": self.jurisdiction_hits[:6],
        }


def _score_hits(text: str, needles: tuple[str, ...]) -> tuple[float, list[str]]:
    low = text.lower()
    hits = [n for n in needles if re.search(r"\b" + re.escape(n) + r"\b", low)]
    score = min(1.0, len(hits) / 3.0) if hits else 0.0
    return score, hits


def classify(prompt: str) -> DomainReport:
    """Detecte domaine + juridiction avec un score de confiance simple."""
    best_domain: tuple[str, float, list[str]] = ("inconnu", 0.0, [])
    for dom, needles in DOMAIN_MAP.items():
        score, hits = _score_hits(prompt or "", needles)
        if score > best_domain[1]:
            best_domain = (dom, score, hits)

    best_juris: tuple[str, float, list[str]] = ("DZ", 0.0, [])
    for juris, needles in JURISDICTION_MAP.items():
        score, hits = _score_hits(prompt or "", needles)
        if score > best_juris[1]:
            best_juris = (juris, score, hits)

    return DomainReport(
        domain=best_domain[0],
        jurisdiction=best_juris[0] if best_juris[1] > 0 else "DZ",
        domain_confidence=best_domain[1],
        jurisdiction_confidence=best_juris[1],
        domain_hits=best_domain[2],
        jurisdiction_hits=best_juris[2],
    )
