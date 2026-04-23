"""Upgrade 17 (BLOC F) - Dossier final livre a l'utilisateur.

Consolide en un unique DeliveryPackage (JSON + .md de synthese) :
- resume              : spec_hash, verdict, score
- architecture        : extrait du manifest + tenants
- outils_utilises     : registre des outils branches pendant la tache
- decisions           : judge_history + quorum + contradictions
- code                : liste d'artefacts (path + language + bytes)
- tests               : proofs pytest
- ecarts              : defauts restants
- risques             : hypotheses ouvertes
- conformite          : matrice compliance
- deploiement         : instructions Docker + Terraform
- rollback            : plan base sur rollback_events
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.orchestration import (
    compliance_matrix,
    defect_taxonomy,
    evidence_ledger,
    tool_registry,
)


@dataclass
class DeliveryPackage:
    task_id: str
    spec_hash: str
    sections: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "spec_hash": self.spec_hash,
            **self.sections,
        }

    def to_markdown(self) -> str:
        s = self.sections
        resume = s.get("resume", {})
        lines = [
            f"# Dossier de livraison - {self.task_id[:8]}",
            "",
            f"**Verdict :** {resume.get('verdict', 'n/a')}",
            f"**Score :** {resume.get('validation_score', 0):.3f}",
            f"**Confiance :** {resume.get('confidence', 0):.3f} "
            f"({resume.get('confidence_label', 'unknown')})",
            "",
            "## Resume",
            "",
            f"- spec_hash : `{self.spec_hash[:16]}...`",
            f"- duration  : {resume.get('duration_ms', 0)} ms",
            f"- artifacts : {resume.get('artifacts_count', 0)} fichiers",
            "",
            "## Outils utilises",
            "",
        ]
        for t in s.get("outils_utilises", []):
            lines.append(f"- **{t['name']}** ({t['tool_type']}) : {t['status']}")
        lines += ["", "## Ecarts restants", ""]
        for d in s.get("ecarts", [])[:10]:
            lines.append(f"- `{d.get('gravite')}` {d.get('title')}")
        lines += ["", "## Risques / Hypotheses ouvertes", ""]
        for h in s.get("risques", [])[:10]:
            lines.append(f"- [{h.get('severity')}] {h.get('description', '')[:160]}")
        lines += ["", "## Conformite", ""]
        for c in s.get("conformite", [])[:10]:
            lines.append(
                f"- {c['requirement_code']} ({c['severity']}) : {c['statut']} - {c['requirement_label'][:100]}"
            )
        lines += ["", "## Deploiement", "", s.get("deploiement", "_n/a_"), ""]
        lines += ["## Rollback", "", s.get("rollback", "_n/a_"), ""]
        return "\n".join(lines)


def _spec_hash(spec: str) -> str:
    return hashlib.sha256((spec or "").encode("utf-8")).hexdigest()


async def build(
    pool: asyncpg.Pool, task_id: str, spec: str,
    pipeline_verdict: str, pipeline_score: float,
    confidence_report: dict[str, Any],
    manifest: list[dict[str, Any]],
    agent_outputs: dict[str, dict[str, Any]] | None = None,
    duration_ms: int = 0,
) -> DeliveryPackage:
    uid = UUID(task_id)

    async with pool.acquire() as conn:
        open_hyps = await conn.fetch(
            "SELECT description, severity, plan_b FROM hypotheses "
            "WHERE task_id = $1 AND statut = 'open' ORDER BY severity DESC",
            uid,
        )

    defects = await defect_taxonomy.list_by_task(pool, task_id)
    matrix = await compliance_matrix.list_by_task(pool, task_id)
    tools = await tool_registry.list_all(pool)
    ledger_tail = await evidence_ledger.tail(pool, limit=30)

    sections: dict[str, Any] = {
        "resume": {
            "verdict": pipeline_verdict,
            "validation_score": pipeline_score,
            "confidence": confidence_report.get("composite", 0),
            "confidence_label": confidence_report.get("label", "unknown"),
            "duration_ms": duration_ms,
            "artifacts_count": len(manifest),
        },
        "architecture": {
            "files_by_language": _group_by_language(manifest),
            "top_modules": [m["path"] for m in manifest[:20]],
        },
        "outils_utilises": tools,
        "decisions": {
            "evidence_events_tail": [
                {"kind": e["kind"], "actor": e["actor"], "chain_hash": e["chain_hash"][:12]}
                for e in ledger_tail
            ],
        },
        "code": [
            {"path": m["path"], "language": m.get("language"),
             "bytes": m.get("size_bytes", 0)}
            for m in manifest
        ],
        "tests": {
            agent_id: out.get("tests_total", 0) for agent_id, out in
            (agent_outputs or {}).items() if agent_id == "agent-04-pytest"
        },
        "ecarts": defects,
        "risques": [
            {"description": r["description"],
             "severity": r["severity"],
             "plan_b": r["plan_b"]}
            for r in open_hyps
        ],
        "conformite": matrix,
        "deploiement": (
            "```bash\n"
            "docker compose -f docker-compose.yml up -d\n"
            "```\n"
            "Services : postgres (pgvector), redis, vault, sonarqube, backend, worker, frontend."
        ),
        "rollback": (
            "En cas de probleme : `docker compose down` puis restaurer le volume "
            "`pgdata` depuis snapshot. Les `rollback_events` sont persistes en BDD."
        ),
    }

    pkg = DeliveryPackage(
        task_id=task_id, spec_hash=_spec_hash(spec), sections=sections,
    )
    return pkg


def _group_by_language(manifest: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in manifest:
        lang = str(m.get("language") or "unknown")
        out[lang] = out.get(lang, 0) + 1
    return out


async def store(pool: asyncpg.Pool, pkg: DeliveryPackage) -> str:
    """Ecrit le package en evidence_ledger (kind='artifact') pour tracabilite."""
    return await evidence_ledger.record(
        pool, kind="artifact", actor="delivery_package.builder",
        payload={"package": pkg.to_dict()},
        task_id=pkg.task_id,
    )
