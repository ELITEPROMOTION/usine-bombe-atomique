"""V5.1 BLOC 13 - Autonomy Auditor.

Calcule 15+ KPIs d'autonomie sur fenetre glissante :
  - autonomy_action_rate = actions_prises_sans_humain / actions_totales
  - autonomy_weighted_by_criticity = idem, pondere par criticite
  - avoidable_escalation_rate = interventions_jugees_non_necessaires / total
  - escalation_precision = interventions_necessaires / interventions_totales
  - questions_per_escalation : moyenne des questions par intervention C
  - ahmed_cognitive_load_minutes_per_project
  - autonomous_continuation_rate_after_block : % de tasks qui ont continue
  - confidence_calibration_score : 1 - Brier score
  - patch_success_by_type : LOCAL_FIX/CONTRACT_FIX/SECURITY_FIX/...
  - c_sub_type_distribution : C1..C6
  - chaos_pass_rate + MTSH_seconds
  - artifact_freshness_median_minutes + stale_data_incidents
  - active_leases + lease_cap_violations
  - human_load_budget_used_pct
"""
from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Pondération par criticité pour autonomy_weighted_by_criticity
CRITICITY_WEIGHT = {"low": 0.5, "medium": 1.0, "high": 2.0, "critical": 4.0}

# Budget hebdomadaire Ahmed (en interruptions) - AJUSTABLE
HUMAN_LOAD_BUDGET_WEEKLY = 20  # 20 interventions/semaine = cible


@dataclass
class AutonomyKPIs:
    window_hours: int = 168
    autonomy_action_rate: float = 0.0
    autonomy_weighted_by_criticity: float = 0.0
    avoidable_escalation_rate: float = 0.0
    escalation_precision: float = 0.0
    questions_per_escalation: float = 0.0
    ahmed_cognitive_load_minutes_per_project: float = 0.0
    ahmed_interruptions_per_project: float = 0.0
    autonomous_continuation_rate_after_block: float = 0.0
    confidence_calibration_score: float = 0.0
    patch_success_by_type: dict[str, float] = field(default_factory=dict)
    c_sub_type_distribution: dict[str, int] = field(default_factory=dict)
    chaos_pass_rate: float = 0.0
    mean_time_to_self_heal_seconds: int = 0
    artifact_freshness_median_minutes: int = 0
    stale_data_incidents: int = 0
    active_leases: int = 0
    lease_cap_violations: int = 0
    human_load_budget_used_pct: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_hours": self.window_hours,
            "autonomy_action_rate": round(self.autonomy_action_rate, 4),
            "autonomy_weighted_by_criticity": round(self.autonomy_weighted_by_criticity, 4),
            "avoidable_escalation_rate": round(self.avoidable_escalation_rate, 4),
            "escalation_precision": round(self.escalation_precision, 4),
            "questions_per_escalation": round(self.questions_per_escalation, 3),
            "ahmed_cognitive_load_minutes_per_project": round(
                self.ahmed_cognitive_load_minutes_per_project, 2),
            "ahmed_interruptions_per_project": round(
                self.ahmed_interruptions_per_project, 2),
            "autonomous_continuation_rate_after_block": round(
                self.autonomous_continuation_rate_after_block, 4),
            "confidence_calibration_score": round(
                self.confidence_calibration_score, 4),
            "patch_success_by_type": self.patch_success_by_type,
            "c_sub_type_distribution": self.c_sub_type_distribution,
            "chaos_pass_rate": round(self.chaos_pass_rate, 4),
            "mean_time_to_self_heal_seconds": self.mean_time_to_self_heal_seconds,
            "artifact_freshness_median_minutes": self.artifact_freshness_median_minutes,
            "stale_data_incidents": self.stale_data_incidents,
            "active_leases": self.active_leases,
            "lease_cap_violations": self.lease_cap_violations,
            "human_load_budget_used_pct": round(self.human_load_budget_used_pct, 4),
            "details": self.details,
        }


