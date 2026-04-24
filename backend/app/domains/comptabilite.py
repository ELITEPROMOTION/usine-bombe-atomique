"""Domaine comptabilite : SCF Algerie, plan comptable, ecritures, bilans."""
from __future__ import annotations

from typing import ClassVar

from app.domains._base import RulesBasedDomain


class ComptabiliteDomain(RulesBasedDomain):
    domain_id: ClassVar[str] = "comptabilite"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Comptabilite DZ SCF : plan comptable 7 classes, ecritures analytiques, "
        "TVA deductible/collectee, bilan + compte resultat + grand livre"
    )
    required_fields: ClassVar[tuple[str, ...]] = ()
    supported_operations: ClassVar[tuple[str, ...]] = (
        "classer_compte", "valider_ecriture", "generer_bilan",
        "cloturer_exercice", "rapprochement_bancaire",
    )
    schema: ClassVar[dict] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "numero_compte": {"type": "integer", "minimum": 100, "maximum": 799},
            "type": {"type": "string",
                      "enum": ["ecriture", "journal", "bilan", "classe_compte"]},
            "nature": {"type": "string",
                        "enum": ["achat", "vente", "op_diverse", "salaires",
                                 "impots", "tresorerie"]},
            "total_debit": {"type": "number", "minimum": 0},
            "total_credit": {"type": "number", "minimum": 0},
            "exercice": {"type": "integer"},
        },
        "additionalProperties": True,
    }
