"""V5.4 - Reasoning Core (orchestrateur central).

Pilote les 7 etages : Decomposition → MultiPath → Graph → SelfConsistency
                       → ReAct → Reflexion → Constitutional.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg

from app.cognition import (
    bias_detector,
    cot_engine,
    meta_cognition,
    reasoning_fingerprint,
    uncertainty_quantifier,
)
from app.cognition.reasoning_trace_models import (
    BiasReport,
    ConstitutionalReport,
    MetaCognitiveReport,
    ReasoningTrace,
    UncertaintyReport,
)

logger = logging.getLogger(__name__)

RULES_VERSION = "v5.4"


@dataclass
class ReasoningRequest:
    problem_statement: str
    task_id: str | None = None
    criticality: str = "medium"
    allow_shortcut: bool = True
    budget_tokens: int | None = None


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def reason(
    pool: asyncpg.Pool, req: ReasoningRequest,
) -> ReasoningTrace:
    """Execute un raisonnement complet + persiste la trace."""
    t0 = time.perf_counter()
    decision = meta_cognition.decide_strategy(
        req.problem_statement, criticality=req.criticality)
    meta_report = meta_cognition.build_report(decision)
    fp = reasoning_fingerprint.fingerprint(
        req.problem_statement, decision.strategy_techniques, RULES_VERSION)

    # Etage 1+2+3+5+6+7 : on fait un pipeline simple (CoT uniquement ici,
    # les autres moteurs sont invoques par d'autres entry-points)
    chain = cot_engine.structured_cot(req.problem_statement)

    # Uncertainty
    uncertainty = uncertainty_quantifier.build_report(
        samples=[s.confidence for s in chain.steps] or [chain.confidence],
        sources_count=0, domain_fit=0.8,
        budget_used=len(chain.steps) * 100,
        budget_total=decision.budget_tokens,
        mean_confidence=chain.confidence,
    )

    # Bias
    bias = bias_detector.build_report(
        " ".join(s.content for s in chain.steps))

    # Trace master
    total_ms = int((time.perf_counter() - t0) * 1000)
    trace = ReasoningTrace(
        task_id=req.task_id,
        problem_statement=req.problem_statement,
        problem_type=decision.problem_type,
        technique_path=decision.strategy_techniques,
        chain=chain,
        uncertainty=uncertainty,
        bias=bias,
        meta=meta_report,
        final_answer=chain.final_answer,
        final_confidence=chain.confidence,
        reasoning_fingerprint=fp,
        total_tokens=len(chain.steps) * 100,   # estimation
        total_duration_ms=total_ms,
        status="completed",
    )
    # Persist
    await _persist(pool, trace, req.task_id)
    return trace


async def _persist(
    pool: asyncpg.Pool, trace: ReasoningTrace, task_id: str | None,
) -> None:
    async with pool.acquire() as conn:
        # Master trace row
        row = await conn.fetchrow(
            """
            INSERT INTO reasoning_traces(
                task_id, problem_statement, problem_type,
                input_hash, output_hash, rules_version, technique_path,
                final_answer, final_confidence, reasoning_fingerprint,
                total_tokens, total_duration_ms, source_refs, status,
                completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb,
                    $9, $10, $11, $12, $13::jsonb, $14, NOW())
            RETURNING trace_id
            """,
            UUID(task_id) if task_id else None,
            trace.problem_statement[:8000],
            trace.problem_type,
            _sha256(trace.problem_statement),
            _sha256(trace.final_answer or ""),
            RULES_VERSION,
            json.dumps(trace.technique_path),
            json.dumps(trace.final_answer),
            trace.final_confidence,
            trace.reasoning_fingerprint,
            trace.total_tokens, trace.total_duration_ms,
            json.dumps([]), trace.status,
        )
        tid = row["trace_id"]
        # Chain trace
        if trace.chain:
            await conn.execute(
                """
                INSERT INTO chain_traces(trace_id, mode, steps,
                    intermediate_conclusions, alternatives_rejected,
                    verification_trace, final_answer, confidence,
                    duration_ms)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb,
                        $6::jsonb, $7, $8, $9)
                """,
                tid, trace.chain.mode,
                json.dumps([s.model_dump() for s in trace.chain.steps]),
                json.dumps(trace.chain.intermediate_conclusions),
                json.dumps(trace.chain.alternatives_rejected),
                json.dumps(trace.chain.verification_trace),
                trace.chain.final_answer[:4000]
                    if trace.chain.final_answer else None,
                trace.chain.confidence, trace.total_duration_ms,
            )
        # Uncertainty
        if trace.uncertainty:
            await conn.execute(
                """
                INSERT INTO uncertainty_reports(trace_id, aleatory,
                    epistemic, ontological, computational,
                    credible_low, credible_high, propagation)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                """,
                tid, trace.uncertainty.aleatory,
                trace.uncertainty.epistemic,
                trace.uncertainty.ontological,
                trace.uncertainty.computational,
                trace.uncertainty.credible_low,
                trace.uncertainty.credible_high,
                json.dumps(trace.uncertainty.sensitivities),
            )
        # Bias
        if trace.bias:
            await conn.execute(
                """
                INSERT INTO bias_reports(trace_id, biases_detected,
                    mitigations_applied)
                VALUES ($1, $2::jsonb, $3::jsonb)
                """,
                tid,
                json.dumps(trace.bias.biases_detected),
                json.dumps(trace.bias.mitigations_applied),
            )
        # Meta
        if trace.meta:
            await conn.execute(
                """
                INSERT INTO meta_cognitive_reports(trace_id, problem_class,
                    strategy_selected, resources_allocated,
                    stuck_states_detected, loops_detected, stop_reason)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                """,
                tid, trace.meta.problem_class,
                trace.meta.strategy_selected[:60],
                json.dumps(trace.meta.resources_allocated),
                trace.meta.stuck_states_detected,
                trace.meta.loops_detected,
                (trace.meta.stop_reason or "")[:40] or None,
            )
    trace.trace_id = str(tid)


async def get_trace(
    pool: asyncpg.Pool, trace_id: str,
) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM reasoning_traces WHERE trace_id = $1",
            UUID(trace_id),
        )
    if row is None:
        return None
    d: dict[str, Any] = {}
    for k, v in dict(row).items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat() if v else None
        elif k in ("technique_path", "final_answer", "source_refs") \
                and isinstance(v, str):
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                d[k] = v
        else:
            d[k] = v
    d["trace_id"] = str(d["trace_id"])
    return d


async def list_traces(
    pool: asyncpg.Pool, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT trace_id, problem_type, technique_path,
                   final_confidence, status, created_at, reasoning_fingerprint
            FROM reasoning_traces ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    out = []
    for r in rows:
        d = dict(r)
        d["trace_id"] = str(d["trace_id"])
        d["created_at"] = d["created_at"].isoformat()
        if isinstance(d["technique_path"], str):
            try:
                d["technique_path"] = json.loads(d["technique_path"])
            except json.JSONDecodeError:
                logger.debug("json decode skipped") if "logger" in globals() else None
        d["final_confidence"] = float(d["final_confidence"] or 0)
        out.append(d)
    return out
