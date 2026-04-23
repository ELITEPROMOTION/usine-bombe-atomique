"""V5.3 BLOC 2 - Evidence Harvester (24/7).

Fetch httpx + backoff exponentiel (max 4 tries) + quarantaine si > 1h down.
Ingestion en sandbox conceptuelle (pas d'execution de code externe).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import asyncpg
import httpx

from app.ctc import source_registry

logger = logging.getLogger(__name__)

BACKOFF_BASE_SEC = 2
BACKOFF_MAX_TRIES = 4
HTTP_TIMEOUT = 10.0

# Patterns suspects dans contenu (simple sandbox check)
SUSPICIOUS_PATTERNS = [
    re.compile(r"<script\b", re.IGNORECASE),
    re.compile(r"eval\s*\(", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
]


@dataclass
class HarvestResult:
    source_id: str
    url: str
    http_status: int
    bytes_received: int
    content_hash: str | None
    changed: bool
    error: str | None
    latency_ms: int
    suspicious: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def _is_suspicious(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in SUSPICIOUS_PATTERNS)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


async def fetch_one(
    pool: asyncpg.Pool, source_id: str, *,
    skip_actual_fetch: bool = False,
) -> HarvestResult:
    """Fetch a single source with backoff. If skip_actual_fetch=True,
    simulate (pour tests offline)."""
    src = await source_registry.get(pool, source_id)
    if src is None:
        return HarvestResult(
            source_id=source_id, url="", http_status=0, bytes_received=0,
            content_hash=None, changed=False, error="source unknown",
            latency_ms=0, suspicious=False)
    if src.status == "quarantined":
        return HarvestResult(
            source_id=source_id, url=src.url, http_status=0,
            bytes_received=0, content_hash=None, changed=False,
            error="quarantined", latency_ms=0, suspicious=False)

    t0 = time.perf_counter()
    last_error: str | None = None
    http_status = 0
    body = ""
    if skip_actual_fetch:
        body = f"simulated content for {src.url}"
        http_status = 200
    else:
        for attempt in range(1, BACKOFF_MAX_TRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT,
                                                follow_redirects=True) as c:
                    r = await c.get(src.url)
                    http_status = r.status_code
                    body = r.text or ""
                if 200 <= http_status < 400:
                    break
                last_error = f"http {http_status}"
            except Exception as exc:
                last_error = str(exc)[:200]
            await asyncio.sleep(BACKOFF_BASE_SEC ** attempt)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    body_bytes = len(body.encode("utf-8", errors="replace"))
    content_hash = _hash(body) if body else None
    suspicious = _is_suspicious(body)

    # Detect change
    changed = False
    if content_hash and src:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE truth_sources SET checksum = $2, "
                "last_validated_at = NOW() WHERE source_id = $1 "
                "AND (checksum IS NULL OR checksum != $2)",
                __import__("uuid").UUID(source_id), content_hash,
            )
            prev_row = await conn.fetchrow(
                "SELECT content_hash FROM evidence_harvesting_log "
                "WHERE source_id = $1 ORDER BY fetched_at DESC LIMIT 1 OFFSET 1",
                __import__("uuid").UUID(source_id),
            )
            if prev_row and prev_row["content_hash"] != content_hash:
                changed = True

    await source_registry.record_harvest(
        pool, source_id, http_status=http_status,
        bytes_received=body_bytes, content_hash=content_hash,
        changed=changed, error=last_error, latency_ms=latency_ms,
    )
    # Auto-quarantine si suspicious
    if suspicious:
        await source_registry.quarantine(
            pool, source_id, reason="suspicious content pattern detected")

    return HarvestResult(
        source_id=source_id, url=src.url, http_status=http_status,
        bytes_received=body_bytes, content_hash=content_hash,
        changed=changed, error=last_error, latency_ms=latency_ms,
        suspicious=suspicious,
    )


async def harvest_domain(
    pool: asyncpg.Pool, domain: str, *,
    skip_actual_fetch: bool = True,
) -> list[HarvestResult]:
    sources = await source_registry.by_domain(pool, domain, min_tier=5)
    return [await fetch_one(pool, s.source_id,
                              skip_actual_fetch=skip_actual_fetch)
            for s in sources]


async def harvest_cycle(
    pool: asyncpg.Pool, *, skip_actual_fetch: bool = True,
) -> dict[str, Any]:
    """Execute un cycle complet sur toutes les sources actives."""
    sources = await source_registry.list_all(pool, status="active")
    results: list[HarvestResult] = []
    for s in sources:
        results.append(await fetch_one(pool, s.source_id,
                                          skip_actual_fetch=skip_actual_fetch))
    return {
        "total": len(results),
        "ok": sum(1 for r in results if 200 <= r.http_status < 400),
        "errors": sum(1 for r in results if r.error),
        "suspicious": sum(1 for r in results if r.suspicious),
        "changed": sum(1 for r in results if r.changed),
    }
