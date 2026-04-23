"""Upgrade 18 - Verification Bundle : paquet unique de preuves par livraison.

Chaque cloture de tache produit un bundle JSON consolide contenant :
- spec_hash           : SHA-256 du prompt original
- test_proofs         : counts pytest + stderr tail (agent #04)
- security_proofs     : bandit/secrets/deps (agent #11)
- domain_proofs       : regles DZ (agent #18)
- coverage_proofs     : ratio tests/sources (confidence_scorer dim coverage)
- lint_proofs         : ruff issues (agent #14)
- structure_proofs    : Level 0 (AST/JSON/YAML)
- confidence_proofs   : confidence_scorer composite + dims
- pipeline_proofs     : 5 niveaux validation
- ledger_tip          : dernier chain_hash de evidence_ledger

Si une preuve obligatoire manque => bundle.missing_proofs != [] => FAIL.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

REQUIRED_PROOFS = (
    "spec_hash", "test_proofs", "security_proofs", "domain_proofs",
    "coverage_proofs", "lint_proofs", "structure_proofs",
    "confidence_proofs", "pipeline_proofs",
)


@dataclass
class Bundle:
    task_id: str
    proofs: dict[str, Any] = field(default_factory=dict)
    missing_proofs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_proofs

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "ok": self.ok,
            "missing_proofs": self.missing_proofs,
            "proofs_count": len(self.proofs),
            "proofs": self.proofs,
        }


def _proof_from_agent(agent_results: dict[str, Any], agent_id: str,
                       keys: tuple[str, ...]) -> dict[str, Any] | None:
    res = agent_results.get(agent_id)
    if not res:
        return None
    out = getattr(res, "output", None) or (res if isinstance(res, dict) else None)
    if not out:
        return None
    return {k: out.get(k) for k in keys if k in out}


def build(
    task_id: str,
    spec: str,
    agent_results: dict[str, Any],
    pipeline_levels: list[Any],
    confidence: dict[str, Any],
    structure_result: dict[str, Any],
    ledger_tip_hash: str | None = None,
) -> Bundle:
    bundle = Bundle(task_id=task_id)
    spec_hash = hashlib.sha256((spec or "").encode("utf-8")).hexdigest()

    bundle.proofs["spec_hash"] = spec_hash
    bundle.proofs["ledger_tip"] = ledger_tip_hash

    pytest_proof = _proof_from_agent(agent_results, "agent-04-pytest",
                                      ("score", "tests_total", "tests_passed",
                                       "tests_failed", "errors"))
    if pytest_proof:
        bundle.proofs["test_proofs"] = pytest_proof

    sec_proof = _proof_from_agent(agent_results, "agent-11-security",
                                   ("score", "bandit_count", "secrets_count",
                                    "deps_count"))
    if sec_proof:
        bundle.proofs["security_proofs"] = sec_proof

    dom_proof = _proof_from_agent(agent_results, "agent-18-conformite-dz",
                                   ("score", "domain", "summary"))
    if dom_proof:
        bundle.proofs["domain_proofs"] = dom_proof

    lint_proof = _proof_from_agent(agent_results, "agent-14-linter",
                                    ("score", "issues_count", "issues_by_code"))
    if lint_proof:
        bundle.proofs["lint_proofs"] = lint_proof

    dims = {d["name"]: d["score"] for d in confidence.get("dimensions", [])}
    if "coverage" in dims:
        bundle.proofs["coverage_proofs"] = {
            "ratio": dims["coverage"],
            "composite": confidence.get("composite"),
        }
    bundle.proofs["confidence_proofs"] = confidence
    bundle.proofs["structure_proofs"] = structure_result
    bundle.proofs["pipeline_proofs"] = [
        {"level": getattr(lv, "level", None) or lv.get("level"),
         "score": getattr(lv, "score", None) or lv.get("score"),
         "passed": getattr(lv, "passed", None) or lv.get("passed")}
        for lv in pipeline_levels
    ]

    bundle.missing_proofs = [p for p in REQUIRED_PROOFS if p not in bundle.proofs]
    return bundle


def bundle_digest(bundle: Bundle) -> str:
    """SHA-256 stable du bundle (pour stockage / evidence)."""
    canon = json.dumps(bundle.proofs, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
