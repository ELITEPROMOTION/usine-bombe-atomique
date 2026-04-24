"""V5.2 BLOC 8 - Reasoning Canary.

Promotion d'une regle reasoning en 3 phases :
  SHADOW  : decide sans appliquer, compare avec legacy
  LIMITED : applique sur 1-5% du trafic
  FULL    : applique partout

Chaque promotion est journalisee dans reasoning_promotions. Si les metriques
degradent (divergence_rate eleve, quality_delta<0, invariants violes),
la promotion est REJECTED.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class CanaryMetrics:
    sample_size: int
    divergence_rate: float
    quality_delta: float
    cost_delta: float
    invariants_violated: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "divergence_rate": round(self.divergence_rate, 4),
            "quality_delta": round(self.quality_delta, 4),
            "cost_delta": round(self.cost_delta, 6),
            "invariants_violated": self.invariants_violated,
        }


# Seuils de promotion
MAX_DIVERGENCE_SHADOW = 0.30
MAX_DIVERGENCE_LIMITED = 0.15
MIN_QUALITY_DELTA = -0.01           # pas de regression qualite
MAX_INVARIANTS_VIOLATED = 0


def evaluate_shadow(
    decisions_new: list[str], decisions_legacy: list[str],
    quality_new: float, quality_legacy: float,
    cost_new: float, cost_legacy: float,
    invariants_violated: int,
) -> tuple[CanaryMetrics, bool]:
    n = max(1, len(decisions_new))
    divergent = sum(1 for a, b in zip(decisions_new, decisions_legacy, strict=False) if a != b)
    div_rate = divergent / n
    q_delta = quality_new - quality_legacy
    c_delta = cost_new - cost_legacy
    metrics = CanaryMetrics(
        sample_size=n, divergence_rate=div_rate,
        quality_delta=q_delta, cost_delta=c_delta,
        invariants_violated=invariants_violated,
    )
    can_promote = (
        div_rate <= MAX_DIVERGENCE_SHADOW
        and q_delta >= MIN_QUALITY_DELTA
        and invariants_violated <= MAX_INVARIANTS_VIOLATED
    )
    return metrics, can_promote


async def run_shadow(
    pool: asyncpg.Pool, rule_key: str, sample: dict[str, Any],
) -> dict[str, Any]:
    """Enregistre un cycle shadow et retourne metrics + can_promote.
    `sample` contient :
       - decisions_new : list[str]
       - decisions_legacy : list[str]
       - quality_new, quality_legacy : float
       - cost_new, cost_legacy : float
       - invariants_violated : int
    """
    metrics, can_promote = evaluate_shadow(
        decisions_new=sample.get("decisions_new", []),
        decisions_legacy=sample.get("decisions_legacy", []),
        quality_new=float(sample.get("quality_new", 0.0)),
        quality_legacy=float(sample.get("quality_legacy", 0.0)),
        cost_new=float(sample.get("cost_new", 0.0)),
        cost_legacy=float(sample.get("cost_legacy", 0.0)),
        invariants_violated=int(sample.get("invariants_violated", 0)),
    )
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reasoning_promotions
              (rule_key, phase, sample_size, divergence_rate,
               quality_delta, cost_delta, invariants_violated, evidence)
            VALUES ($1, 'shadow', $2, $3, $4, $5, $6, $7::jsonb)
            """,
            rule_key[:120], metrics.sample_size, metrics.divergence_rate,
            metrics.quality_delta, metrics.cost_delta,
            metrics.invariants_violated,
            json.dumps({"sample_summary": sample.get("note", "")}),
        )
    return {"metrics": metrics.to_dict(), "can_promote": can_promote}


