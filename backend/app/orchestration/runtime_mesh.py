"""V4.4 - Runtime Observability Mesh.

Surveillance continue des services deployes :

- `probe_target(url)` : health + latence + error_rate + cpu/mem (quand dispo)
- `record_metric()` : persiste dans `runtime_metrics` avec drift vs baseline
- `capture_baseline()` : cliche N mesures, stocke la mediane dans `runtime_baselines`
- `detect_drift()` : retourne les metriques hors enveloppe (drift > tolerance)
- `alert_if_drift()` : cree un incident_log + declenche auto_repair si critique

Pas d'agent APM externe : on scrappe des endpoints HTTP et on calcule les
statistiques localement. Dashboard temps reel expose via `/analytics/runtime/*`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from app.orchestration import audit_events, evidence_ledger

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.25  # 25% de deviation vs baseline


@dataclass
class Probe:
    target: str
    url: str
    status_code: int = 0
    latency_ms: float = 0.0
    error: str = ""

    @property
    def health_ok(self) -> bool:
        return 200 <= self.status_code < 400


@dataclass
class DriftAlert:
    target: str
    metric: str
    value: float
    baseline: float
    drift_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target, "metric": self.metric,
            "value": round(self.value, 4),
            "baseline": round(self.baseline, 4),
            "drift_pct": round(self.drift_pct * 100, 2),
        }


async def probe_http(target: str, url: str, timeout: float = 5.0) -> Probe:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url)
            latency = (time.perf_counter() - t0) * 1000
            return Probe(target=target, url=url,
                          status_code=r.status_code, latency_ms=latency)
    except Exception as exc:
        return Probe(target=target, url=url, error=str(exc))


async def record_metric(
    pool: asyncpg.Pool, target: str, metric: str, value: float,
    baseline: float | None = None,
    task_id: str | None = None, artifact_version: str | None = None,
) -> None:
    drift = None
    if baseline is not None and baseline > 0:
        drift = (value - baseline) / baseline
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO runtime_metrics
              (task_id, artifact_version, target, metric, value, baseline, drift_pct)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            UUID(task_id) if task_id else None,
            artifact_version[:64] if artifact_version else None,
            target[:120], metric[:40], value, baseline,
            round(drift, 4) if drift is not None else None,
        )


async def capture_baseline(
    pool: asyncpg.Pool, target: str, url: str, samples: int = 5,
    interval_s: float = 1.0,
) -> dict[str, float]:
    """Baseline rapide : N probes successifs, mediane par metrique."""
    probes: list[Probe] = []
    for _ in range(samples):
        probes.append(await probe_http(target, url))
        await asyncio.sleep(interval_s)
    good = [p for p in probes if p.health_ok]
    n = max(1, len(probes))
    baselines = {
        "latency_p95_ms": _percentile([p.latency_ms for p in probes], 0.95),
        "error_rate": (n - len(good)) / n,
        "health": 1.0 if good else 0.0,
    }
    async with pool.acquire() as conn:
        for metric, value in baselines.items():
            await conn.execute(
                """
                INSERT INTO runtime_baselines (target, metric, value, captured_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (target, metric) DO UPDATE SET
                  value = EXCLUDED.value, captured_at = NOW()
                """,
                target[:120], metric, value,
            )
    logger.info("baseline captured target=%s %s", target, baselines)
    return baselines


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    clean = sorted(v for v in values if v > 0)
    if not clean:
        return 0.0
    idx = min(len(clean) - 1, max(0, int(round(p * (len(clean) - 1)))))
    return float(clean[idx])


async def get_baseline(pool: asyncpg.Pool, target: str) -> dict[str, float]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT metric, value FROM runtime_baselines WHERE target = $1",
            target[:120],
        )
    return {r["metric"]: float(r["value"]) for r in rows}


async def detect_drift(
    pool: asyncpg.Pool, target: str, current: dict[str, float],
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[DriftAlert]:
    baseline = await get_baseline(pool, target)
    alerts: list[DriftAlert] = []
    for metric, value in current.items():
        base = baseline.get(metric)
        if base is None or base <= 0:
            continue
        drift = (value - base) / base
        if metric in ("latency_p95_ms", "error_rate") and drift > tolerance:
            alerts.append(DriftAlert(target, metric, value, base, drift))
        if metric == "health" and value < base:
            alerts.append(DriftAlert(target, metric, value, base, drift))
    return alerts


async def alert_if_drift(
    pool: asyncpg.Pool, alerts: list[DriftAlert],
    task_id: str | None = None,
) -> list[str]:
    """Cree un incident_log par alert + ecrit evidence + audit."""
    ids: list[str] = []
    for a in alerts:
        severity = "critical" if a.metric == "health" else "high"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO incident_log
                  (task_id, incident_kind, severity, title, details)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                RETURNING id
                """,
                UUID(task_id) if task_id else None,
                "runtime_drift", severity,
                f"Drift {a.metric} sur {a.target} : +{a.drift_pct*100:.1f}%",
                json.dumps(a.to_dict()),
            )
            ids.append(str(row["id"]))
        await evidence_ledger.record(
            pool, kind="test", actor="runtime_mesh.drift",
            payload=a.to_dict(), task_id=task_id,
        )
        await audit_events.emit(
            pool, action="runtime_drift_detected", actor="runtime_mesh",
            payload=a.to_dict(), task_id=task_id,
        )
    return ids


