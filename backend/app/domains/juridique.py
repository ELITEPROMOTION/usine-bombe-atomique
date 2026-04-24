"""Domaine juridique : contrats, baux, actes notaries, droits enregistrement."""
from __future__ import annotations

from typing import ClassVar

from app.domains._base import RulesBasedDomain


class JuridiqueDomain(RulesBasedDomain):
    domain_id: ClassVar[str] = "juridique"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Juridique DZ : contrats vente, baux commerciaux, actes notaries, "
        "droits d'enregistrement, succession, conformite CCC"
    )
    required_fields: ClassVar[tuple[str, ...]] = ("type_acte",)
    supported_operations: ClassVar[tuple[str, ...]] = (
        "valider_contrat", "calculer_droits", "verifier_conformite",
        "generer_acte",
    )
    schema: ClassVar[dict] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["type_acte"],
        "properties": {
            "type_acte": {"type": "string",
                           "enum": ["vente", "bail_commercial", "bail_habitation",
                                    "donation", "succession", "contrat_travail",
                                    "societe", "caution"]},
            "categorie": {"type": "string",
                           "enum": ["immobilier", "mobilier", "service", "financier"]},
            "prix": {"type": "number", "minimum": 0},
            "vendeur": {"type": ["string", "object", "null"]},
            "acheteur": {"type": ["string", "object", "null"]},
            "duree_mois": {"type": "integer", "minimum": 0},
            "loyer_mensuel": {"type": "number", "minimum": 0},
            "caution": {"type": "number", "minimum": 0},
            "revision_annuelle": {"type": "number"},
        },
        "additionalProperties": True,
    }
