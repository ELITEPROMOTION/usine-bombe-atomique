"""V5.2 BLOC 7 - Drift Detector.

Surveille les decisions prises et detecte 4 types de derives :
  STATISTICAL  : distribution des choix change anormalement
  INVARIANT    : frequence de violations anormales
  PERFORMANCE  : latence / cout evolue defavorablement
  QUALITY      : confidence_score moyen baisse / rework augmente

Actions auto :
  - warning        -> log + /ahmed_inbox
  - warning_strong -> pause auto-tuning sur metrique concernee
  - critical       -> rollback parametres + escalade C
"""
from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# Seuils derive (deviation vs baseline, %)
WARNING_THRESHOLD = 0.15        # +15% deviation
WARNING_STRONG_THRESHOLD = 0.30
CRITICAL_THRESHOLD = 0.50


@dataclass
class DriftAlert:
    kind: str                      # statistical|invariant|performance|quality
    severity: str                  # warning|warning_strong|critical
    metric: str
    baseline: float
    current: float
    deviation_pct: float
    auto_action: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "severity": self.severity,
            "metric": self.metric, "baseline": self.baseline,
            "current": self.current,
            "deviation_pct": round(self.deviation_pct, 4),
            "auto_action": self.auto_action, "details": self.details,
        }


def _severity(deviation: float) -> str | None:
    a = abs(deviation)
    if a >= CRITICAL_THRESHOLD:
        return "critical"
    if a >= WARNING_STRONG_THRESHOLD:
        return "warning_strong"
    if a >= WARNING_THRESHOLD:
        return "warning"
    return None


def _auto_action(severity: str) -> str:
    return {
        "warning": "notify_ahmed_inbox",
        "warning_strong": "pause_tuning",
        "critical": "rollback_params_and_escalate",
    }[severity]


# ============================================================ STATISTICAL

async def detect_statistical(
    pool: asyncpg.Pool, window_days: int = 7, baseline_days: int = 30,
) -> list[DriftAlert]:
    """Compare la distribution des chosen_value sur window_days vs baseline_days."""
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        cur_rows = await conn.fetch(
            """
            SELECT chosen_value FROM decisions_audit
            WHERE created_at >= $1 AND category = 'REASONABLE'
            """, now - timedelta(days=window_days),
        )
        base_rows = await conn.fetch(
            """
            SELECT chosen_value FROM decisions_audit
            WHERE created_at >= $1 AND created_at < $2
              AND category = 'REASONABLE'
            """,
            now - timedelta(days=baseline_days),
            now - timedelta(days=window_days),
        )

    def _dist(rows: list[asyncpg.Record]) -> dict[str, float]:
        vals: list[str] = []
        from app.governance._json_utils import parse_jsonb
        for r in rows:
            v = parse_jsonb(r["chosen_value"])
            vals.append(str(v))
        tot = len(vals) or 1
        d: dict[str, float] = {}
        for v in vals:
            d[v] = d.get(v, 0) + 1
        return {k: c / tot for k, c in d.items()}

    cur_dist = _dist(cur_rows)
    base_dist = _dist(base_rows)
    alerts: list[DriftAlert] = []
    for val, freq in cur_dist.items():
        base_freq = base_dist.get(val, 0.0)
        if base_freq < 0.02:
            continue  # valeur marginale
        deviation = (freq - base_freq) / max(0.01, base_freq)
        sev = _severity(deviation)
        if sev is None:
            continue
        alerts.append(DriftAlert(
            kind="statistical", severity=sev,
            metric=f"chosen_value:{val[:60]}",
            baseline=base_freq, current=freq,
            deviation_pct=deviation,
            auto_action=_auto_action(sev),
            details={"cur_samples": len(cur_rows),
                      "base_samples": len(base_rows)},
        ))
    return alerts


# ============================================================ QUALITY

async def detect_quality(
    pool: asyncpg.Pool, window_days: int = 7, baseline_days: int = 30,
) -> list[DriftAlert]:
    """Confidence moyenne en decisions vs historique."""
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        cur = await conn.fetchval(
            "SELECT AVG(confidence_score) FROM decisions_audit "
            "WHERE created_at >= $1",
            now - timedelta(days=window_days),
        )
        base = await conn.fetchval(
            """
            SELECT AVG(confidence_score) FROM decisions_audit
            WHERE created_at >= $1 AND created_at < $2
            """,
            now - timedelta(days=baseline_days),
            now - timedelta(days=window_days),
        )
    if cur is None or base is None or float(base) == 0:
        return []
    cur_f, base_f = float(cur), float(base)
    deviation = (cur_f - base_f) / max(0.01, base_f)
    sev = _severity(deviation)
    if sev is None or deviation > 0:  # on alerte seulement sur baisse
        return []
    return [DriftAlert(
        kind="quality", severity=sev,
        metric="avg_confidence_score",
        baseline=base_f, current=cur_f,
        deviation_pct=deviation,
        auto_action=_auto_action(sev),
        details={},
    )]


