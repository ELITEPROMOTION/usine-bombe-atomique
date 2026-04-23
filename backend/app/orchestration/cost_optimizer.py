"""Cost Optimizer V3 - selection Haiku / Sonnet / Opus selon la tache.

Heuristiques :
- Haiku  : spec courte (< 1500 chars), priorite low/medium, peu de domaines, CRUD simple
- Sonnet : defaut raisonnable ; Classe B, conformite requise, multi-ressources
- Opus   : spec longue (> 6000 chars) OU priorite critical OU 3+ domaines OU
           Tri-Cerveau en raffinement

Tarifs 2026 (par million de tokens) :
- claude-haiku-4-5  : $0.25 input / $1.25 output
- claude-sonnet-4-6 : $3.00 / $15.00
- claude-opus-4-7   : $15.00 / $75.00

Le module expose aussi `estimate_cost()` et `record_actual_usage()` qui ecrit
dans la table `api_usage` existante (ch.6 du CDC).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import asyncpg

from app.orchestration.memory_engine import extract_domain_tags

logger = logging.getLogger(__name__)

ModelTier = Literal["haiku", "sonnet", "opus"]


PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":     (0.25, 1.25),
    "claude-sonnet-4-6":    (3.00, 15.00),
    "claude-opus-4-7":      (15.00, 75.00),
}

MODEL_IDS: dict[ModelTier, str] = {
    "haiku":  "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}


@dataclass
class Selection:
    tier: ModelTier
    model_id: str
    rationale: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    signals: dict[str, float | int | bool | str]


def estimate_tokens(spec: str) -> tuple[int, int]:
    """Approximation : 1 token ~ 4 caracteres. Output ~ 3x input (code genere)."""
    inp = max(500, len(spec or "") // 4)
    out = max(1500, inp * 3)
    return inp, min(out, 16000)


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Cout USD estime pour un run au tarif 2026 (MTok in/out)."""
    rates = PRICING_USD_PER_MTOK.get(model_id, (0.0, 0.0))
    return round((rates[0] * input_tokens + rates[1] * output_tokens) / 1_000_000, 6)


def select_model(
    spec: str,
    priority: str = "high",
    refinement_round: int = 0,
) -> Selection:
    """Selectionne le tier de modele selon la spec et la priorite."""
    spec_len = len(spec or "")
    domains = extract_domain_tags(spec)
    domain_count = len(domains)
    has_compliance = any(t in domains for t in ("dz", "paie", "vefa"))

    signals: dict[str, float | int | bool | str] = {
        "spec_length": spec_len,
        "priority": priority,
        "domain_count": domain_count,
        "has_compliance": has_compliance,
        "refinement_round": refinement_round,
    }

    # Regles ordre descendant de priorite
    if priority == "critical" or spec_len > 6000 or domain_count >= 3 or refinement_round >= 1:
        tier: ModelTier = "opus"
        rationale = "Tache critique / spec longue / multi-domaine / raffinement -> Opus"
    elif priority == "low" and spec_len < 1500 and domain_count <= 1 and not has_compliance:
        tier = "haiku"
        rationale = "Tache legere sans conformite -> Haiku"
    else:
        tier = "sonnet"
        rationale = "Par defaut : Sonnet (equilibre cout/qualite)"

    model_id = MODEL_IDS[tier]
    inp, out = estimate_tokens(spec)
    cost = estimate_cost(model_id, inp, out)
    return Selection(
        tier=tier,
        model_id=model_id,
        rationale=rationale,
        estimated_input_tokens=inp,
        estimated_output_tokens=out,
        estimated_cost_usd=cost,
        signals=signals,
    )


async def record_actual_usage(
    pool: asyncpg.Pool,
    task_id: str,
    agent_id: str,
    model_id: str,
    tokens_input: int,
    tokens_output: int,
    latency_ms: int,
) -> float:
    """Ecrit la consommation reelle dans api_usage et renvoie le cout calcule."""
    cost = estimate_cost(model_id, tokens_input, tokens_output)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO api_usage
              (task_id, agent_id, provider, model, tokens_input, tokens_output,
               cost_usd, latency_ms)
            VALUES ($1,$2,'anthropic',$3,$4,$5,$6,$7)
            """,
            UUID(task_id), agent_id, model_id,
            int(tokens_input), int(tokens_output), cost, int(latency_ms),
        )
    return cost


async def total_cost_for_task(pool: asyncpg.Pool, task_id: str) -> float:
    """Somme des couts USD enregistres dans `api_usage` pour une tache."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM api_usage WHERE task_id = $1",
            UUID(task_id),
        )
    return float(row["total"] if row else 0)
