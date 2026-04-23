"""V5.1 BLOC 6 - Autonomy Explainability API.

Pour tout correlation_id, repond a 3 questions :
  1. Pourquoi le systeme a (ou n'a PAS) escalade ?
  2. Quels niveaux ont ete tentes ?
  3. Quels etaient les fallbacks envisages ?

Backend pour le CEO dashboard V2 + endpoints Ahmed mobile first.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import asyncpg

from app.autonomy import correlation_id_universal


async def explain(
    pool: asyncpg.Pool, correlation_id: str,
) -> dict[str, Any]:
    trace = await correlation_id_universal.trace(pool, correlation_id)
    if not trace.get("found"):
        return {"correlation_id": correlation_id, "found": False}

    async with pool.acquire() as conn:
        decisions = await conn.fetch(
            """
            SELECT action, payload_json AS payload, created_at FROM audit_events
            WHERE action = 'autonomy_decision'
              AND payload_json::text LIKE '%' || $1 || '%'
            ORDER BY created_at ASC LIMIT 50
            """, correlation_id,
        )

    parsed_decisions: list[dict[str, Any]] = []
    for d in decisions:
        p = d["payload"]
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except json.JSONDecodeError:
                p = {}
        parsed_decisions.append({
            "at": d["created_at"].isoformat(),
            "mode": p.get("mode"),
            "confidence": p.get("confidence"),
            "scope": p.get("scope"),
            "constraints": p.get("constraints", []),
        })

    return {
        "correlation_id": correlation_id,
        "found": True,
        "trace": trace,
        "decisions": parsed_decisions,
        "summary": _summarize(trace, parsed_decisions),
    }


def _summarize(trace: dict[str, Any], decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return "aucune decision autonomy enregistree (traitement standard)"
    final = decisions[-1]
    hops = trace.get("hops", 0)
    mode = final.get("mode", "?")
    msg = f"Verdict final: {mode} apres {hops} hop(s) sur {len(decisions)} decisions."
    if mode == "ESCALATE":
        msg += " Escalation justifiee par Human Necessity Proof."
    elif mode == "CONTINUE":
        msg += " Systeme a resolu toute l'ambiguite avant escalation."
    elif mode in ("PROBE", "CONSTRAIN", "DEFER"):
        msg += " Action menee sans interruption Ahmed."
    return msg


async def recent_avoided_escalations(
    pool: asyncpg.Pool, limit: int = 10,
) -> list[dict[str, Any]]:
    """Retourne les N dernieres escalations 'evitees' (resolved avant L4)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT correlation_id, level, kind, evidence, created_at
            FROM ambiguity_ledger
            WHERE resolved = TRUE AND level < 4
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        ev = r["evidence"]
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except json.JSONDecodeError:
                ev = {}
        out.append({
            "correlation_id": r["correlation_id"],
            "resolved_at_level": r["level"],
            "kind": r["kind"],
            "evidence": ev,
            "at": r["created_at"].isoformat() if isinstance(r["created_at"], datetime)
                  else str(r["created_at"]),
        })
    return out
