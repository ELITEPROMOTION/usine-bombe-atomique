"""V5.2 BLOC 3 - Reasoning Engine (cadre).

Force toute decision REASONABLE a produire un ReasoningTrace structure :
  - contraintes : "je dois choisir X parmi [options]"
  - alternatives considerees + raison de rejet
  - confidence_score 0..1
  - invariants verifies

Flow :
  1. guard(domain) via reasoning_boundaries
  2. build ReasoningContext (options, criteria, bounds)
  3. appel LLM OU decide_deterministic
  4. post-check par invariants_runtime.verify_post
  5. persist decisions_audit

Le module ne fait PAS d'appel LLM direct ici : il fournit le cadre.
L'appelant (agent) injecte son provider via decide().
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg

from app.governance import invariants_runtime, reasoning_boundaries
from app.governance._json_utils import parse_jsonb
from app.governance.invariants_runtime import InvariantResult

logger = logging.getLogger(__name__)


@dataclass
class ReasoningContext:
    task_id: str | None
    domain: str                           # doit etre whitelisted
    question: str                         # formulation pour LLM
    options: list[str]                    # choix possibles (whitelist)
    criteria: list[str]                   # criteres consideres
    bounds: dict[str, Any] = field(default_factory=dict)
    memory_hits: list[str] = field(default_factory=list)
    correlation_id: str | None = None
    actor: str = "reasoning_engine"


@dataclass
class ReasoningTrace:
    chosen_value: str
    alternatives_considered: list[dict[str, Any]]  # [{name, reason_rejected}]
    reasoning_trace: str
    confidence_score: float
    bounds_respected: bool
    invariants_checked: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen_value": self.chosen_value,
            "alternatives_considered": self.alternatives_considered,
            "reasoning_trace": self.reasoning_trace,
            "confidence_score": round(self.confidence_score, 4),
            "bounds_respected": self.bounds_respected,
            "invariants_checked": self.invariants_checked,
        }


def _context_hash(ctx: ReasoningContext) -> str:
    canon = json.dumps({
        "domain": ctx.domain, "question": ctx.question,
        "options": sorted(ctx.options), "criteria": sorted(ctx.criteria),
        "bounds": ctx.bounds,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def decide_deterministic(
    ctx: ReasoningContext,
) -> ReasoningTrace:
    """Decideur deterministe : premier option de la whitelist.

    Sert de fallback quand aucun LLM n'est disponible et pour les tests.
    """
    if not ctx.options:
        raise ValueError("ReasoningContext.options vide")
    chosen = ctx.options[0]
    alts = [{"name": o, "reason_rejected": "ordre whitelist (deterministe)"}
            for o in ctx.options[1:]]
    trace = (f"Domaine={ctx.domain}. Question={ctx.question!r}. "
             f"Options={ctx.options}. "
             f"Criteres={ctx.criteria}. "
             f"Memoire={len(ctx.memory_hits)} hits. "
             f"Strategie=deterministic (first_option).")
    return ReasoningTrace(
        chosen_value=chosen, alternatives_considered=alts,
        reasoning_trace=trace, confidence_score=0.80,
        bounds_respected=True, invariants_checked=["whitelist_domain"],
    )


def validate_output(
    ctx: ReasoningContext, trace: ReasoningTrace,
) -> list[InvariantResult]:
    """Post-check : la decision respecte-t-elle les invariants ?"""
    results: list[InvariantResult] = []
    # chosen_value DOIT etre dans options
    ok_in_options = trace.chosen_value in ctx.options
    results.append(InvariantResult(
        "chosen_value_in_options", "REASONING",
        passed=ok_in_options,
        details={"chosen": trace.chosen_value, "options": ctx.options},
    ))
    # confidence_score dans [0..1]
    results.append(InvariantResult(
        "confidence_in_0_1", "REASONING",
        passed=0.0 <= trace.confidence_score <= 1.0,
        details={"confidence": trace.confidence_score},
    ))
    # reasoning_trace non vide
    results.append(InvariantResult(
        "reasoning_trace_non_empty", "REASONING",
        passed=bool(trace.reasoning_trace and len(trace.reasoning_trace) > 20),
        details={"len": len(trace.reasoning_trace or "")},
    ))
    return results


async def decide(
    pool: asyncpg.Pool, ctx: ReasoningContext,
    decider: Callable[[ReasoningContext], ReasoningTrace] | None = None,
) -> ReasoningTrace:
    """Execute le reasoning : guard, choose, validate, persist."""
    # Step 1 : guard whitelist
    reasoning_boundaries.guard(ctx.domain)

    # Step 2 : run decider (fallback deterministic)
    chosen_fn = decider or decide_deterministic
    trace = chosen_fn(ctx)

    # Step 3 : validate
    results = validate_output(ctx, trace)
    failures = [r for r in results if not r.passed]
    if failures:
        # Persist reject + raise
        await _persist_decision(pool, ctx, trace, results, rejected=True)
        raise invariants_runtime.InvariantViolation(
            f"reasoning output invalide : {[f.name for f in failures]}")

    # Step 4 : persist OK
    await _persist_decision(pool, ctx, trace, results, rejected=False)
    return trace


async def _persist_decision(
    pool: asyncpg.Pool, ctx: ReasoningContext, trace: ReasoningTrace,
    invariants_results: list[InvariantResult], rejected: bool,
) -> str:
    ctx_hash = _context_hash(ctx)
    inv_check = [{"name": r.name, "passed": r.passed,
                   "family": r.family, "details": r.details}
                  for r in invariants_results]
    bounds_ok = all(r.passed for r in invariants_results)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO decisions_audit
              (task_id, context_hash, domain, category, chosen_value,
               alternatives_considered, reasoning_trace, confidence_score,
               bounds_respected, invariants_checked, actor, correlation_id)
            VALUES ($1, $2, $3, 'REASONABLE', $4::jsonb, $5::jsonb,
                    $6, $7, $8, $9::jsonb, $10, $11)
            RETURNING decision_id
            """,
            UUID(ctx.task_id) if ctx.task_id else None,
            ctx_hash, ctx.domain[:80],
            json.dumps(trace.chosen_value),
            json.dumps(trace.alternatives_considered),
            trace.reasoning_trace[:8000],
            trace.confidence_score,
            bounds_ok and not rejected,
            json.dumps(inv_check),
            ctx.actor, (ctx.correlation_id or "")[:64] or None,
        )
    return str(row["decision_id"])


