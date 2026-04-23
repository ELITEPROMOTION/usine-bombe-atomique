"""Auto-Tuner V4 - recalibrage des seuils de validation.

Lit les scores historiques de `project_memory`, recalcule les bornes
`pass_min` / `cpass_min` / `soft_fail_min` via des quantiles, et persiste
dans `validation_thresholds` (par scope : 'global' ou 'domain:<tag>').

Regles :
- Moins de 5 echantillons : seuils par defaut (0.85 / 0.70 / 0.50)
- Plus de 5 : pass_min = median des PASS, borne a [0.80, 0.92] ;
  cpass_min = p25 general, borne a [0.65, 0.80] ;
  soft_fail_min = plancher fixe 0.50.

Le pipeline `run_pipeline` lit ces seuils avant de rendre son verdict.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

DEFAULT_PASS_MIN = 0.85
DEFAULT_CPASS_MIN = 0.70
DEFAULT_SOFT_FAIL_MIN = 0.50

PASS_BOUNDS = (0.80, 0.92)
CPASS_BOUNDS = (0.65, 0.80)
MIN_SAMPLES = 5


@dataclass
class Thresholds:
    scope: str
    pass_min: float
    cpass_min: float
    soft_fail_min: float
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "pass_min": round(self.pass_min, 4),
            "cpass_min": round(self.cpass_min, 4),
            "soft_fail_min": round(self.soft_fail_min, 4),
            "sample_count": self.sample_count,
        }


def compute_thresholds(scores_pass: list[float], scores_all: list[float],
                       scope: str = "global") -> Thresholds:
    """Calcule les seuils pass/cpass/soft par quantiles sur l'historique."""
    if len(scores_all) < MIN_SAMPLES:
        return Thresholds(scope, DEFAULT_PASS_MIN, DEFAULT_CPASS_MIN,
                          DEFAULT_SOFT_FAIL_MIN, len(scores_all))

    median_pass = statistics.median(scores_pass) if scores_pass else DEFAULT_PASS_MIN
    try:
        p25 = statistics.quantiles(scores_all, n=4)[0]
    except statistics.StatisticsError:
        p25 = DEFAULT_CPASS_MIN

    pass_min = _clip(median_pass, *PASS_BOUNDS)
    cpass_min = _clip(p25, *CPASS_BOUNDS)
    # Garantir ordre strict
    cpass_min = min(cpass_min, pass_min - 0.05)
    soft_fail_min = min(DEFAULT_SOFT_FAIL_MIN, cpass_min - 0.10)
    return Thresholds(scope, pass_min, cpass_min, soft_fail_min, len(scores_all))


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


async def load_thresholds(pool: asyncpg.Pool, scope: str = "global") -> Thresholds:
    """Charge les seuils persistes pour un scope (defaut si absent)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT scope, pass_min, cpass_min, soft_fail_min, sample_count
            FROM validation_thresholds WHERE scope = $1
            """,
            scope,
        )
    if not row:
        return Thresholds(scope, DEFAULT_PASS_MIN, DEFAULT_CPASS_MIN,
                          DEFAULT_SOFT_FAIL_MIN, 0)
    return Thresholds(
        scope=row["scope"],
        pass_min=float(row["pass_min"]),
        cpass_min=float(row["cpass_min"]),
        soft_fail_min=float(row["soft_fail_min"]),
        sample_count=int(row["sample_count"]),
    )


async def retune_global(pool: asyncpg.Pool) -> Thresholds:
    """Recalcule les seuils globaux depuis project_memory."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT validation_score, verdict
            FROM project_memory
            ORDER BY created_at DESC
            LIMIT 200
            """
        )
    scores_all = [float(r["validation_score"]) for r in rows]
    scores_pass = [float(r["validation_score"]) for r in rows
                   if r["verdict"] in ("PASS", "CONDITIONAL_PASS")]
    thresholds = compute_thresholds(scores_pass, scores_all, scope="global")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO validation_thresholds
              (scope, pass_min, cpass_min, soft_fail_min, sample_count, last_recomputed_at)
            VALUES ($1,$2,$3,$4,$5, NOW())
            ON CONFLICT (scope) DO UPDATE SET
              pass_min = EXCLUDED.pass_min,
              cpass_min = EXCLUDED.cpass_min,
              soft_fail_min = EXCLUDED.soft_fail_min,
              sample_count = EXCLUDED.sample_count,
              last_recomputed_at = NOW()
            """,
            thresholds.scope, thresholds.pass_min, thresholds.cpass_min,
            thresholds.soft_fail_min, thresholds.sample_count,
        )
    logger.info("auto_tuner retuned: %s", thresholds.to_dict())
    return thresholds


async def list_all(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Retourne toutes les lignes de `validation_thresholds` (tous scopes)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT scope, pass_min, cpass_min, soft_fail_min, sample_count, last_recomputed_at "
            "FROM validation_thresholds ORDER BY scope"
        )
    return [
        {
            "scope": r["scope"],
            "pass_min": float(r["pass_min"]),
            "cpass_min": float(r["cpass_min"]),
            "soft_fail_min": float(r["soft_fail_min"]),
            "sample_count": r["sample_count"],
            "last_recomputed_at": r["last_recomputed_at"].isoformat(),
        }
        for r in rows
    ]
