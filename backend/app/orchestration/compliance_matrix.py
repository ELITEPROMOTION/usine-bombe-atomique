"""Upgrade 14 (BLOC D) - Matrice de conformite : exigence <-> test <-> preuve.

Stocke en base (migration 009). Chaque ligne lie :
- requirement_code / requirement_label
- test_ref   : reference au test qui valide
- proof_ref  : preuve materielle (evidence_ledger.event_id ou path artefact)
- statut     : open | in_progress | satisfied | waived | failed
- responsable / severity

Expose add / update / list_by_task / summary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg


@dataclass
class ComplianceItem:
    requirement_code: str
    requirement_label: str
    test_ref: str | None = None
    proof_ref: str | None = None
    statut: str = "open"
    responsable: str | None = None
    severity: str = "medium"


async def add(pool: asyncpg.Pool, task_id: str, item: ComplianceItem) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO compliance_matrix
              (task_id, requirement_code, requirement_label, test_ref, proof_ref,
               statut, responsable, severity)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (task_id, requirement_code) DO UPDATE SET
              requirement_label = EXCLUDED.requirement_label,
              test_ref = COALESCE(EXCLUDED.test_ref, compliance_matrix.test_ref),
              proof_ref = COALESCE(EXCLUDED.proof_ref, compliance_matrix.proof_ref),
              statut = EXCLUDED.statut,
              severity = EXCLUDED.severity,
              updated_at = NOW()
            RETURNING id
            """,
            UUID(task_id), item.requirement_code[:80], item.requirement_label[:4000],
            item.test_ref, item.proof_ref, item.statut, item.responsable, item.severity,
        )
    return str(row["id"])


async def set_status(
    pool: asyncpg.Pool, task_id: str, requirement_code: str,
    statut: str, proof_ref: str | None = None,
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE compliance_matrix
            SET statut = $3, proof_ref = COALESCE($4, proof_ref), updated_at = NOW()
            WHERE task_id = $1 AND requirement_code = $2
            RETURNING id
            """,
            UUID(task_id), requirement_code, statut, proof_ref,
        )
    return row is not None


async def list_by_task(pool: asyncpg.Pool, task_id: str) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT requirement_code, requirement_label, test_ref, proof_ref,
                   statut, responsable, severity, created_at, updated_at
            FROM compliance_matrix WHERE task_id = $1
            ORDER BY severity DESC, requirement_code
            """,
            UUID(task_id),
        )
    return [
        {
            "requirement_code": r["requirement_code"],
            "requirement_label": r["requirement_label"],
            "test_ref": r["test_ref"], "proof_ref": r["proof_ref"],
            "statut": r["statut"], "responsable": r["responsable"],
            "severity": r["severity"],
            "created_at": r["created_at"].isoformat(),
            "updated_at": r["updated_at"].isoformat(),
        } for r in rows
    ]


async def summary(pool: asyncpg.Pool, task_id: str) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT statut, severity, COUNT(*) AS n
            FROM compliance_matrix WHERE task_id = $1
            GROUP BY statut, severity
            """,
            UUID(task_id),
        )
    matrix: dict[str, dict[str, int]] = {}
    total = 0
    for r in rows:
        matrix.setdefault(r["statut"], {})[r["severity"]] = int(r["n"])
        total += int(r["n"])
    satisfied = sum(v for sev in matrix.get("satisfied", {}).values() for v in [sev])
    return {
        "total": total,
        "satisfied": satisfied,
        "satisfaction_rate": round(satisfied / max(1, total), 4),
        "matrix": matrix,
    }
