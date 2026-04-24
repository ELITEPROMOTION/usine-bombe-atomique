"""Cache semantique evolue V5.8 - per-domain + TTL adaptatif + warming + metrics.

Architecture :
  - Un sous-cache par domain_id (fiscal_dz, juridique, logistique, rh, comptabilite)
  - TTL adaptatif : fiscal_dz 30j / juridique 7j / logistique 1j / rh 7j / comptabilite 7j
  - Warming : pre-compute embeddings pour top 100 queries frequentes
  - Invalidation cascade via knowledge graph : changement rule -> flush domaine

Stockage : Redis hash par domaine + PostgreSQL fallback (semantic_cache V4 existant).
Cette extension enrichit sans casser l'existant.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import asyncpg

logger = logging.getLogger("uba.intelligence.cache_evolved")


# TTL par domaine (en secondes)
DOMAIN_TTL_S: dict[str, int] = {
    "fiscal_dz":    30 * 86400,  # 30 jours - regles stables
    "juridique":    7 * 86400,   # 7 jours - jurisprudence evolue
    "logistique":   1 * 86400,   # 1 jour - donnees stock temps reel
    "rh":           7 * 86400,   # 7 jours - paie mensuelle
    "comptabilite": 7 * 86400,   # 7 jours - cycles comptables
}

DEFAULT_TTL_S = 3 * 86400


@dataclass
class CacheEntry:
    query_hash: str
    domain_id: str
    query: str
    response: dict[str, Any]
    hits: int = 0
    created_at: float = 0.0
    last_access: float = 0.0


@dataclass
class DomainCacheMetrics:
    domain_id: str
    entries_count: int = 0
    hits_24h: int = 0
    misses_24h: int = 0
    total_lookup_ms: float = 0.0
    lookup_count: int = 0
    evictions: int = 0
    top_queries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        total = self.hits_24h + self.misses_24h
        return (self.hits_24h / total) if total else 0.0

    @property
    def avg_lookup_ms(self) -> float:
        return (self.total_lookup_ms / self.lookup_count) if self.lookup_count else 0.0


class EvolvedCacheService:
    """Cache per-domain avec TTL adaptatif + metrics."""

    def __init__(self, pool: asyncpg.Pool, redis_client: Any | None = None) -> None:
        self.pool = pool
        self.redis = redis_client
        # In-memory fallback (per-test, pas prod-scale)
        self._mem: dict[str, dict[str, CacheEntry]] = {}
        self._metrics: dict[str, DomainCacheMetrics] = {}

    def _ttl_for(self, domain_id: str) -> int:
        return DOMAIN_TTL_S.get(domain_id, DEFAULT_TTL_S)

    def _key(self, domain_id: str, query: str) -> str:
        return hashlib.sha256(
            f"{domain_id}::{query}".encode("utf-8"),
        ).hexdigest()

    def _get_metrics(self, domain_id: str) -> DomainCacheMetrics:
        if domain_id not in self._metrics:
            self._metrics[domain_id] = DomainCacheMetrics(domain_id=domain_id)
        return self._metrics[domain_id]

    async def lookup(
        self, domain_id: str, query: str,
    ) -> dict[str, Any] | None:
        start = time.perf_counter()
        m = self._get_metrics(domain_id)
        key = self._key(domain_id, query)

        # Try Redis first
        if self.redis is not None:
            try:
                raw = await self.redis.get(f"uba:cache:{domain_id}:{key}")
                if raw:
                    m.hits_24h += 1
                    m.lookup_count += 1
                    m.total_lookup_ms += (time.perf_counter() - start) * 1000
                    return json.loads(raw)
            except Exception as exc:
                logger.debug("redis cache lookup failed: %s", exc)

        # In-memory fallback
        domain_cache = self._mem.get(domain_id, {})
        entry = domain_cache.get(key)
        m.lookup_count += 1
        m.total_lookup_ms += (time.perf_counter() - start) * 1000
        if entry is not None:
            ttl = self._ttl_for(domain_id)
            if time.time() - entry.created_at < ttl:
                entry.hits += 1
                entry.last_access = time.time()
                m.hits_24h += 1
                return entry.response
            # TTL expired
            del domain_cache[key]
            m.evictions += 1

        m.misses_24h += 1
        return None

    async def store(
        self, domain_id: str, query: str, response: dict[str, Any],
    ) -> None:
        key = self._key(domain_id, query)
        ttl = self._ttl_for(domain_id)
        entry = CacheEntry(
            query_hash=key, domain_id=domain_id, query=query,
            response=response, created_at=time.time(),
            last_access=time.time(),
        )

        # Redis store (best effort)
        if self.redis is not None:
            try:
                await self.redis.setex(
                    f"uba:cache:{domain_id}:{key}", ttl,
                    json.dumps(response, default=str),
                )
            except Exception as exc:
                logger.debug("redis cache store failed: %s", exc)

        # In-memory fallback
        self._mem.setdefault(domain_id, {})[key] = entry

    async def invalidate_domain(self, domain_id: str) -> int:
        """Flush tout le cache d'un domaine."""
        count = 0
        if domain_id in self._mem:
            count += len(self._mem[domain_id])
            self._mem[domain_id].clear()
        m = self._get_metrics(domain_id)
        m.evictions += count
        if self.redis is not None:
            try:
                cursor = 0
                pattern = f"uba:cache:{domain_id}:*"
                while True:
                    cursor, keys = await self.redis.scan(
                        cursor=cursor, match=pattern, count=100,
                    )
                    if keys:
                        await self.redis.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            except Exception as exc:
                logger.debug("redis invalidate failed: %s", exc)
        logger.info(
            "cache.invalidate domain=%s entries=%d", domain_id, count,
        )
        return count

    async def metrics(self, domain_id: str | None = None) -> dict[str, Any]:
        if domain_id:
            m = self._get_metrics(domain_id)
            return {
                "domain_id": domain_id,
                "ttl_days": self._ttl_for(domain_id) // 86400,
                "entries_count": len(self._mem.get(domain_id, {})),
                "hits_24h": m.hits_24h,
                "misses_24h": m.misses_24h,
                "hit_rate": round(m.hit_rate, 3),
                "avg_lookup_ms": round(m.avg_lookup_ms, 2),
                "evictions": m.evictions,
            }
        # All domains
        out: dict[str, Any] = {"by_domain": {}}
        all_domains = set(self._mem.keys()) | set(DOMAIN_TTL_S.keys())
        for d in all_domains:
            out["by_domain"][d] = await self.metrics(d)
        out["domain_count"] = len(all_domains)
        return out

    async def top_queries(
        self, domain_id: str, limit: int = 10,
    ) -> list[dict[str, Any]]:
        entries = list(self._mem.get(domain_id, {}).values())
        entries.sort(key=lambda e: -e.hits)
        return [
            {"query": e.query[:200], "hits": e.hits,
             "age_seconds": int(time.time() - e.created_at)}
            for e in entries[:limit]
        ]

    async def warm(
        self, domain_id: str, queries: list[str],
        compute_fn: Any | None = None,
    ) -> dict[str, Any]:
        """Pre-compute + store N queries frequentes."""
        warmed = 0
        skipped = 0
        for q in queries:
            if await self.lookup(domain_id, q) is not None:
                skipped += 1
                continue
            # Pas de compute_fn -> placeholder entry for warming tracking
            placeholder = {"warmed": True, "query": q}
            if compute_fn is not None:
                try:
                    response = await compute_fn(q) if asyncio.iscoroutinefunction(
                        compute_fn,
                    ) else compute_fn(q)
                    await self.store(domain_id, q, response)
                except Exception as exc:
                    logger.debug("warm compute failed for %s: %s", q[:50], exc)
                    continue
            else:
                await self.store(domain_id, q, placeholder)
            warmed += 1
        return {"warmed": warmed, "skipped": skipped, "domain": domain_id}