async def observe_once(
    pool: asyncpg.Pool, targets: dict[str, str],
    task_id: str | None = None, artifact_version: str | None = None,
) -> dict[str, Any]:
    """Un cycle de probes : mesure chaque target, persiste, detecte drift."""
    results: dict[str, Any] = {}
    all_alerts: list[DriftAlert] = []
    for name, url in targets.items():
        probe = await probe_http(name, url)
        metrics = {
            "latency_p95_ms": probe.latency_ms,  # 1 probe -> approx p95
            "error_rate": 0.0 if probe.health_ok else 1.0,
            "health": 1.0 if probe.health_ok else 0.0,
        }
        baseline = await get_baseline(pool, name)
        for metric, value in metrics.items():
            await record_metric(
                pool, name, metric, value,
                baseline=baseline.get(metric),
                task_id=task_id, artifact_version=artifact_version,
            )
        alerts = await detect_drift(pool, name, metrics)
        all_alerts.extend(alerts)
        results[name] = {
            "probe": {"status_code": probe.status_code,
                      "latency_ms": round(probe.latency_ms, 2),
                      "error": probe.error},
            "metrics": metrics,
            "drift_alerts": [a.to_dict() for a in alerts],
        }
    if all_alerts:
        await alert_if_drift(pool, all_alerts, task_id=task_id)
    return {"targets": results,
            "alerts_count": len(all_alerts),
            "summary": "drift" if all_alerts else "stable"}


async def latest_metrics(
    pool: asyncpg.Pool, target: str | None = None, limit: int = 100,
) -> list[dict[str, Any]]:
    if target:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT target, metric, value, baseline, drift_pct, observed_at
                FROM runtime_metrics WHERE target = $1
                ORDER BY observed_at DESC LIMIT $2
                """, target[:120], limit,
            )
    else:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT target, metric, value, baseline, drift_pct, observed_at
                FROM runtime_metrics
                ORDER BY observed_at DESC LIMIT $1
                """, limit,
            )
    return [
        {"target": r["target"], "metric": r["metric"],
         "value": float(r["value"]), "baseline": float(r["baseline"] or 0),
         "drift_pct": float(r["drift_pct"] or 0),
         "observed_at": r["observed_at"].isoformat()}
        for r in rows
    ]


async def incidents(
    pool: asyncpg.Pool, acknowledged: bool | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    sql = ("SELECT id, task_id, incident_kind, severity, title, details, "
           "human_acknowledged, created_at FROM incident_log")
    args: list[Any] = []
    if acknowledged is not None:
        sql += " WHERE human_acknowledged = $1"
        args.append(acknowledged)
    sql += f" ORDER BY created_at DESC LIMIT {int(limit)}"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    out = []
    for r in rows:
        details = r["details"]
        if isinstance(details, str):
            details = json.loads(details)
        out.append({
            "id": str(r["id"]),
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "kind": r["incident_kind"], "severity": r["severity"],
            "title": r["title"], "details": details,
            "acknowledged": r["human_acknowledged"],
            "created_at": r["created_at"].isoformat(),
        })
    return out


async def acknowledge(pool: asyncpg.Pool, incident_id: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE incident_log SET human_acknowledged = TRUE WHERE id = $1 "
            "RETURNING id",
            UUID(incident_id),
        )
    return row is not None