async def _load_raw(
    pool: asyncpg.Pool, since: datetime,
) -> dict[str, Any]:
    """Recupere toutes les donnees brutes en 1 connexion."""
    async with pool.acquire() as conn:
        interventions = await conn.fetch(
            "SELECT form_type, criticality, created_at, status "
            "FROM pending_user_inputs WHERE created_at >= $1", since)
        total_events_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM audit_events WHERE created_at >= $1",
            since)
        outcomes = await conn.fetch(
            "SELECT was_necessary, form_type, c_sub_type, ahmed_response_ms, "
            "       autonomy_alternative "
            "FROM intervention_outcomes WHERE created_at >= $1", since)
        patch_rows = await conn.fetch(
            "SELECT payload_json AS payload FROM evidence_ledger "
            "WHERE kind = 'repair' AND created_at >= $1 LIMIT 1000", since)
        chaos_rows = await conn.fetch(
            "SELECT passed, duration_seconds, self_healed "
            "FROM autonomy_chaos_runs WHERE created_at >= $1", since)
        active_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM permission_leases "
            "WHERE revoked_at IS NULL AND expires_at > NOW()")
        violations_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM permission_leases "
            "WHERE usage_count > usage_cap")
        stale_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM incident_log "
            "WHERE incident_kind = 'stale_data' AND created_at >= $1", since)
        tasks_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM tasks WHERE created_at >= $1", since)
    return {
        "interventions": interventions,
        "total_events": int(total_events_row["n"] or 0) if total_events_row else 0,
        "outcomes": outcomes, "patch_rows": patch_rows, "chaos_rows": chaos_rows,
        "active_leases": int(active_row["n"] or 0) if active_row else 0,
        "lease_violations": int(violations_row["n"] or 0) if violations_row else 0,
        "stale": int(stale_row["n"] or 0) if stale_row else 0,
        "projects": max(1, int(tasks_row["n"] or 0) if tasks_row else 1),
    }


def _action_rates(
    total_events: int, interventions: list[asyncpg.Record],
) -> tuple[float, float]:
    total_intervs = len(interventions)
    action_rate = (max(0.0, min(1.0, 1.0 - total_intervs / total_events))
                    if total_events > 0 else 0.0)
    intervs_w = sum(CRITICITY_WEIGHT.get(r["criticality"] or "medium", 1.0)
                     for r in interventions)
    weighted = max(0.0, min(1.0, 1.0 - intervs_w / (total_events or 1)))
    return action_rate, weighted


def _outcomes_stats(
    outcomes: list[asyncpg.Record], projects: int,
) -> dict[str, float]:
    if not outcomes:
        return {"precision": 0.0, "avoidable": 0.0, "ahmed_min": 0.0,
                "continuation": 0.0}
    necessary = [o for o in outcomes if o["was_necessary"] is True]
    unnecessary = [o for o in outcomes if o["was_necessary"] is False]
    resp_ms = [o["ahmed_response_ms"] for o in outcomes if o["ahmed_response_ms"]]
    ahmed_min = 0.0
    if resp_ms:
        avg_min = statistics.mean(resp_ms) / 1000 / 60
        ahmed_min = avg_min * len(outcomes) / projects
    with_alt = sum(1 for o in outcomes if o.get("autonomy_alternative"))
    return {
        "precision": len(necessary) / len(outcomes),
        "avoidable": len(unnecessary) / len(outcomes),
        "ahmed_min": ahmed_min,
        "continuation": with_alt / len(outcomes),
    }


def _patch_stats(
    patch_rows: list[asyncpg.Record],
) -> tuple[dict[str, float], int]:
    wins: dict[str, int] = {}
    tots: dict[str, int] = {}
    for r in patch_rows:
        p = r["payload"]
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except json.JSONDecodeError:
                continue
        ptype = (p or {}).get("patch_type", "UNKNOWN")
        tots[ptype] = tots.get(ptype, 0) + 1
        if (p or {}).get("success"):
            wins[ptype] = wins.get(ptype, 0) + 1
    return ({k: round(wins.get(k, 0) / v, 4) for k, v in tots.items()},
            sum(tots.values()))


def _chaos_stats(chaos_rows: list[asyncpg.Record]) -> tuple[float, int]:
    if not chaos_rows:
        return 0.0, 0
    passed = sum(1 for c in chaos_rows if c["passed"])
    healed = [c["duration_seconds"] for c in chaos_rows if c["self_healed"]]
    mtsh = int(statistics.mean(healed)) if healed else 0
    return passed / len(chaos_rows), mtsh


