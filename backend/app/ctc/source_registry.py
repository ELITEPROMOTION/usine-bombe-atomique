"""V5.3 BLOC 1 - Source Registry (Tier 1-5).

API CRUD + selection par domaine + quarantaine + fallback Tier equivalent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


# Hierarchie acces : plus bas = meilleur
ACCESS_RANK = {
    "api_native":             1,
    "sdk_official":           2,
    "cli_official":           3,
    "connector_orchestrator": 4,
    "agentic_navigation":     5,
    "desktop_automation":     6,
    "manual":                 7,
}

TIER_WEIGHT = {1: 1.5, 2: 1.0, 3: 0.7, 4: 0.4, 5: 0.0}


@dataclass
class TruthSource:
    source_id: str
    domain: str
    url: str
    source_type: str
    authority_tier: int
    access_mode: str
    freshness_policy_seconds: int
    status: str
    last_validated_at: datetime | None
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id, "domain": self.domain,
            "url": self.url, "source_type": self.source_type,
            "authority_tier": self.authority_tier,
            "access_mode": self.access_mode,
            "freshness_policy_seconds": self.freshness_policy_seconds,
            "status": self.status, "notes": self.notes,
            "last_validated_at": self.last_validated_at.isoformat()
                if self.last_validated_at else None,
        }


def tier_weight(tier: int) -> float:
    return TIER_WEIGHT.get(tier, 0.0)


async def register(
    pool: asyncpg.Pool, *,
    domain: str, url: str, source_type: str, authority_tier: int,
    access_mode: str = "manual", notes: str | None = None,
    freshness_policy_seconds: int = 86400,
) -> str:
    """Ajoute une source. Retourne source_id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO truth_sources(domain, url, source_type,
                authority_tier, access_mode, freshness_policy_seconds, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (url) DO UPDATE SET notes = COALESCE(EXCLUDED.notes, truth_sources.notes)
            RETURNING source_id
            """,
            domain[:60], url, source_type[:30], authority_tier,
            access_mode[:40], freshness_policy_seconds, notes,
        )
    return str(row["source_id"])


async def get(pool: asyncpg.Pool, source_id: str) -> TruthSource | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM truth_sources WHERE source_id=$1", UUID(source_id))
    return _to_source(row) if row else None


async def by_domain(
    pool: asyncpg.Pool, domain: str, *,
    min_tier: int = 5, only_active: bool = True,
) -> list[TruthSource]:
    sql = ("SELECT * FROM truth_sources WHERE domain = $1 "
            "AND authority_tier <= $2")
    if only_active:
        sql += " AND status = 'active'"
    sql += " ORDER BY authority_tier ASC, created_at DESC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, domain[:60], min_tier)
    return [_to_source(r) for r in rows]


async def pick_best(
    pool: asyncpg.Pool, domain: str, min_count: int = 3,
) -> list[TruthSource]:
    """Selectionne N sources de meilleur Tier actif."""
    sources = await by_domain(pool, domain, min_tier=3, only_active=True)
    if len(sources) < min_count:
        # Elargit aux Tier 4 si besoin
        sources = await by_domain(pool, domain, min_tier=4, only_active=True)
    return sources[:min_count] if len(sources) >= min_count else sources


async def quarantine(
    pool: asyncpg.Pool, source_id: str, reason: str,
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE truth_sources SET status='quarantined', "
            "access_justification=$2 WHERE source_id=$1",
            UUID(source_id), reason[:500])
        # Persist event
        await conn.execute(
            """
            INSERT INTO circuit_breaker_events(source_id, event_type, reason)
            VALUES ($1, 'quarantined', $2)
            """, UUID(source_id), reason[:500])
    return result.endswith("1")


async def restore(pool: asyncpg.Pool, source_id: str) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE truth_sources SET status='active' WHERE source_id=$1",
            UUID(source_id))
        await conn.execute(
            """
            INSERT INTO circuit_breaker_events(source_id, event_type, reason)
            VALUES ($1, 'restored', 'manual restoration')
            """, UUID(source_id))
    return result.endswith("1")


async def record_harvest(
    pool: asyncpg.Pool, source_id: str, *,
    http_status: int, bytes_received: int, content_hash: str | None,
    changed: bool, error: str | None = None, latency_ms: int = 0,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO evidence_harvesting_log(source_id, http_status,
                bytes_received, content_hash, changed, error, latency_ms)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            UUID(source_id), http_status, bytes_received,
            content_hash, changed, error, latency_ms)


async def latest_harvests(
    pool: asyncpg.Pool, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT h.source_id, s.url, s.domain, s.authority_tier,
                   h.fetched_at, h.http_status, h.changed, h.latency_ms,
                   h.error
            FROM evidence_harvesting_log h
            LEFT JOIN truth_sources s ON s.source_id = h.source_id
            ORDER BY h.fetched_at DESC LIMIT $1
            """, limit,
        )
    return [{
        "source_id": str(r["source_id"]) if r["source_id"] else None,
        "url": r["url"], "domain": r["domain"],
        "authority_tier": r["authority_tier"],
        "fetched_at": r["fetched_at"].isoformat(),
        "http_status": r["http_status"], "changed": r["changed"],
        "latency_ms": r["latency_ms"], "error": r["error"],
    } for r in rows]


async def list_all(
    pool: asyncpg.Pool, status: str | None = None,
) -> list[TruthSource]:
    sql = "SELECT * FROM truth_sources"
    args: list[Any] = []
    if status:
        sql += " WHERE status = $1"
        args.append(status)
    sql += " ORDER BY authority_tier ASC, domain ASC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [_to_source(r) for r in rows]


def _to_source(row: asyncpg.Record) -> TruthSource:
    return TruthSource(
        source_id=str(row["source_id"]),
        domain=row["domain"], url=row["url"],
        source_type=row["source_type"],
        authority_tier=row["authority_tier"],
        access_mode=row["access_mode"],
        freshness_policy_seconds=row["freshness_policy_seconds"],
        status=row["status"],
        last_validated_at=row["last_validated_at"],
        notes=row["notes"],
    )
