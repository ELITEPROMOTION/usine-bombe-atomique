"""V5.3 BLOC 4 - Truth Graph (WORM).

Append-only via trigger. Relations :
  supports, contradicts, depends_on, invalidates
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


LINK_TYPES = {"supports", "contradicts", "depends_on", "invalidates"}
ENTITY_TYPES = {"task", "artifact", "validation", "decision",
                 "version", "incident", "hypothesis", "risk"}


async def link(
    pool: asyncpg.Pool, *,
    assertion_id: str, entity_type: str, entity_id: str, link_type: str,
) -> str:
    if link_type not in LINK_TYPES:
        raise ValueError(f"link_type invalide : {link_type}")
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"entity_type invalide : {entity_type}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO truth_assertion_links(
                assertion_id, linked_entity_type, linked_entity_id, link_type)
            VALUES ($1, $2, $3, $4)
            RETURNING link_id
            """,
            UUID(assertion_id), entity_type, UUID(entity_id), link_type,
        )
    return str(row["link_id"])


async def evidence_for(
    pool: asyncpg.Pool, entity_type: str, entity_id: str,
) -> list[dict[str, Any]]:
    """Retourne toutes assertions liees (+ source + status)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT l.link_id, l.link_type, l.created_at,
                   a.assertion_id, a.assertion_type, a.domain, a.severity,
                   a.confidence, a.status, a.normalized_text,
                   a.source_id, s.url AS source_url, s.authority_tier
            FROM truth_assertion_links l
            JOIN truth_assertions a ON a.assertion_id = l.assertion_id
            LEFT JOIN truth_sources s ON s.source_id = a.source_id
            WHERE l.linked_entity_type = $1 AND l.linked_entity_id = $2
            ORDER BY l.created_at DESC
            """, entity_type, UUID(entity_id),
        )
    return [{
        "link_id": str(r["link_id"]), "link_type": r["link_type"],
        "assertion_id": str(r["assertion_id"]),
        "assertion_type": r["assertion_type"],
        "domain": r["domain"], "severity": r["severity"],
        "confidence": r["confidence"], "status": r["status"],
        "text": r["normalized_text"][:400],
        "source_url": r["source_url"],
        "authority_tier": r["authority_tier"],
        "linked_at": r["created_at"].isoformat(),
    } for r in rows]


async def contradictions_open(
    pool: asyncpg.Pool, limit: int = 50,
) -> list[dict[str, Any]]:
    """Liste les liens 'contradicts' actifs."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT link_id, assertion_id, linked_entity_type,
                   linked_entity_id, created_at
            FROM truth_assertion_links
            WHERE link_type = 'contradicts'
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    return [{
        "link_id": str(r["link_id"]),
        "assertion_id": str(r["assertion_id"]),
        "entity_type": r["linked_entity_type"],
        "entity_id": str(r["linked_entity_id"]),
        "created_at": r["created_at"].isoformat(),
    } for r in rows]


async def stats(pool: asyncpg.Pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT link_type, COUNT(*) AS n
            FROM truth_assertion_links GROUP BY link_type
            """
        )
    dist: dict[str, int] = {r["link_type"]: int(r["n"]) for r in rows}
    return {
        "total": sum(dist.values()),
        "by_link_type": dist,
    }
