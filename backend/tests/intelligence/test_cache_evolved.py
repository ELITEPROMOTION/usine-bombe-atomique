"""Tests cache semantique evolue V5.8."""
from __future__ import annotations

import pytest

from app.intelligence.cache_evolved import (
    DEFAULT_TTL_S, DOMAIN_TTL_S, EvolvedCacheService,
)

pytestmark = pytest.mark.asyncio


async def test_store_and_lookup(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    await svc.store("fiscal_dz", "irg 300k", {"tranche": 2})
    res = await svc.lookup("fiscal_dz", "irg 300k")
    assert res == {"tranche": 2}


async def test_lookup_miss_returns_none(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    res = await svc.lookup("fiscal_dz", "query_inexistante")
    assert res is None


async def test_different_domains_isolated(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    await svc.store("fiscal_dz", "query X", {"answer": "fiscal"})
    await svc.store("juridique", "query X", {"answer": "juridique"})
    assert (await svc.lookup("fiscal_dz", "query X")) == {"answer": "fiscal"}
    assert (await svc.lookup("juridique", "query X")) == {"answer": "juridique"}


async def test_ttl_per_domain() -> None:
    # Verify TTL config
    assert DOMAIN_TTL_S["fiscal_dz"] == 30 * 86400
    assert DOMAIN_TTL_S["logistique"] == 1 * 86400
    assert DOMAIN_TTL_S["juridique"] == 7 * 86400


async def test_ttl_default_for_unknown_domain(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    ttl = svc._ttl_for("unknown_domain")
    assert ttl == DEFAULT_TTL_S


async def test_invalidate_domain(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    await svc.store("rh", "q1", {"r": 1})
    await svc.store("rh", "q2", {"r": 2})
    count = await svc.invalidate_domain("rh")
    assert count == 2
    assert await svc.lookup("rh", "q1") is None


async def test_metrics_per_domain(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    # Trigger some activity
    await svc.store("comptabilite", "q1", {"a": 1})
    await svc.lookup("comptabilite", "q1")
    await svc.lookup("comptabilite", "miss")
    m = await svc.metrics(domain_id="comptabilite")
    assert m["hits_24h"] >= 1
    assert m["misses_24h"] >= 1
    assert 0 <= m["hit_rate"] <= 1.0


async def test_metrics_all_domains(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    m = await svc.metrics()
    assert "by_domain" in m
    assert m["domain_count"] >= 5  # 5 domains configures


async def test_top_queries(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    await svc.store("fiscal_dz", "popular_query", {"r": 1})
    # Hit multiple times
    for _ in range(3):
        await svc.lookup("fiscal_dz", "popular_query")
    top = await svc.top_queries("fiscal_dz", limit=5)
    assert len(top) >= 1
    assert top[0]["hits"] >= 3


async def test_warm_queries(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    result = await svc.warm("fiscal_dz", ["q_new_1", "q_new_2"])
    assert result["warmed"] == 2
    assert result["skipped"] == 0
    assert result["domain"] == "fiscal_dz"


async def test_warm_skips_already_cached(pool) -> None:
    svc = EvolvedCacheService(pool, redis_client=None)
    await svc.store("fiscal_dz", "already_there", {"r": 1})
    result = await svc.warm("fiscal_dz", ["already_there", "q_new"])
    assert result["warmed"] == 1
    assert result["skipped"] == 1


async def test_5_domains_have_ttl_configured() -> None:
    for d in ["fiscal_dz", "juridique", "logistique", "rh", "comptabilite"]:
        assert d in DOMAIN_TTL_S
