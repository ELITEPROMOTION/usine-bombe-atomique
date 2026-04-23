"""V5.3 BLOC 16 - Truth Explainability API.

Fonctions d'explication pour le router /truth/*.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def explain_event(
    pool: asyncpg.Pool, event_id: str,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM evidence_chain_events WHERE event_id = $1
            """, UUID(event_id),
        )
    if row is None:
        return {"found": False}
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif k in ("source_refs", "evidence_refs") and isinstance(v, str):
            import json as _j
            try:
                d[k] = _j.loads(v)
            except _j.JSONDecodeError:
                pass
    d["found"] = True
    return d


async def sources_for_event(
    pool: asyncpg.Pool, event_id: str,
) -> list[dict[str, Any]]:
    ev = await explain_event(pool, event_id)
    if not ev.get("found"):
        return []
    src_ids = ev.get("source_refs") or []
    if not src_ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source_id, url, domain, authority_tier, status
            FROM truth_sources WHERE source_id = ANY($1::uuid[])
            """, [UUID(s) for s in src_ids],
        )
    return [dict(r) | {"source_id": str(r["source_id"])} for r in rows]


async def assertions_for_event(
    pool: asyncpg.Pool, event_id: str,
) -> list[dict[str, Any]]:
    ev = await explain_event(pool, event_id)
    if not ev.get("found"):
        return []
    ass_ids = ev.get("evidence_refs") or []
    if not ass_ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT assertion_id, assertion_type, domain, severity,
                   status, normalized_text
            FROM truth_assertions WHERE assertion_id = ANY($1::uuid[])
            """, [UUID(a) for a in ass_ids],
        )
    return [{
        "assertion_id": str(r["assertion_id"]),
        "type": r["assertion_type"], "domain": r["domain"],
        "severity": r["severity"], "status": r["status"],
        "text": r["normalized_text"],
    } for r in rows]


async def source_history(
    pool: asyncpg.Pool, source_id: str, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT fetched_at, http_status, changed, content_hash, error
            FROM evidence_harvesting_log WHERE source_id = $1
            ORDER BY fetched_at DESC LIMIT $2
            """, UUID(source_id), limit,
        )
    return [{
        "fetched_at": r["fetched_at"].isoformat(),
        "http_status": r["http_status"], "changed": r["changed"],
        "content_hash": r["content_hash"], "error": r["error"],
    } for r in rows]


async def latest_integrity_check(pool: asyncpg.Pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM evidence_chain_integrity_log "
            "ORDER BY checked_at DESC LIMIT 1"
        )
    if row is None:
        return {"never_checked": True}
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


async def phase_gate_details(
    pool: asyncpg.Pool, gate_id: str,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        gate = await conn.fetchrow(
            "SELECT * FROM phase_gates WHERE gate_id = $1", UUID(gate_id),
        )
        failures = await conn.fetch(
            "SELECT reason_code, reason_text, created_at "
            "FROM phase_gate_failures WHERE gate_id = $1 "
            "ORDER BY created_at DESC",
            UUID(gate_id),
        )
    if gate is None:
        return {"found": False}
    d = dict(gate)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat() if v else None
    d["failures"] = [{
        "reason_code": f["reason_code"], "reason_text": f["reason_text"],
        "at": f["created_at"].isoformat(),
    } for f in failures]
    d["found"] = True
    return d
