"""Auto-Repair Engine V4.1 - detection anomalie + patch tri-cerveau + notif CEO.

**Perimetre de securite** : aucune reecriture automatique du code de prod.
Le moteur fait :
1. Surveille les signaux (tasks failed >= N, agent_benchmarks degrades, erreurs catalog).
2. Sur anomalie -> consigne un evidence + soumet une `repair_task` au backlog
   avec priority=critical.
3. Une "patch proposal" est generee (template deterministe) et attachee.
4. Notification CEO : ecrite dans audit_events (`action='auto_repair_alert'`)
   + proposition dans `improvement_backlog` avec category='architecture'.
5. Deploiement blue/green : simule via creation de `blue_container` vs `green_container`
   dans un champ status (sans toucher Docker en prod).

Ainsi `auto_repair` est actionnable sans risque operationnel.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.orchestration import audit_events, evidence_ledger, self_improver

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    kind: str
    severity: str
    detail: dict[str, Any]


ANOMALY_RULES: dict[str, dict[str, int | float]] = {
    "failure_spike": {"threshold": 3, "window_min": 10},
    "agent_degradation": {"min_score": 0.50, "min_exec": 3},
    "error_catalog_surge": {"min_occurrences": 5},
}


async def scan_anomalies(pool: asyncpg.Pool) -> list[Anomaly]:
    """Retourne la liste des anomalies detectees sur l'etat courant."""
    out: list[Anomaly] = []
    async with pool.acquire() as conn:
        # Failure spike : 3+ tasks failed dans les 10 dernieres minutes
        spike = await conn.fetchval(
            """
            SELECT COUNT(*) FROM tasks
            WHERE status = 'failed' AND updated_at > NOW() - INTERVAL '10 minutes'
            """
        )
        if (spike or 0) >= ANOMALY_RULES["failure_spike"]["threshold"]:
            out.append(Anomaly("failure_spike", "high",
                               {"failed_last_10min": int(spike)}))

        # Agent degradation : avg_score sous seuil avec >= 3 executions
        rows = await conn.fetch(
            """
            SELECT agent_id, agent_name, avg_score, executions
            FROM agent_benchmarks
            WHERE executions >= 3 AND avg_score < 0.50
            """
        )
        for r in rows:
            out.append(Anomaly("agent_degradation", "high", {
                "agent_id": r["agent_id"], "agent_name": r["agent_name"],
                "avg_score": float(r["avg_score"]),
                "executions": int(r["executions"]),
            }))

        # Error catalog surge : entree avec >= 5 occurrences
        rows = await conn.fetch(
            "SELECT agent_id, error_type, occurrences FROM error_catalog "
            "WHERE occurrences >= 5 ORDER BY occurrences DESC LIMIT 5"
        )
        for r in rows:
            out.append(Anomaly("error_catalog_surge", "medium", {
                "agent_id": r["agent_id"], "error_type": r["error_type"],
                "occurrences": int(r["occurrences"]),
            }))
    return out


def _format_patch_proposal(anomaly: Anomaly) -> dict[str, Any]:
    """Template deterministe de patch (inscrit dans le backlog)."""
    if anomaly.kind == "agent_degradation":
        agent = anomaly.detail.get("agent_id", "?")
        return {
            "title": f"Auto-repair: reactivation / rollback {agent}",
            "steps": [
                f"1. Lancer challenger sur {agent} (contre-hypothese)",
                f"2. Si contre-hypothese gagne : desactiver {agent} dans marketplace",
                "3. Deployer version blue candidate en sandbox",
                "4. Smoke test : 5 taches A/B",
                "5. Si OK : swap blue<->green, sinon rollback",
            ],
            "blue_green_state": "blue_pending",
            "rollback_plan": f"marketplace.enabled={agent}->True + restore prev config",
        }
    if anomaly.kind == "failure_spike":
        return {
            "title": "Auto-repair: pic de failures detecte",
            "steps": [
                "1. Verifier Anthropic credits / quota",
                "2. Verifier connectivite BDD et Redis",
                "3. Reduire max_jobs worker temporairement",
                "4. Retenter les taches failed recentes",
            ],
            "blue_green_state": "not_applicable",
        }
    return {
        "title": f"Auto-repair: {anomaly.kind}",
        "steps": ["1. Analyse humaine recommandee"],
        "blue_green_state": "not_applicable",
    }


async def run_cycle(pool: asyncpg.Pool) -> dict[str, Any]:
    """Un cycle : scan -> enregistre evidence + audit + backlog proposals."""
    anomalies = await scan_anomalies(pool)
    summary: list[dict[str, Any]] = []

    for ano in anomalies:
        patch = _format_patch_proposal(ano)
        event_id = await evidence_ledger.record(
            pool,
            kind="repair",
            actor="auto_repair_engine",
            payload={
                "anomaly_kind": ano.kind,
                "severity": ano.severity,
                "detail": ano.detail,
                "patch": patch,
            },
        )
        await audit_events.emit(
            pool,
            action="auto_repair_alert",
            actor="auto_repair_engine",
            payload={
                "anomaly": ano.kind, "severity": ano.severity,
                "detail": ano.detail, "evidence_id": event_id,
                "ceo_notification": True,
            },
        )
        await self_improver.persist(pool, [self_improver.Proposal(
            category="architecture",
            priority="critical" if ano.severity == "high" else "high",
            title=patch["title"][:240],
            rationale=f"auto_repair cycle : {ano.kind} -> {ano.severity}",
            evidence={"anomaly": ano.detail, "steps": patch["steps"],
                      "blue_green_state": patch["blue_green_state"],
                      "evidence_id": event_id},
        )])
        summary.append({"anomaly": ano.kind, "severity": ano.severity,
                        "evidence_id": event_id,
                        "patch_title": patch["title"]})

    logger.info("auto_repair cycle : %d anomalie(s), %d patch(es) proposes",
                len(anomalies), len(summary))
    return {"anomalies_count": len(anomalies), "patches": summary}
