"""Upgrades 20, 33, 34 - Patch-only rework + corrections typees + revalidation causale.

Chaque correctif est classe en un PatchType qui dicte :
- sa matrice de revalidation obligatoire (couches a rejouer)
- le budget maximal (nb fichiers touches) avant bascule en regen_required
- la priorite dans la reactualisation du pipeline

Couches de revalidation (layers) :
- structure : AST, imports, level_0
- contract  : schemas, contracts json, OpenAPI
- security  : bandit, secrets
- data      : migrations, BDD
- behavior  : pytest + integration
- all       : regen complet
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PatchType(str, Enum):
    LOCAL_FIX    = "local_fix"        # 1-2 fichiers, logique isolee
    CONTRACT_FIX = "contract_fix"     # changement schema ou endpoint signature
    SECURITY_FIX = "security_fix"     # correction vulnerabilite
    SCHEMA_FIX   = "schema_fix"       # migration BDD
    BEHAVIOR_FIX = "behavior_fix"     # regression / bug comportement
    REGEN        = "regen_required"   # patch trop large -> regenerer


# Budget max en fichiers modifies avant bascule vers regen_required
FILE_BUDGET: dict[PatchType, int] = {
    PatchType.LOCAL_FIX:    3,
    PatchType.CONTRACT_FIX: 6,
    PatchType.SECURITY_FIX: 8,
    PatchType.SCHEMA_FIX:   5,
    PatchType.BEHAVIOR_FIX: 10,
    PatchType.REGEN:        9999,
}

# Matrice revalidation : layers a rejouer selon le type de patch
REVALIDATION_MATRIX: dict[PatchType, tuple[str, ...]] = {
    PatchType.LOCAL_FIX:    ("structure", "behavior"),
    PatchType.CONTRACT_FIX: ("structure", "contract", "behavior"),
    PatchType.SECURITY_FIX: ("structure", "security", "behavior"),
    PatchType.SCHEMA_FIX:   ("structure", "data", "contract", "behavior"),
    PatchType.BEHAVIOR_FIX: ("structure", "behavior"),
    PatchType.REGEN:        ("all",),
}


@dataclass
class PatchPlan:
    type: PatchType
    files_changed: list[str] = field(default_factory=list)
    layers_to_revalidate: list[str] = field(default_factory=list)
    exceeded_budget: bool = False
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "files_changed": self.files_changed,
            "layers_to_revalidate": self.layers_to_revalidate,
            "exceeded_budget": self.exceeded_budget,
            "rationale": self.rationale,
        }


def classify_patch(
    files_changed: list[str],
    declared_type: PatchType = PatchType.LOCAL_FIX,
    touches_schema_sql: bool = False,
    touches_security_files: bool = False,
    touches_contract_json: bool = False,
) -> PatchPlan:
    """Classe le patch et calcule la matrice de revalidation a appliquer."""
    effective = declared_type

    if touches_schema_sql:
        effective = PatchType.SCHEMA_FIX
    elif touches_contract_json:
        effective = PatchType.CONTRACT_FIX
    elif touches_security_files:
        effective = PatchType.SECURITY_FIX

    budget = FILE_BUDGET.get(effective, 3)
    exceeded = len(files_changed) > budget
    if exceeded:
        effective = PatchType.REGEN

    layers = list(REVALIDATION_MATRIX[effective])
    return PatchPlan(
        type=effective,
        files_changed=files_changed,
        layers_to_revalidate=layers,
        exceeded_budget=exceeded,
        rationale=(f"{len(files_changed)} fichier(s) modifie(s), "
                   f"budget={budget}, type={effective.value}"),
    )


def required_layers_from_diff(diff_paths: list[str]) -> list[str]:
    """Upgrade 34 - determine les couches touchees depuis le diff seul."""
    layers: set[str] = {"structure"}  # toujours structure
    for p in diff_paths:
        if p.endswith(".sql") or "migrations/" in p:
            layers.add("data")
            layers.add("contract")
        if "agent_contracts/" in p or "schemas.py" in p:
            layers.add("contract")
        if "security" in p.lower() or "auth" in p.lower():
            layers.add("security")
        if p.startswith("tests/") or p.endswith("_test.py"):
            layers.add("behavior")
        if p.startswith("app/") and p.endswith(".py"):
            layers.add("behavior")
    return sorted(layers)
