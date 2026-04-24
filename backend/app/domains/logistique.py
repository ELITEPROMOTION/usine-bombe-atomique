"""Domaine logistique : stocks multi-entrepots, import/export DZ, tracabilite."""
from __future__ import annotations

from typing import ClassVar

from app.domains._base import RulesBasedDomain


class LogistiqueDomain(RulesBasedDomain):
    domain_id: ClassVar[str] = "logistique"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = (
        "Logistique : stocks multi-entrepots, valorisation (FIFO/LIFO/CMP), "
        "import/export DZ (droits de douane), tracabilite, peremption"
    )
    required_fields: ClassVar[tuple[str, ...]] = ()
    supported_operations: ClassVar[tuple[str, ...]] = (
        "verifier_stock", "calculer_reappro", "valoriser_stock",
        "calculer_droits_douane", "alerter_peremption",
    )
    schema: ClassVar[dict] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "operation": {"type": "string",
                           "enum": ["import", "export", "transfert",
                                    "inventaire", "reappro"]},
            "categorie": {"type": "string",
                           "enum": ["standard", "matiere_premiere",
                                    "strategique", "luxe", "alimentaire"]},
            "stock_actuel": {"type": "number", "minimum": 0},
            "seuil_min": {"type": "number", "minimum": 0},
            "seuil_max": {"type": "number", "minimum": 0},
            "seuil_critique": {"type": "number", "minimum": 0},
            "prix_unitaire": {"type": "number", "minimum": 0},
            "valeur_caf": {"type": "number", "minimum": 0},
            "methode": {"type": "string",
                         "enum": ["fifo", "lifo", "cmp"]},
            "jours_avant_peremption": {"type": "integer"},
        },
        "additionalProperties": True,
    }