# ============================================================ INVARIANT

async def detect_invariant(
    pool: asyncpg.Pool, window_days: int = 7,
) -> list[DriftAlert]:
    """Compte les decisions avec bounds_respected = false."""
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM decisions_audit WHERE created_at >= $1",
            now - timedelta(days=window_days),
        )
        viol = await conn.fetchval(
            "SELECT COUNT(*) FROM decisions_audit "
            "WHERE created_at >= $1 AND bounds_respected = FALSE",
            now - timedelta(days=window_days),
        )
    total, viol = int(total or 0), int(viol or 0)
    if total == 0:
        return []
    rate = viol / total
    if rate < 0.01:
        return []
    # violation rate 1-3% warning, 3-10% strong, >10% critical
    if rate >= 0.10:
        sev = "critical"
    elif rate >= 0.03:
        sev = "warning_strong"
    else:
        sev = "warning"
    return [DriftAlert(
        kind="invariant", severity=sev,
        metric="bounds_violation_rate",
        baseline=0.0, current=rate,
        deviation_pct=rate,
        auto_action=_auto_action(sev),
        details={"violations": viol, "total": total},
    )]


# ============================================================ PERFORMANCE

async def detect_performance(
    pool: asyncpg.Pool, window_days: int = 7, baseline_days: int = 30,
) -> list[DriftAlert]:
    """Mediane duree_ms tasks (proxy performance)."""
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        cur_rows = await conn.fetch(
            """
            SELECT EXTRACT(EPOCH FROM updated_at - created_at) * 1000 AS ms
            FROM tasks WHERE created_at >= $1 AND status = 'completed'
            """, now - timedelta(days=window_days),
        )
        base_rows = await conn.fetch(
            """
            SELECT EXTRACT(EPOCH FROM updated_at - created_at) * 1000 AS ms
            FROM tasks WHERE created_at >= $1 AND created_at < $2
              AND status = 'completed'
            """,
            now - timedelta(days=baseline_days),
            now - timedelta(days=window_days),
        )
    cur = [float(r["ms"]) for r in cur_rows if r["ms"] is not None]
    base = [float(r["ms"]) for r in base_rows if r["ms"] is not None]
    if len(cur) < 3 or len(base) < 3:
        return []
    cur_med, base_med = statistics.median(cur), statistics.median(base)
    if base_med <= 0:
        return []
    deviation = (cur_med - base_med) / base_med
    sev = _severity(deviation)
    if sev is None or deviation < 0:
        return []
    return [DriftAlert(
        kind="performance", severity=sev,
        metric="median_task_duration_ms",
        baseline=base_med, current=cur_med,
        deviation_pct=deviation,
        auto_action=_auto_action(sev),
        details={"cur_n": len(cur), "base_n": len(base)},
    )]


# ============================================================ public

async def scan_all(
    pool: asyncpg.Pool, window_days: int = 7, baseline_days: int = 30,
) -> list[DriftAlert]:
    alerts: list[DriftAlert] = []
    alerts.extend(await detect_statistical(pool, window_days, baseline_days))
    alerts.extend(await detect_quality(pool, window_days, baseline_days))
    alerts.extend(await detect_invariant(pool, window_days))
    alerts.extend(await detect_performance(pool, window_days, baseline_days))
    for a in alerts:
        await _persist(pool, a)
    return alerts


async def _persist(pool: asyncpg.Pool, a: DriftAlert) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO drift_alerts
              (drift_kind, severity, metric, baseline_value, current_value,
               deviation_pct, auto_action, details)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            a.kind[:40], a.severity[:20], a.metric[:120],
            a.baseline, a.current, a.deviation_pct,
            a.auto_action[:80], json.dumps(a.details),
        )


async def recent(
    pool: asyncpg.Pool, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT drift_kind, severity, metric, baseline_value, "
            "current_value, deviation_pct, auto_action, acknowledged, "
            "detected_at FROM drift_alerts "
            "ORDER BY detected_at DESC LIMIT $1", limit,
        )
    return [{
        "kind": r["drift_kind"], "severity": r["severity"],
        "metric": r["metric"],
        "baseline": float(r["baseline_value"] or 0),
        "current": float(r["current_value"] or 0),
        "deviation_pct": float(r["deviation_pct"] or 0),
        "auto_action": r["auto_action"],
        "acknowledged": r["acknowledged"],
        "detected_at": r["detected_at"].isoformat(),
    } for r in rows]