def _c_distribution(outcomes: list[asyncpg.Record]) -> dict[str, int]:
    c: dict[str, int] = {}
    for o in outcomes:
        sub = o["c_sub_type"]
        if sub:
            c[sub] = c.get(sub, 0) + 1
    return c


async def compute(
    pool: asyncpg.Pool, window_hours: int = 168,
) -> AutonomyKPIs:
    """Calcule les KPIs sur une fenetre glissante (7j par defaut)."""
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    raw = await _load_raw(pool, since)
    kpis = AutonomyKPIs(window_hours=window_hours)

    action_rate, weighted = _action_rates(raw["total_events"], raw["interventions"])
    kpis.autonomy_action_rate = action_rate
    kpis.autonomy_weighted_by_criticity = weighted

    stats = _outcomes_stats(raw["outcomes"], raw["projects"])
    kpis.escalation_precision = stats["precision"]
    kpis.avoidable_escalation_rate = stats["avoidable"]
    kpis.ahmed_cognitive_load_minutes_per_project = stats["ahmed_min"]
    kpis.autonomous_continuation_rate_after_block = stats["continuation"]
    kpis.ahmed_interruptions_per_project = len(raw["interventions"]) / raw["projects"]

    kpis.c_sub_type_distribution = _c_distribution(raw["outcomes"])
    kpis.patch_success_by_type, total_patches = _patch_stats(raw["patch_rows"])
    kpis.chaos_pass_rate, kpis.mean_time_to_self_heal_seconds = _chaos_stats(
        raw["chaos_rows"])

    kpis.active_leases = raw["active_leases"]
    kpis.lease_cap_violations = raw["lease_violations"]
    kpis.stale_data_incidents = raw["stale"]

    week_fraction = window_hours / 168
    budget = HUMAN_LOAD_BUDGET_WEEKLY * week_fraction
    kpis.human_load_budget_used_pct = min(
        1.0, len(raw["interventions"]) / max(1.0, budget))

    kpis.details = {
        "total_events": raw["total_events"],
        "total_interventions": len(raw["interventions"]),
        "total_outcomes": len(raw["outcomes"]),
        "total_projects": raw["projects"],
        "total_patches": total_patches,
        "total_chaos_runs": len(raw["chaos_rows"]),
    }
    return kpis


async def persist(pool: asyncpg.Pool, kpis: AutonomyKPIs) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO autonomy_metrics(
                window_hours, autonomy_action_rate, autonomy_weighted_by_criticity,
                avoidable_escalation_rate, escalation_precision,
                questions_per_escalation,
                ahmed_cognitive_load_minutes_per_project,
                ahmed_interruptions_per_project,
                autonomous_continuation_rate_after_block,
                confidence_calibration_score,
                patch_success_by_type, c_sub_type_distribution,
                chaos_pass_rate, mean_time_to_self_heal_seconds,
                artifact_freshness_median_minutes, stale_data_incidents,
                active_leases, lease_cap_violations, human_load_budget_used_pct,
                details
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12::jsonb,
                    $13,$14,$15,$16,$17,$18,$19,$20::jsonb)
            RETURNING id
            """,
            kpis.window_hours,
            kpis.autonomy_action_rate, kpis.autonomy_weighted_by_criticity,
            kpis.avoidable_escalation_rate, kpis.escalation_precision,
            kpis.questions_per_escalation,
            kpis.ahmed_cognitive_load_minutes_per_project,
            kpis.ahmed_interruptions_per_project,
            kpis.autonomous_continuation_rate_after_block,
            kpis.confidence_calibration_score,
            json.dumps(kpis.patch_success_by_type),
            json.dumps(kpis.c_sub_type_distribution),
            kpis.chaos_pass_rate, kpis.mean_time_to_self_heal_seconds,
            kpis.artifact_freshness_median_minutes, kpis.stale_data_incidents,
            kpis.active_leases, kpis.lease_cap_violations,
            kpis.human_load_budget_used_pct,
            json.dumps(kpis.details),
        )
    return int(row["id"])


async def latest(pool: asyncpg.Pool) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM autonomy_metrics ORDER BY captured_at DESC LIMIT 1",
        )
    if row is None:
        return None
    d: dict[str, Any] = {}
    for k, v in dict(row).items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, str) and k in ("patch_success_by_type",
                                            "c_sub_type_distribution", "details"):
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                d[k] = v
        else:
            d[k] = v
    return d
