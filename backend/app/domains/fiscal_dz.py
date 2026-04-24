"""Domaine fiscal Algerie : IRG, IBS, TVA, TAP, IVR."""
from __future__ import annotations

from typing import ClassVar

from app.domains._base import RulesBasedDomain


class FiscalDZDomain(RulesBasedDomain):
    domain_id: ClassVar[str] = "fiscal_dz"
    version: ClassVar[str] = "2026.01"
    description: ClassVar[str] = (
        "Fiscalite Algerie : IRG (tranches), IBS (selon activite), "
        "TVA (19/9/0), TAP (2% CA), droits timbre"
    )
    required_fields: ClassVar[tuple[str, ...]] = ()
    supported_operations: ClassVar[tuple[str, ...]] = (
        "calculate_irg", "calculate_ibs", "calculate_tva",
        "calculate_tap", "declaration_ivr",
    )
    schema: ClassVar[dict] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "revenu_annuel": {"type": "number", "minimum": 0},
            "benefice_imposable": {"type": "number", "minimum": 0},
            "ca_annuel": {"type": "number", "minimum": 0},
            "ht": {"type": "number", "minimum": 0},
            "activite": {"type": "string",
                          "enum": ["production", "btp", "tourisme",
                                   "agriculture", "services", "commerce"]},
            "regime": {"type": "string",
                        "enum": ["reel", "forfait", "simplifie"]},
            "produit_type": {"type": "string",
                              "enum": ["normal", "reduit", "exonere"]},
            "destinataire": {"type": "string",
                              "enum": ["local", "export"]},
        },
        "additionalProperties": True,
    }
