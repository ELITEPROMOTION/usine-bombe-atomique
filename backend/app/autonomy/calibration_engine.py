"""V5.1 BLOC 5 - Calibration Engine.

Calibre les scores de confiance via Brier + isotonic simplifie :
  - Brier = moyenne((confidence - actual_outcome)^2)
  - calibration_score = 1 - Brier   (1 = parfait)
  - isotonic monotone simple : bucketing + rank mapping

Input : evidence_ledger + intervention_outcomes
Output : mapping calibre "raw_conf -> calibrated_conf"
"""
from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class CalibrationReport:
    samples: int
    brier_score: float
    calibration_score: float
    buckets: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "brier_score": round(self.brier_score, 4),
            "calibration_score": round(self.calibration_score, 4),
            "buckets": self.buckets,
        }


def _actual(outcome: dict[str, Any]) -> float:
    """1 si la prediction s'est averee bonne, 0 sinon."""
    verdict = (outcome or {}).get("verdict", "")
    success = (outcome or {}).get("success")
    if success is not None:
        return 1.0 if success else 0.0
    return 1.0 if verdict in ("robust", "ok", "promoted") else 0.0


def _parse_payload(raw: Any) -> dict[str, Any] | None:
    p = raw
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except json.JSONDecodeError:
            return None
    return p if isinstance(p, dict) else None


def _extract_prediction(payload: dict[str, Any]) -> tuple[float, float] | None:
    conf = payload.get("confidence")
    if conf is None:
        return None
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= c <= 1.0):
        return None
    return c, _actual(payload)


def _build_buckets(preds: list[tuple[float, float]]) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        bucket = [(c, a) for c, a in preds if lo <= c < hi]
        if not bucket:
            continue
        avg_conf = statistics.mean(c for c, _ in bucket)
        avg_act = statistics.mean(a for _, a in bucket)
        buckets.append({
            "range": f"{lo:.1f}-{hi:.2f}", "n": len(bucket),
            "avg_confidence": round(avg_conf, 3),
            "avg_outcome": round(avg_act, 3),
            "gap": round(avg_conf - avg_act, 3),
        })
    return buckets


async def compute(pool: asyncpg.Pool, window_days: int = 14) -> CalibrationReport:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT payload_json AS payload FROM evidence_ledger
            WHERE kind IN ('decision','repair','artifact','test')
              AND created_at >= $1 LIMIT 5000
            """, since,
        )

    preds: list[tuple[float, float]] = []
    for r in rows:
        p = _parse_payload(r["payload"])
        if p is None:
            continue
        pred = _extract_prediction(p)
        if pred is not None:
            preds.append(pred)

    if not preds:
        return CalibrationReport(
            samples=0, brier_score=0.0, calibration_score=0.0, buckets=[])

    brier = statistics.mean((c - a) ** 2 for c, a in preds)
    cal = max(0.0, min(1.0, 1.0 - brier))
    buckets = _build_buckets(preds)
    return CalibrationReport(samples=len(preds), brier_score=brier,
                              calibration_score=cal, buckets=buckets)


def calibrate(raw: float, report: CalibrationReport) -> float:
    """Mappe une confidence brute via isotonic approx (monotone par bucket)."""
    if not report.buckets:
        return raw
    for b in report.buckets:
        lo, hi = [float(x) for x in b["range"].split("-")]
        if lo <= raw < hi:
            # Remplace la confidence par l'outcome moyen observe du bucket
            return max(0.0, min(1.0, float(b["avg_outcome"])))
    return raw
