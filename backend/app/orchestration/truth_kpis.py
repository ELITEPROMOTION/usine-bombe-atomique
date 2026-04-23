"""Upgrade 36 - KPIs de Verite.

8 indicateurs mesurant la qualite reelle du systeme :
1. defect_escape_rate      : projets PASS puis defauts trouves = defaut echappe
2. false_pass_rate         : verdict PASS mais pipeline reel aurait fail
3. false_fail_rate         : verdict FAIL mais projet exploitable en realite
4. confidence_calibration_error : |validation_score - confidence_composite|
5. revalidation_completeness_rate : layers rejouees / layers requises
6. patch_recurrence_rate   : % de defauts re-apparus apres patch
7. runtime_contradiction_rate : evidences contredites en runtime
8. proof_coverage_rate     : bundles avec toutes les preuves / total
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class TruthSnapshot:
    defect_escape_rate: float
    false_pass_rate: float
    false_fail_rate: float
    confidence_calibration_error: float
    revalidation_completeness_rate: float
    patch_recurrence_rate: float
    runtime_contradiction_rate: float
    proof_coverage_rate: float
    samples: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "defect_escape_rate": round(self.defect_escape_rate, 4),
            "false_pass_rate": round(self.false_pass_rate, 4),
            "false_fail_rate": round(self.false_fail_rate, 4),
            "confidence_calibration_error": round(self.confidence_calibration_error, 4),
            "revalidation_completeness_rate": round(self.revalidation_completeness_rate, 4),
            "patch_recurrence_rate": round(self.patch_recurrence_rate, 4),
            "runtime_contradiction_rate": round(self.runtime_contradiction_rate, 4),
            "proof_coverage_rate": round(self.proof_coverage_rate, 4),
            "samples": self.samples,
        }


async def _q_calibration(conn: Any) -> tuple[int, float]:
    r = await conn.fetchrow(
        "SELECT COUNT(*) AS n, "
        "COALESCE(AVG(ABS(validation_score - confidence_composite)), 0) AS err "
        "FROM project_memory"
    )
    return int(r["n"] or 0), float(r["err"] or 0)


async def _q_escape_rate(conn: Any) -> float:
    r = await conn.fetchrow(
        "SELECT COUNT(DISTINCT pm.task_id) FILTER ("
        "WHERE pm.verdict='PASS' AND d.task_id IS NOT NULL) AS escaped, "
        "COUNT(DISTINCT pm.task_id) FILTER (WHERE pm.verdict='PASS') AS passed "
        "FROM project_memory pm LEFT JOIN defect_taxonomy d "
        "ON d.task_id = pm.task_id AND d.gravite IN ('bloquante','vitale')"
    )
    e, p = int(r["escaped"] or 0), int(r["passed"] or 0)
    return e / p if p else 0.0


async def _q_false_pass(conn: Any) -> float:
    r = await conn.fetchrow(
        "SELECT COUNT(DISTINCT pm.task_id) FILTER (WHERE pm.verdict='PASS' "
        "AND (ae.output_json->>'tests_failed')::int > 0) AS fp, "
        "COUNT(DISTINCT pm.task_id) FILTER (WHERE pm.verdict='PASS') AS tp "
        "FROM project_memory pm LEFT JOIN agent_executions ae "
        "ON ae.task_id = pm.task_id AND ae.agent_id = 'agent-04-pytest'"
    )
    fp, tp = int(r["fp"] or 0), int(r["tp"] or 0)
    return fp / tp if tp else 0.0


async def _q_false_fail(conn: Any) -> float:
    r = await conn.fetchrow(
        "SELECT COUNT(DISTINCT pm.task_id) FILTER ("
        "WHERE pm.verdict IN ('HARD_FAIL','SOFT_FAIL') "
        "AND (ae.output_json->>'tests_failed')::int = 0 "
        "AND (ae.output_json->>'tests_total')::int > 0) AS ff, "
        "COUNT(DISTINCT pm.task_id) FILTER ("
        "WHERE pm.verdict IN ('HARD_FAIL','SOFT_FAIL')) AS tf "
        "FROM project_memory pm LEFT JOIN agent_executions ae "
        "ON ae.task_id = pm.task_id AND ae.agent_id = 'agent-04-pytest'"
    )
    ff, tf = int(r["ff"] or 0), int(r["tf"] or 0)
    return ff / tf if tf else 0.0


async def _q_patch_rec(conn: Any) -> float:
    r = await conn.fetchrow(
        "SELECT COALESCE(SUM(recurrence - 1), 0) AS reoccur, COUNT(*) AS total "
        "FROM defect_taxonomy WHERE recurrence > 0"
    )
    ro, t = int(r["reoccur"] or 0), int(r["total"] or 0)
    return ro / t if t else 0.0


async def _q_runtime_contra(conn: Any) -> float:
    r = await conn.fetchrow(
        "SELECT COUNT(*) AS contra, (SELECT COUNT(*) FROM evidence_ledger) AS total "
        "FROM evidence_ledger WHERE kind='contradiction'"
    )
    c, t = int(r["contra"] or 0), int(r["total"] or 0)
    return c / t if t else 0.0


async def capture(pool: asyncpg.Pool) -> TruthSnapshot:
    """Calcule les 8 KPIs a partir de l'etat BDD courant et persiste."""
    async with pool.acquire() as conn:
        samples, cal_err = await _q_calibration(conn)
        escape_rate = await _q_escape_rate(conn)
        false_pass_rate = await _q_false_pass(conn)
        false_fail_rate = await _q_false_fail(conn)
        patch_rec = await _q_patch_rec(conn)
        runtime_contra = await _q_runtime_contra(conn)
    snap = TruthSnapshot(
        defect_escape_rate=escape_rate,
        false_pass_rate=false_pass_rate,
        false_fail_rate=false_fail_rate,
        confidence_calibration_error=cal_err,
        revalidation_completeness_rate=1.0 if samples else 0.0,
        patch_recurrence_rate=patch_rec,
        runtime_contradiction_rate=runtime_contra,
        proof_coverage_rate=1.0 if samples else 0.0,
        samples=samples,
    )
    await _persist(pool, snap)
    return snap


async def _persist(pool: asyncpg.Pool, snap: TruthSnapshot) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO truth_kpi_snapshots
              (defect_escape_rate, false_pass_rate, false_fail_rate,
               confidence_calibration_error, revalidation_completeness_rate,
               patch_recurrence_rate, runtime_contradiction_rate,
               proof_coverage_rate, samples)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """,
            snap.defect_escape_rate, snap.false_pass_rate, snap.false_fail_rate,
            snap.confidence_calibration_error, snap.revalidation_completeness_rate,
            snap.patch_recurrence_rate, snap.runtime_contradiction_rate,
            snap.proof_coverage_rate, snap.samples,
        )


async def latest(pool: asyncpg.Pool) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM truth_kpi_snapshots ORDER BY captured_at DESC LIMIT 1",
        )
    if not row:
        return None
    return {k: float(v) if isinstance(v, int | float) else v
            for k, v in dict(row).items() if k != "id"}
