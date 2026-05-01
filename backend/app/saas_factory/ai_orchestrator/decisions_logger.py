"""Journalisation des decisions IA dans `ai_decisions_log`.

Chaque appel via `AIRouter.route()` produit une ligne :
- prompt_hash (sha256, jamais le prompt brut)
- prompt_preview (200 premiers chars max — utile en debug)
- response_preview (200 premiers chars)
- requested / actual provider
- tokens, cost, latency
- fallback_used, retries, loop_detected, error_msg
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

PREVIEW_LEN: int = 200


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: UUID
    project_id: str
    requested_provider: str
    actual_provider: str
    status: str
    prompt_hash: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    fallback_used: bool
    retries: int
    loop_detected: bool
    error_msg: str | None
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


def _short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _preview(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s[:PREVIEW_LEN] if len(s) > PREVIEW_LEN else s


class DecisionsLogger:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def log(
        self,
        *,
        project_id: str,
        requested_provider: str,
        actual_provider: str,
        status: str,            # 'ok' | 'fallback' | 'error' | 'budget_blocked' | 'loop_blocked'
        prompt: str,
        response_text: str | None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        fallback_used: bool = False,
        retries: int = 0,
        loop_detected: bool = False,
        error_msg: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        prompt_hash = _short_hash(prompt)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ai_decisions_log (
                    project_id, requested_provider, actual_provider, status,
                    prompt_hash, prompt_preview, response_preview,
                    tokens_in, tokens_out, cost_usd, latency_ms,
                    fallback_used, retries, loop_detected,
                    error_msg, metadata_json
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7,
                    $8, $9, $10, $11,
                    $12, $13, $14,
                    $15, $16::jsonb
                ) RETURNING decision_id
                """,
                project_id,
                requested_provider[:32],
                actual_provider[:32],
                status[:32],
                prompt_hash,
                _preview(prompt),
                _preview(response_text),
                int(tokens_in),
                int(tokens_out),
                float(cost_usd),
                int(latency_ms),
                bool(fallback_used),
                int(retries),
                bool(loop_detected),
                (error_msg or "")[:500] or None,
                json.dumps(metadata or {}, sort_keys=True,
                           ensure_ascii=False, default=str),
            )
        logger.info(
            "ai_decision project=%s req=%s actual=%s status=%s cost=%.4f$ retries=%d",
            project_id, requested_provider, actual_provider, status,
            cost_usd, retries,
        )
        return row["decision_id"]

    async def stats_for_project(self, project_id: str) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS calls,
                    COALESCE(SUM(cost_usd), 0)::FLOAT8 AS total_cost,
                    COALESCE(SUM(tokens_in), 0)::BIGINT AS tokens_in,
                    COALESCE(SUM(tokens_out), 0)::BIGINT AS tokens_out,
                    SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END)::INT AS fallbacks,
                    SUM(CASE WHEN loop_detected THEN 1 ELSE 0 END)::INT AS loops,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END)::INT AS errors
                  FROM ai_decisions_log
                 WHERE project_id = $1
                """,
                project_id,
            )
        return dict(row) if row else {}
