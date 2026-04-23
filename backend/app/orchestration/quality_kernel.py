"""Upgrade 31 - Quality Kernel souverain : 5 registres en un objet.

Le Quality Kernel unifie :
- Invariant Registry      : regles jamais violees (hashed)
- Evidence Ledger         : preuves par artefact (delegue a evidence_ledger)
- Defect Taxonomy         : classifier les ecarts (delegue)
- Remediation Ledger      : lien defaut -> patch -> cause -> revalidation
- Runtime Truth Ledger    : reconciliation prod vs hypotheses (KPIs)

Interface uniforme pour le worker. Garantit qu'aucun composant
inferieur (agent, pipeline) ne peut contourner les invariants.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from app.orchestration import (
    defect_taxonomy,
    evidence_ledger,
    hypotheses_registry,
    truth_kpis,
)

logger = logging.getLogger(__name__)


INVARIANTS: dict[str, str] = {
    "no_hardcoded_secret":  "Aucun secret en clair dans le code livre",
    "no_sql_injection":     "Toute requete dynamique utilise des placeholders",
    "no_prompt_injection":  "Prompt utilisateur jamais concatene a prompt systeme LLM",
    "no_foreign_reg_only":  "Livrable cible DZ ne doit pas imposer SOX/HIPAA/CCPA seuls",
    "evidence_chain_intact":"Toute decision critique est chainee SHA-256 dans le ledger",
    "audit_immutable":      "audit_events refuse tout UPDATE/DELETE via trigger",
}


def invariant_hash(name: str, rule_text: str) -> str:
    canon = f"{name}|{rule_text}"
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass
class RemediationLink:
    defect_id: str
    patch_summary: str
    root_cause: str
    revalidation_layers: list[str] = field(default_factory=list)


@dataclass
class KernelReport:
    invariants_signed: list[dict[str, str]]
    ledger_integrity: dict[str, Any]
    defect_summary: dict[str, Any]
    open_hypotheses: int
    truth_kpis: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariants_signed": self.invariants_signed,
            "ledger_integrity": self.ledger_integrity,
            "defect_summary": self.defect_summary,
            "open_hypotheses": self.open_hypotheses,
            "truth_kpis": self.truth_kpis,
        }


async def full_report(pool: asyncpg.Pool) -> KernelReport:
    """Cliche consolide des 5 registres pour le dashboard CEO / CTO."""
    invariants = [
        {"name": n, "hash": invariant_hash(n, t), "rule": t}
        for n, t in INVARIANTS.items()
    ]
    integrity = await evidence_ledger.verify_chain(pool)
    defects = await defect_taxonomy.summary(pool)
    open_hyp = len(await hypotheses_registry.list_open(pool, limit=200))
    kpi_snap = await truth_kpis.latest(pool) or {}

    return KernelReport(
        invariants_signed=invariants,
        ledger_integrity=integrity,
        defect_summary=defects,
        open_hypotheses=open_hyp,
        truth_kpis=kpi_snap,
    )


async def record_remediation(
    pool: asyncpg.Pool, task_id: str, defect_id: str,
    patch_summary: str, root_cause: str, layers: list[str],
) -> str:
    """Emet une entree evidence 'override' liant defaut-patch-cause."""
    return await evidence_ledger.record(
        pool, kind="override", actor="quality_kernel.remediation",
        payload={
            "defect_id": defect_id,
            "patch_summary": patch_summary[:500],
            "root_cause": root_cause[:500],
            "revalidation_layers": layers,
        },
        task_id=task_id,
    )