async def promote_to_limited(
    pool: asyncpg.Pool, rule_key: str, metrics: CanaryMetrics,
) -> dict[str, Any]:
    if metrics.divergence_rate > MAX_DIVERGENCE_LIMITED:
        return await reject(pool, rule_key,
                             reason=f"divergence {metrics.divergence_rate:.3f} "
                                    f"> {MAX_DIVERGENCE_LIMITED}",
                             metrics=metrics)
    if metrics.invariants_violated > MAX_INVARIANTS_VIOLATED:
        return await reject(pool, rule_key,
                             reason="invariants violated",
                             metrics=metrics)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reasoning_promotions
              (rule_key, phase, sample_size, divergence_rate,
               quality_delta, cost_delta, invariants_violated, evidence)
            VALUES ($1, 'limited', $2, $3, $4, $5, $6, '{}'::jsonb)
            """,
            rule_key[:120], metrics.sample_size, metrics.divergence_rate,
            metrics.quality_delta, metrics.cost_delta,
            metrics.invariants_violated,
        )
    return {"phase": "limited", "metrics": metrics.to_dict()}


async def promote_to_full(
    pool: asyncpg.Pool, rule_key: str, metrics: CanaryMetrics,
) -> dict[str, Any]:
    if metrics.quality_delta < MIN_QUALITY_DELTA:
        return await reject(pool, rule_key,
                             reason=f"quality_delta {metrics.quality_delta:.3f} "
                                    f"< {MIN_QUALITY_DELTA}",
                             metrics=metrics)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reasoning_promotions
              (rule_key, phase, sample_size, divergence_rate,
               quality_delta, cost_delta, invariants_violated, evidence)
            VALUES ($1, 'full', $2, $3, $4, $5, $6, '{}'::jsonb)
            """,
            rule_key[:120], metrics.sample_size, metrics.divergence_rate,
            metrics.quality_delta, metrics.cost_delta,
            metrics.invariants_violated,
        )
    return {"phase": "full", "metrics": metrics.to_dict()}


async def reject(
    pool: asyncpg.Pool, rule_key: str, *, reason: str,
    metrics: CanaryMetrics | None = None,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reasoning_promotions
              (rule_key, phase, sample_size, divergence_rate,
               quality_delta, cost_delta, invariants_violated, evidence)
            VALUES ($1, 'rejected', $2, $3, $4, $5, $6, $7::jsonb)
            """,
            rule_key[:120],
            metrics.sample_size if metrics else 0,
            metrics.divergence_rate if metrics else 0,
            metrics.quality_delta if metrics else 0,
            metrics.cost_delta if metrics else 0,
            metrics.invariants_violated if metrics else 0,
            json.dumps({"reason": reason}),
        )
    return {"phase": "rejected", "reason": reason}


async def rollback(
    pool: asyncpg.Pool, rule_key: str, *, reason: str,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reasoning_promotions
              (rule_key, phase, evidence)
            VALUES ($1, 'rolled_back', $2::jsonb)
            """,
            rule_key[:120], json.dumps({"reason": reason}),
        )
    return {"phase": "rolled_back", "reason": reason}


async def history(
    pool: asyncpg.Pool, rule_key: str | None = None, limit: int = 30,
) -> list[dict[str, Any]]:
    sql = ("SELECT rule_key, phase, sample_size, divergence_rate, "
           "quality_delta, cost_delta, invariants_violated, "
           "evidence, promoted_at FROM reasoning_promotions ")
    args: list[Any] = []
    if rule_key:
        sql += "WHERE rule_key = $1 "
        args.append(rule_key)
    sql += f"ORDER BY promoted_at DESC LIMIT {int(limit)}"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    out: list[dict[str, Any]] = []
    for r in rows:
        ev = r["evidence"]
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except json.JSONDecodeError:
                ev = {}
        out.append({
            "rule_key": r["rule_key"], "phase": r["phase"],
            "sample_size": r["sample_size"],
            "divergence_rate": float(r["divergence_rate"] or 0),
            "quality_delta": float(r["quality_delta"] or 0),
            "cost_delta": float(r["cost_delta"] or 0),
            "invariants_violated": r["invariants_violated"],
            "evidence": ev,
            "promoted_at": r["promoted_at"].isoformat(),
        })
    return out
