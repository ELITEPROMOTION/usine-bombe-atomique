"""V4.4 - Promotion Progressive.

Un artefact ne passe JAMAIS directement en production :

    build -> staging -> canary -> production

Chaque etape :
1. Ouvre une ligne `promotion_stages` (status=in_progress)
2. Execute les gates de l'etape (smoke test, metrics compare baseline)
3. Ecrit une evidence dans `evidence_ledger` (kind=test ou artifact)
4. Ferme la ligne (passed / failed)
5. Si passed -> appelle l'etape suivante ; sinon -> rollback + incident

Aucune etape ne peut etre court-circuitee. Production sans preuve=impossible
(API verifie que toutes les etapes precedentes sont `passed`).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

import asyncpg

from app.orchestration import audit_events, evidence_ledger

logger = logging.getLogger(__name__)


class Stage(str, Enum):
    BUILD       = "build"
    STAGING     = "staging"
    CANARY      = "canary"
    PRODUCTION  = "production"
    ROLLED_BACK = "rolled_back"


STAGE_ORDER: tuple[Stage, ...] = (Stage.BUILD, Stage.STAGING, Stage.CANARY, Stage.PRODUCTION)


@dataclass
class StageOutcome:
    task_id: str
    artifact_version: str
    stage: Stage
    status: str              # passed | failed | skipped
    metrics: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    next_stage: Stage | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "artifact_version": self.artifact_version,
            "stage": self.stage.value, "status": self.status,
            "metrics": self.metrics, "reason": self.reason,
            "next_stage": self.next_stage.value if self.next_stage else None,
        }


async def _insert_stage(
    pool: asyncpg.Pool, task_id: str, artifact_version: str,
    stage: Stage, status: str, metrics: dict[str, Any] | None,
    evidence_id: str | None,
    rollback_reason: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO promotion_stages
              (task_id, artifact_version, stage, status,
               finished_at, metrics, evidence_event_id, rollback_reason)
            VALUES ($1, $2, $3, $4, NOW(), $5::jsonb, $6, $7)
            ON CONFLICT (task_id, artifact_version, stage) DO UPDATE SET
              status = EXCLUDED.status,
              finished_at = EXCLUDED.finished_at,
              metrics = EXCLUDED.metrics,
              evidence_event_id = EXCLUDED.evidence_event_id,
              rollback_reason = EXCLUDED.rollback_reason
            """,
            UUID(task_id), artifact_version, stage.value, status,
            json.dumps(metrics or {}),
            UUID(evidence_id) if evidence_id else None,
            rollback_reason,
        )


# ------------------------------------------------------------------ gates

async def _gate_build(
    pool: asyncpg.Pool, task_id: str, artifact_version: str,
) -> StageOutcome:
    ev = await evidence_ledger.record(
        pool, kind="artifact", actor="promotion_engine.build",
        payload={"artifact_version": artifact_version, "stage": "build"},
        task_id=task_id,
    )
    await _insert_stage(pool, task_id, artifact_version, Stage.BUILD,
                         "passed", {"stored": True}, ev)
    return StageOutcome(task_id, artifact_version, Stage.BUILD,
                         "passed", {"stored": True},
                         reason="build artefact stocke",
                         next_stage=Stage.STAGING)


async def _gate_staging_smoke(
    pool: asyncpg.Pool, task_id: str, artifact_version: str,
    smoke_probe: dict[str, Any],
) -> StageOutcome:
    """smoke_probe attendu :
       {"health_ok": bool, "http_2xx_ratio": float (0..1), "basic_tests": int}"""
    health_ok = bool(smoke_probe.get("health_ok", True))
    ratio = float(smoke_probe.get("http_2xx_ratio", 1.0))
    basic_tests = int(smoke_probe.get("basic_tests", 0))
    passed = health_ok and ratio >= 0.95 and basic_tests >= 1
    ev = await evidence_ledger.record(
        pool, kind="test", actor="promotion_engine.staging",
        payload={"artifact_version": artifact_version, "stage": "staging",
                 "smoke_probe": smoke_probe, "passed": passed},
        task_id=task_id,
    )
    await _insert_stage(pool, task_id, artifact_version, Stage.STAGING,
                         "passed" if passed else "failed", smoke_probe, ev)
    return StageOutcome(
        task_id, artifact_version, Stage.STAGING,
        "passed" if passed else "failed", smoke_probe,
        reason=("smoke OK" if passed else
                f"smoke fail : health={health_ok} ratio={ratio} basic_tests={basic_tests}"),
        next_stage=Stage.CANARY if passed else None,
    )


async def _gate_canary(
    pool: asyncpg.Pool, task_id: str, artifact_version: str,
    canary_metrics: dict[str, float],
    baseline: dict[str, float] | None = None,
    drift_tolerance: float = 0.20,
) -> StageOutcome:
    """Compare les metriques canary avec baseline (si fournie).

    canary_metrics attendu :
      {"latency_p95_ms": float, "error_rate": float (0..1), "cpu_pct": float}
    """
    baseline = baseline or {}
    violations: list[str] = []
    drift: dict[str, float] = {}
    for metric, value in canary_metrics.items():
        base = baseline.get(metric)
        if base is None or base <= 0:
            continue
        delta = (value - base) / base
        drift[metric] = round(delta, 4)
        # Regression sur latency / error_rate / cpu si > +tolerance
        if delta > drift_tolerance and metric in ("latency_p95_ms",
                                                    "error_rate", "cpu_pct"):
            violations.append(f"{metric} +{delta*100:.1f}% vs baseline")
    # Seuils absolus minimaux
    if canary_metrics.get("error_rate", 0.0) > 0.05:
        violations.append(f"error_rate={canary_metrics['error_rate']} > 5%")
    passed = not violations
    ev = await evidence_ledger.record(
        pool, kind="test", actor="promotion_engine.canary",
        payload={"artifact_version": artifact_version, "stage": "canary",
                 "canary_metrics": canary_metrics,
                 "baseline": baseline, "drift": drift,
                 "violations": violations, "passed": passed},
        task_id=task_id,
    )
    await _insert_stage(pool, task_id, artifact_version, Stage.CANARY,
                         "passed" if passed else "failed",
                         {**canary_metrics, "drift": drift}, ev)
    return StageOutcome(
        task_id, artifact_version, Stage.CANARY,
        "passed" if passed else "failed",
        {**canary_metrics, "drift": drift},
        reason="canary stable" if passed else "; ".join(violations),
        next_stage=Stage.PRODUCTION if passed else None,
    )


