"""Active learning loop V5.8.

Strategie :
  1. Decision avec confidence < threshold -> submit loop
  2. Propose 1-3 alternatives au CEO Ahmed via inbox (contrat C)
  3. Capture feedback (accept/reject/modify)
  4. Propage feedback dans :
     - prompt_cache (positive examples)
     - memory_engine (learning)
     - rules_engine (si modification d'une regle)

Metriques :
  - agreement_rate : % Ahmed accepte propositions
  - improvement_delta : diff confidence avant vs apres apprentissage
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger("uba.intelligence.active_learner")

DEFAULT_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class ActiveLearningLoop:
    id: int
    decision_id: str | None
    domain_id: str | None
    input_context: dict[str, Any]
    original_output: dict[str, Any]
    original_confidence: float | None
    proposals: list[dict[str, Any]]
    status: str = "pending"
    ahmed_choice: dict[str, Any] | None = None
    feedback_text: str | None = None
    agreement_score: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    applied_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "decision_id": self.decision_id,
            "domain_id": self.domain_id,
            "input_context": self.input_context,
            "original_output": self.original_output,
            "original_confidence": self.original_confidence,
            "proposals": self.proposals,
            "status": self.status,
            "ahmed_choice": self.ahmed_choice,
            "feedback_text": self.feedback_text,
            "agreement_score": self.agreement_score,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


class ActiveLearner:
    """Gere le cycle de vie des loops d'apprentissage actif."""

    def __init__(
        self, pool: asyncpg.Pool,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.pool = pool
        self.confidence_threshold = confidence_threshold

    async def submit_loop(
        self,
        decision_id: str | None,
        domain_id: str | None,
        input_context: dict[str, Any],
        original_output: dict[str, Any],
        original_confidence: float,
        proposals: list[dict[str, Any]] | None = None,
    ) -> int:
        """Cree un loop si confidence < threshold. Retourne loop_id ou -1."""
        if original_confidence >= self.confidence_threshold:
            return -1

        # Genere des proposals si absent
        proposals = proposals or self._generate_proposals(
            input_context, original_output,
        )

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO active_learning_loops
                    (decision_id, domain_id, input_context, original_output,
                     original_confidence, proposals)
                VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb, $5, $6::jsonb)
                RETURNING id
                """,
                UUID(decision_id) if decision_id else None,
                domain_id,
                json.dumps(input_context),
                json.dumps(original_output),
                original_confidence,
                json.dumps(proposals),
            )
        logger.info(
            "active_learning_loop_created id=%s domain=%s confidence=%.3f",
            row["id"], domain_id, original_confidence,
        )
        return int(row["id"])

    def _generate_proposals(
        self, input_context: dict[str, Any], output: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Genere 1-3 alternatives lightweight (placeholder pour reasoning_core)."""
        alts = [
            {"variant": "confident", "output": output,
             "rationale": "status quo"},
            {"variant": "conservative",
             "output": {**output, "flag_for_review": True},
             "rationale": "human review marker"},
        ]
        return alts

    async def list_pending(
        self, domain_id: str | None = None, limit: int = 50,
    ) -> list[ActiveLearningLoop]:
        query = """
            SELECT id, decision_id, domain_id, input_context, original_output,
                   original_confidence, proposals, status, ahmed_choice,
                   feedback_text, agreement_score, created_at, applied_at
            FROM active_learning_loops
            WHERE status = 'pending' AND expires_at > NOW()
        """
        params: list[Any] = []
        if domain_id:
            query += " AND domain_id = $1"
            params.append(domain_id)
            query += " ORDER BY created_at DESC LIMIT $2"
            params.append(limit)
        else:
            query += " ORDER BY created_at DESC LIMIT $1"
            params.append(limit)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_loop(r) for r in rows]

    async def apply_feedback(
        self, loop_id: int, choice: dict[str, Any],
        feedback_text: str | None = None,
        agreement_score: float | None = None,
        status: str = "accepted",
    ) -> ActiveLearningLoop | None:
        """Ahmed a valide/rejete. Met a jour + declenche propagation."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE active_learning_loops
                SET status = $2,
                    ahmed_choice = $3::jsonb,
                    feedback_text = $4,
                    agreement_score = $5,
                    applied_at = NOW()
                WHERE id = $1 AND status = 'pending'
                RETURNING id, decision_id, domain_id, input_context,
                          original_output, original_confidence, proposals,
                          status, ahmed_choice, feedback_text,
                          agreement_score, created_at, applied_at
                """,
                loop_id, status, json.dumps(choice), feedback_text,
                agreement_score,
            )
        if row is None:
            return None
        loop = self._row_to_loop(row)
        # Propagation feedback (placeholder : logue pour traceability)
        logger.info(
            "active_learning_feedback applied loop_id=%s status=%s "
            "agreement=%s domain=%s",
            loop_id, status, agreement_score, loop.domain_id,
        )
        return loop

    async def metrics(
        self, window_days: int = 30, domain_id: str | None = None,
    ) -> dict[str, Any]:
        """Compute + persist metriques (agreement rate)."""
        async with self.pool.acquire() as conn:
            if domain_id:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM((status='accepted')::int) AS accepted,
                        SUM((status='rejected')::int) AS rejected,
                        SUM((status='modified')::int) AS modified,
                        AVG(agreement_score) AS avg_agreement
                    FROM active_learning_loops
                    WHERE created_at > NOW() - ($1 || ' days')::interval
                      AND domain_id = $2
                    """, str(window_days), domain_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM((status='accepted')::int) AS accepted,
                        SUM((status='rejected')::int) AS rejected,
                        SUM((status='modified')::int) AS modified,
                        AVG(agreement_score) AS avg_agreement
                    FROM active_learning_loops
                    WHERE created_at > NOW() - ($1 || ' days')::interval
                    """, str(window_days),
                )
        total = int(row["total"] or 0)
        accepted = int(row["accepted"] or 0)
        rejected = int(row["rejected"] or 0)
        modified = int(row["modified"] or 0)
        agreement_rate = ((accepted + modified * 0.5) / total) if total else 0.0
        metrics = {
            "window_days": window_days,
            "domain_id": domain_id,
            "total_loops": total,
            "accepted_count": accepted,
            "rejected_count": rejected,
            "modified_count": modified,
            "pending_count": total - accepted - rejected - modified,
            "agreement_rate": round(agreement_rate, 3),
            "avg_agreement_score": (
                float(row["avg_agreement"]) if row["avg_agreement"] else None
            ),
        }
        # Persist
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO active_learning_metrics
                    (window_days, domain_id, total_loops, accepted_count,
                     rejected_count, modified_count, agreement_rate)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                window_days, domain_id, total, accepted, rejected, modified,
                agreement_rate,
            )
        return metrics

    async def history(
        self, days: int = 30, limit: int = 100,
    ) -> list[ActiveLearningLoop]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, decision_id, domain_id, input_context,
                       original_output, original_confidence, proposals,
                       status, ahmed_choice, feedback_text, agreement_score,
                       created_at, applied_at
                FROM active_learning_loops
                WHERE created_at > NOW() - ($1 || ' days')::interval
                ORDER BY created_at DESC
                LIMIT $2
                """, str(days), limit,
            )
        return [self._row_to_loop(r) for r in rows]

    @staticmethod
    def _row_to_loop(row: Any) -> ActiveLearningLoop:
        return ActiveLearningLoop(
            id=int(row["id"]),
            decision_id=str(row["decision_id"]) if row["decision_id"] else None,
            domain_id=row["domain_id"],
            input_context=_parse_json(row["input_context"]),
            original_output=_parse_json(row["original_output"]),
            original_confidence=(float(row["original_confidence"])
                                  if row["original_confidence"] else None),
            proposals=_parse_json(row["proposals"]) or [],
            status=row["status"],
            ahmed_choice=_parse_json(row["ahmed_choice"]),
            feedback_text=row["feedback_text"],
            agreement_score=(float(row["agreement_score"])
                             if row["agreement_score"] else None),
            created_at=row["created_at"],
            applied_at=row["applied_at"],
        )


def _parse_json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw
