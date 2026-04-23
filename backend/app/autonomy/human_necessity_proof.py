"""V5.1 BLOC 2 - Human Necessity Proof.

Avant toute escalation vers Ahmed, on EXIGE une preuve structuree :
  1. Quel(s) niveau(x) de l'ambiguity_resolver ont ete tentes ?
  2. Que donnerait une continuation sans humain (counterfactual) ?
  3. Est-ce un hard_boundary (paiement/RGPD) ?
  4. Le lease existant ne couvre-t-il pas deja l'action ?

Si preuve invalide -> l'escalation est refusee et le systeme continue
automatiquement via autonomy_ladder (PROBE/DEFER/CONSTRAIN).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg

from app.autonomy import (
    ambiguity_resolver,
    hard_boundary_registry,
    permission_lease_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class NecessityEvidence:
    form_type: str                # 'A'|'B'|'C'
    c_sub_type: str | None
    scope: str                     # ex: "payment.datadog"
    task_id: str | None
    correlation_id: str | None
    question_or_reason: str
    context: str = ""
    # remplis par prove()
    levels_tried: list[dict[str, Any]] = field(default_factory=list)
    counterfactual: dict[str, Any] = field(default_factory=dict)
    hard_boundary_hit: dict[str, Any] | None = None
    lease_covers: bool = False


@dataclass
class ProofVerdict:
    proved: bool
    proof_hash: str
    reason: str
    evidence: NecessityEvidence


async def _counterfactual(
    ev: NecessityEvidence,
) -> dict[str, Any]:
    """Decrit ce que FERAIT le systeme sans humain (non destructif)."""
    sketch: dict[str, Any]
    if ev.form_type == "A":
        sketch = {
            "path": "credential_vault_universal -> auth_prefetcher",
            "fallback": "fallback_chain -> open-source equivalent",
            "risk": "low",
        }
    elif ev.form_type == "B":
        sketch = {
            "path": "fallback_chain -> free_tier detection",
            "fallback": "defer 7d + evaluate cost/benefit ratio",
            "risk": "medium (perf degraded if no free tier)",
        }
    else:
        sketch = {
            "path": "apply_conservative_default -> monitor drift",
            "fallback": "CONSTRAIN mode (limited scope) then PROBE",
            "risk": "low (reversible action)",
        }
    sketch["sub_type"] = ev.c_sub_type
    return sketch


async def prove(
    pool: asyncpg.Pool, ev: NecessityEvidence,
) -> ProofVerdict:
    """Construit la preuve et verdict."""
    # 1. Tentative ambiguity L1..L3 si form C
    if ev.form_type == "C":
        res = await ambiguity_resolver.resolve(
            pool, ev.question_or_reason, context=ev.context,
            task_id=ev.task_id, correlation_id=ev.correlation_id,
        )
        ev.levels_tried.append({"level": res.level_resolved,
                                 "resolved": res.resolved, "kind": res.kind})
        if res.resolved:
            return _verdict(False, ev,
                            reason=f"ambiguity resolved at L{res.level_resolved}: "
                                    f"{res.resolution}")

    # 2. Hard boundary ?
    hits = await hard_boundary_registry.check(pool, [ev.scope])
    if hits:
        ev.hard_boundary_hit = hits[0]
        # Une hard boundary -> escalation OBLIGATOIRE et PROUVEE
        return _verdict(True, ev, reason=f"hard boundary: {hits[0]['scope']}")

    # 3. Lease actif ?
    lease = await permission_lease_manager.find_active(pool, ev.scope)
    if lease:
        ev.lease_covers = True
        return _verdict(False, ev,
                        reason=f"lease actif #{lease.id} couvre {ev.scope}")

    # 4. Counterfactual - si l'alternative est sure, pas besoin d'humain
    ev.counterfactual = await _counterfactual(ev)
    risk = ev.counterfactual.get("risk", "medium")
    if risk == "low":
        return _verdict(False, ev,
                        reason=f"counterfactual low risk: {ev.counterfactual['path']}")

    # 5. Fallback : preuve valide -> escalation legitime
    return _verdict(True, ev,
                    reason=f"no automatic fallback, risk={risk}")


def _verdict(
    proved: bool, ev: NecessityEvidence, *, reason: str,
) -> ProofVerdict:
    digest = hashlib.sha256(
        json.dumps({
            "form_type": ev.form_type, "c_sub_type": ev.c_sub_type,
            "scope": ev.scope, "reason": reason,
            "levels": ev.levels_tried,
            "counterfactual": ev.counterfactual,
        }, sort_keys=True).encode()
    ).hexdigest()
    return ProofVerdict(proved=proved, proof_hash=digest,
                         reason=reason, evidence=ev)


async def persist(
    pool: asyncpg.Pool, v: ProofVerdict,
) -> int:
    ev = v.evidence
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO human_necessity_proofs(
                task_id, correlation_id, form_type, c_sub_type,
                levels_tried, counterfactual, proof_hash, verdict, reason
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9)
            RETURNING id
            """,
            UUID(ev.task_id) if ev.task_id else None,
            (ev.correlation_id or "")[:64] or None,
            ev.form_type, ev.c_sub_type,
            json.dumps(ev.levels_tried), json.dumps(ev.counterfactual),
            v.proof_hash, "proved" if v.proved else "rejected",
            v.reason[:500],
        )
    return int(row["id"])


async def recent_rejections(
    pool: asyncpg.Pool, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT form_type, c_sub_type, reason, created_at
            FROM human_necessity_proofs
            WHERE verdict = 'rejected'
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]