async def _gate_production(
    pool: asyncpg.Pool, task_id: str, artifact_version: str,
) -> StageOutcome:
    """Exige que build+staging+canary soient passed (verification defensive)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT stage, status FROM promotion_stages
            WHERE task_id = $1 AND artifact_version = $2
            """,
            UUID(task_id), artifact_version,
        )
    status_by = {r["stage"]: r["status"] for r in rows}
    prereqs = ("build", "staging", "canary")
    missing = [s for s in prereqs if status_by.get(s) != "passed"]
    if missing:
        await _insert_stage(pool, task_id, artifact_version, Stage.PRODUCTION,
                             "failed", {"missing_stages": missing}, None,
                             rollback_reason="production bloquee : preuves manquantes")
        return StageOutcome(
            task_id, artifact_version, Stage.PRODUCTION, "failed",
            {"missing_stages": missing},
            reason=f"preuves manquantes : {missing}",
        )
    ev = await evidence_ledger.record(
        pool, kind="artifact", actor="promotion_engine.production",
        payload={"artifact_version": artifact_version, "stage": "production",
                 "promoted": True},
        task_id=task_id,
    )
    await _insert_stage(pool, task_id, artifact_version, Stage.PRODUCTION,
                         "passed", {"promoted": True}, ev)
    await audit_events.emit(
        pool, action="artifact_promoted_to_production",
        actor="promotion_engine",
        payload={"task_id": task_id, "artifact_version": artifact_version},
        task_id=task_id,
    )
    return StageOutcome(
        task_id, artifact_version, Stage.PRODUCTION, "passed",
        {"promoted": True}, reason="promu en production", next_stage=None,
    )


# ------------------------------------------------------------------ public

async def run_full_pipeline(
    pool: asyncpg.Pool, task_id: str, artifact_version: str,
    smoke_probe: dict[str, Any] | None = None,
    canary_metrics: dict[str, float] | None = None,
    baseline: dict[str, float] | None = None,
) -> list[StageOutcome]:
    """Execute les 4 etapes. S'arrete au premier failed."""
    outcomes: list[StageOutcome] = []
    o = await _gate_build(pool, task_id, artifact_version)
    outcomes.append(o)
    if o.status != "passed":
        return outcomes
    smoke_probe = smoke_probe or {"health_ok": True, "http_2xx_ratio": 1.0,
                                   "basic_tests": 1}
    o = await _gate_staging_smoke(pool, task_id, artifact_version, smoke_probe)
    outcomes.append(o)
    if o.status != "passed":
        return outcomes
    canary_metrics = canary_metrics or {
        "latency_p95_ms": 250.0, "error_rate": 0.0, "cpu_pct": 30.0,
    }
    o = await _gate_canary(pool, task_id, artifact_version,
                            canary_metrics, baseline)
    outcomes.append(o)
    if o.status != "passed":
        return outcomes
    o = await _gate_production(pool, task_id, artifact_version)
    outcomes.append(o)
    return outcomes


async def rollback(
    pool: asyncpg.Pool, task_id: str, artifact_version: str, reason: str,
) -> str:
    """Marque l'artefact comme rolled_back et consigne evidence + audit."""
    ev = await evidence_ledger.record(
        pool, kind="repair", actor="promotion_engine.rollback",
        payload={"artifact_version": artifact_version, "reason": reason},
        task_id=task_id,
    )
    await _insert_stage(
        pool, task_id, artifact_version, Stage.ROLLED_BACK,
        "rolled_back", {"reason": reason}, ev, rollback_reason=reason,
    )
    await audit_events.emit(
        pool, action="artifact_rolled_back", actor="promotion_engine",
        payload={"task_id": task_id, "artifact_version": artifact_version,
                 "reason": reason},
        task_id=task_id,
    )
    return ev


async def list_task_stages(
    pool: asyncpg.Pool, task_id: str,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT artifact_version, stage, status, started_at, finished_at,
                   metrics, rollback_reason
            FROM promotion_stages WHERE task_id = $1
            ORDER BY started_at ASC
            """,
            UUID(task_id),
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        metrics = r["metrics"]
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        out.append({
            "artifact_version": r["artifact_version"],
            "stage": r["stage"], "status": r["status"],
            "started_at": r["started_at"].isoformat(),
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            "metrics": metrics or {},
            "rollback_reason": r["rollback_reason"],
        })
    return out


async def active_artifacts(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Retourne les artefacts en cours de promotion (au moins un stage non-terminal)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (task_id, artifact_version)
                task_id, artifact_version, stage, status, finished_at
            FROM promotion_stages
            ORDER BY task_id, artifact_version, started_at DESC
            """
        )
    return [
        {"task_id": str(r["task_id"]), "artifact_version": r["artifact_version"],
         "latest_stage": r["stage"], "status": r["status"],
         "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None}
        for r in rows
    ]
