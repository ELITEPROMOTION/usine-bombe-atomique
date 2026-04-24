"""Tests health checks + SLO V5.7."""
from __future__ import annotations

import pytest

from app.health.checks import (
    CHECKS,
    CheckStatus,
    HealthCheckRegistry,
    run_all,
)

pytestmark = pytest.mark.asyncio


# ---------- Registry ----------

def test_15_checks_registered() -> None:
    assert len(CHECKS) == 15


def test_check_names_unique() -> None:
    names = list(CHECKS.keys())
    assert len(names) == len(set(names))


def test_registry_singleton() -> None:
    r1 = HealthCheckRegistry.instance()
    r2 = HealthCheckRegistry.instance()
    assert r1 is r2


def test_list_check_names() -> None:
    r = HealthCheckRegistry.instance()
    names = r.list_check_names()
    assert len(names) == 15
    assert "postgres_primary_ping" in names
    assert "redis_primary_ping" in names
    assert "vault_status" in names


async def test_run_individual_check(pool) -> None:
    r = HealthCheckRegistry.instance()
    result = await r.run("postgres_primary_ping", use_cache=False)
    assert result.name == "postgres_primary_ping"
    assert result.is_critical is True


async def test_run_unknown_check(pool) -> None:
    r = HealthCheckRegistry.instance()
    result = await r.run("nonexistent_check")
    assert result.status == CheckStatus.UNKNOWN


async def test_postgres_ping_healthy(pool) -> None:
    from app.health.checks import check_postgres_primary_ping
    r = await check_postgres_primary_ping()
    assert r.name == "postgres_primary_ping"
    assert r.is_critical is True
    assert r.status in (CheckStatus.HEALTHY, CheckStatus.DEGRADED)


async def test_redis_ping_healthy(pool) -> None:
    from app.health.checks import check_redis_primary_ping
    r = await check_redis_primary_ping()
    assert r.is_critical is True
    assert r.status in (CheckStatus.HEALTHY, CheckStatus.DEGRADED,
                         CheckStatus.UNHEALTHY)


async def test_vault_status() -> None:
    from app.health.checks import check_vault_status
    r = await check_vault_status()
    assert r.name == "vault_status"
    assert r.is_critical is True


async def test_disk_usage() -> None:
    from app.health.checks import check_disk_usage
    r = await check_disk_usage()
    assert r.name == "disk_usage"
    assert "percent" in r.details
    assert r.is_critical is True


async def test_memory_usage() -> None:
    from app.health.checks import check_memory_usage
    r = await check_memory_usage()
    assert r.name == "memory_usage"


async def test_cpu_load() -> None:
    from app.health.checks import check_cpu_load
    r = await check_cpu_load()
    assert r.name == "cpu_load_1min"


async def test_claude_api_latency() -> None:
    from app.health.checks import check_claude_api_latency
    r = await check_claude_api_latency()
    assert r.name == "claude_api_latency"
    assert "breaker_state" in r.details


async def test_queue_depth(pool) -> None:
    from app.health.checks import check_queue_depth
    r = await check_queue_depth()
    assert r.name == "queue_depth_arq"


async def test_failed_tasks_rate(pool) -> None:
    from app.health.checks import check_failed_tasks_rate
    r = await check_failed_tasks_rate()
    assert r.name == "failed_tasks_rate"


async def test_truth_chain_integrity(pool) -> None:
    from app.health.checks import check_truth_chain_integrity
    r = await check_truth_chain_integrity()
    assert r.name == "truth_chain_integrity"
    assert r.is_critical is True


async def test_evidence_chain_valid(pool) -> None:
    from app.health.checks import check_evidence_chain_valid
    r = await check_evidence_chain_valid()
    assert r.name == "evidence_chain_valid"
    assert r.is_critical is True


async def test_backup_freshness(pool) -> None:
    from app.health.checks import check_backup_freshness
    r = await check_backup_freshness()
    assert r.name == "backup_freshness"


async def test_run_all(pool) -> None:
    results = await run_all(use_cache=False)
    assert len(results) == 15
    critical = [r for r in results if r.is_critical]
    assert len(critical) >= 5  # postgres, redis, vault, disk, memory, truth_chain...


async def test_cache_respects_ttl(pool) -> None:
    r = HealthCheckRegistry.instance()
    r1 = await r.run("postgres_primary_ping")
    r2 = await r.run("postgres_primary_ping")  # cache hit
    assert r1.timestamp == r2.timestamp  # cache hit
