"""Domaine RH : paie DZ, CNAS/CASNOS, conges legaux, declarations DAS/CTD."""
from __future__ import annotations

from typing import ClassVar

from app.domains._base import RulesBasedDomain


class RHDomain(RulesBasedDomain):
    domain_id: ClassVar[str] = "rh"
    version: ClassVar[str] = "2026.01"
    description: ClassVar[str] = (
        "RH DZ : cycle paie (brut/net/IRG/CNAS), conges annuels + maternite + "
        "maladie, SMIG verification, declarations legales"
    )
    required_fields: ClassVar[tuple[str, ...]] = ()
    supported_operations: ClassVar[tuple[str, ...]] = (
        "calculer_paie", "calculer_conges", "verifier_smig",
        "declarer_das_ctd", "generer_bulletin",
    )
    schema: ClassVar[dict] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "salaire_brut_mensuel": {"type": "number", "minimum": 0},
            "anciennete_mois": {"type": "integer", "minimum": 0},
            "mois_travailles": {"type": "integer", "minimum": 0},
            "nb_personnes_charge": {"type": "integer", "minimum": 0},
            "type_conge": {"type": "string",
                            "enum": ["annuel", "maternite", "maladie",
                                     "paternite", "exceptionnel"]},
            "statut": {"type": "string",
                        "enum": ["cdi", "cdd", "stagiaire", "apprenti"]},
        },
        "additionalProperties": True,
    }
