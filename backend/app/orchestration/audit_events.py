"""Event Sourcing V4.1 - audit_events append-only.

Chaque action systeme produit un event immuable (retention 7 ans via
contrainte DB). Les triggers BEFORE UPDATE/DELETE rejettent toute mutation.
Hashage du payload canonique pour detection de falsification.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


def _canon(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def emit(
    pool: asyncpg.Pool,
    action: str,
    actor: str,
    payload: dict[str, Any],
    task_id: str | None = None,
    tenant_id: str | None = None,
) -> str:
    """Emet un event audit immuable et retourne son `event_id`."""
    payload_hash = _sha256(_canon(payload))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO audit_events
              (task_id, tenant_id, actor, action, payload_hash, payload_json)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            RETURNING event_id
            """,
            UUID(task_id) if task_id else None,
            UUID(tenant_id) if tenant_id else None,
            actor, action[:80], payload_hash, _canon(payload),
        )
    return str(row["event_id"])


async def tail(pool: asyncpg.Pool, limit: int = 100,
                action_filter: str | None = None) -> list[dict[str, Any]]:
    """Retourne les derniers events (optionnellement filtres par action)."""
    async with pool.acquire() as conn:
        if action_filter:
            rows = await conn.fetch(
                """
                SELECT event_id, task_id, tenant_id, actor, action,
                       payload_hash, payload_json, created_at
                FROM audit_events WHERE action = $1
                ORDER BY id DESC LIMIT $2
                """, action_filter, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT event_id, task_id, tenant_id, actor, action,
                       payload_hash, payload_json, created_at
                FROM audit_events ORDER BY id DESC LIMIT $1
                """, limit,
            )
    return [
        {
            "event_id": str(r["event_id"]),
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "tenant_id": str(r["tenant_id"]) if r["tenant_id"] else None,
            "actor": r["actor"],
            "action": r["action"],
            "payload_hash": r["payload_hash"],
            "payload": r["payload_json"],
            "created_at": r["created_at"].isoformat(),
        } for r in rows
    ]


async def verify_immutability(pool: asyncpg.Pool) -> dict[str, Any]:
    """Tente un UPDATE : doit lever une exception. Retourne la preuve."""
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM audit_events")
        if total == 0:
            return {"immutable": True, "reason": "aucun event a tester", "events": 0}
        try:
            await conn.execute(
                "UPDATE audit_events SET actor = 'TAMPER' WHERE id = "
                "(SELECT id FROM audit_events ORDER BY id DESC LIMIT 1)",
            )
            return {"immutable": False, "reason": "UPDATE a reussi, trigger absent",
                    "events": int(total)}
        except asyncpg.exceptions.RaiseError as exc:
            return {"immutable": True,
                    "reason": f"UPDATE refuse: {exc!s}", "events": int(total)}
