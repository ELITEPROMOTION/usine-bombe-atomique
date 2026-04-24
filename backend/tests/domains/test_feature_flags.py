"""Tests feature flags V5.6."""
from __future__ import annotations

import pytest

from app.core.feature_flags import FeatureFlagsService, _hash_bucket

pytestmark = pytest.mark.asyncio


def test_hash_bucket_deterministic() -> None:
    b1 = _hash_bucket("user-1", "flag.x")
    b2 = _hash_bucket("user-1", "flag.x")
    assert b1 == b2


def test_hash_bucket_different_users() -> None:
    b1 = _hash_bucket("user-1", "flag.x")
    b2 = _hash_bucket("user-2", "flag.x")
    # Should be different (with very high probability)
    assert b1 != b2


def test_hash_bucket_in_range_0_99() -> None:
    for i in range(20):
        b = _hash_bucket(f"u{i}", "f1")
        assert 0 <= b < 100


def test_hash_bucket_anon() -> None:
    b1 = _hash_bucket(None, "flag.x")
    b2 = _hash_bucket(None, "flag.x")
    assert b1 == b2


async def test_ff_list_flags(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    flags = await svc.list_flags()
    # Migration 027 seed 7 flags
    names = [f["flag_name"] for f in flags]
    assert "domain.fiscal_dz.enabled" in names


async def test_ff_is_enabled_global(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    enabled = await svc.is_enabled("domain.fiscal_dz.enabled")
    assert enabled is True


async def test_ff_unknown_returns_default(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    assert await svc.is_enabled("nonexistent.flag") is False
    assert await svc.is_enabled("nonexistent.flag", default=True) is True


async def test_ff_toggle(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    # Get initial state
    initial = await svc.is_enabled("feature.dark_mode")
    # Toggle off
    await svc.toggle("feature.dark_mode", False, "test")
    assert await svc.is_enabled("feature.dark_mode") is False
    # Restore
    await svc.toggle("feature.dark_mode", initial, "test")


async def test_ff_rollout_0pct(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    await svc.set_rollout("feature.rules_hot_reload", 0, "test")
    # No users should be enabled via rollout (globally disabled too in seed)
    assert await svc.is_enabled("feature.rules_hot_reload") is False


async def test_ff_rollout_100pct(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    await svc.set_rollout("feature.rules_hot_reload", 100, "test")
    # All users enabled
    assert await svc.is_enabled("feature.rules_hot_reload", user_id="any") is True
    # Cleanup
    await svc.set_rollout("feature.rules_hot_reload", 0, "test")


async def test_ff_metrics_structure(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    # Fire some evaluations
    await svc.is_enabled("feature.dark_mode", user_id="u1")
    await svc.is_enabled("feature.dark_mode", user_id="u2")
    m = await svc.metrics("feature.dark_mode", hours=1)
    assert "evaluations" in m
    assert "enabled_rate" in m
    assert "error_rate" in m


async def test_ff_rollout_percent_capped_100(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    await svc.set_rollout("feature.dark_mode", 200, "test")
    # Should be capped at 100
    flags = await svc.list_flags()
    dm = next(f for f in flags if f["flag_name"] == "feature.dark_mode")
    assert dm["rollout_percent"] == 100
    await svc.set_rollout("feature.dark_mode", 0, "test")


async def test_ff_tenant_override(pool) -> None:
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    # feature.rules_hot_reload is globally disabled
    # tenant_override not tested here (would need manual UPDATE).
    # Just verify the API doesn't crash :
    res = await svc.is_enabled(
        "feature.rules_hot_reload",
        tenant_id="00000000-0000-0000-0000-000000000001",
    )
    assert isinstance(res, bool)


async def test_ff_multiple_flags_parallel(pool) -> None:
    import asyncio
    svc = FeatureFlagsService(pool=pool, redis_client=None)
    results = await asyncio.gather(
        svc.is_enabled("domain.fiscal_dz.enabled"),
        svc.is_enabled("domain.juridique.enabled"),
        svc.is_enabled("domain.logistique.enabled"),
        svc.is_enabled("domain.rh.enabled"),
        svc.is_enabled("domain.comptabilite.enabled"),
    )
    assert all(r is True for r in results)


async def test_ff_migration_027_seeds(pool) -> None:
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM feature_flags")
    assert int(n) >= 7