async def fetch_by_task(
    pool: asyncpg.Pool, task_id: str, limit: int = 50,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT decision_id, domain, category, chosen_value,
                   reasoning_trace, confidence_score, bounds_respected,
                   invariants_checked, actor, created_at
            FROM decisions_audit WHERE task_id = $1::uuid
            ORDER BY created_at ASC LIMIT $2
            """, task_id, limit,
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        chosen = parse_jsonb(r["chosen_value"])
        out.append({
            "decision_id": str(r["decision_id"]),
            "domain": r["domain"], "category": r["category"],
            "chosen_value": chosen,
            "reasoning_trace": r["reasoning_trace"],
            "confidence_score": float(r["confidence_score"] or 0),
            "bounds_respected": r["bounds_respected"],
            "actor": r["actor"],
            "at": r["created_at"].isoformat(),
        })
    return out


async def replay(
    pool: asyncpg.Pool, decision_id: str,
) -> dict[str, Any]:
    """Rejoue offline une decision avec le meme context_hash. Compare."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT context_hash, domain, chosen_value,
                   reasoning_trace, confidence_score, alternatives_considered
            FROM decisions_audit WHERE decision_id = $1::uuid
            """, decision_id,
        )
    if not row:
        return {"found": False}
    alts = row["alternatives_considered"]
    if isinstance(alts, str):
        alts = json.loads(alts or "[]")
    options = [row["chosen_value"].strip('"')] + [
        a.get("name") for a in alts if a.get("name")]
    # Clean chosen option label
    chosen = parse_jsonb(row["chosen_value"])
    ctx = ReasoningContext(
        task_id=None, domain=row["domain"], question="replay",
        options=options, criteria=[], actor="replayer",
    )
    trace = decide_deterministic(ctx)
    same = trace.chosen_value == chosen
    return {
        "found": True,
        "original": {"chosen": chosen,
                      "confidence": float(row["confidence_score"] or 0)},
        "replayed": trace.to_dict(),
        "deterministic_match": same,
    }
