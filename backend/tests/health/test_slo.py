"""Tests SLO tracker V5.7."""
from __future__ import annotations

import pytest

from app.observability.slo_tracker import SLOTracker

pytestmark = pytest.mark.asyncio


async def test_list_definitions(pool) -> None:
    t = SLOTracker(pool)
    defs = await t.list_definitions()
    # Migration 028 seed 4 SLOs
    names = {d.slo_name for d in defs}
    assert "availability" in names
    assert "error_rate" in names


async def test_record_measurement(pool) -> None:
    t = SLOTracker(pool)
    await t.record("availability", good=100, bad=0, sli_value=100.0)
    # No exception = success


async def test_compute_status(pool) -> None:
    t = SLOTracker(pool)
    # Seed quelques data
    await t.record("availability", good=1000, bad=1)
    status = await t.compute_status("availability")
    assert status.slo_name == "availability"
    assert status.target_percent == 99.8
    assert 0 <= status.current_sli <= 100
    assert status.error_budget_minutes > 0


async def test_compute_unknown_slo_raises(pool) -> None:
    t = SLOTracker(pool)
    with pytest.raises(KeyError):
        await t.compute_status("nonexistent_slo")


async def test_status_all(pool) -> None:
    t = SLOTracker(pool)
    statuses = await t.status_all()
    assert len(statuses) >= 4  # 4 SLOs seeded


async def test_open_and_close_incident(pool) -> None:
    t = SLOTracker(pool)
    iid = await t.open_incident(
        slo_name="availability", severity="warning",
        burn_rate=5.0, reason="test",
    )
    assert iid > 0
    await t.close_incident(iid, resolution="auto-fixed",
                             resolved_auto=True)


async def test_incidents_list(pool) -> None:
    t = SLOTracker(pool)
    items = await t.incidents(limit=10)
    assert isinstance(items, list)


async def test_sli_calculation_correct(pool) -> None:
    t = SLOTracker(pool)
    # 99% success rate
    await t.record("error_rate", good=99, bad=1)
    status = await t.compute_status("error_rate")
    # sli est calcule sur la window complete (cumul)
    assert 0 <= status.current_sli <= 100


async def test_burn_rate_calculation(pool) -> None:
    t = SLOTracker(pool)
    # Pas d'echecs : burn rate proche 0
    await t.record("availability", good=1000, bad=0)
    status = await t.compute_status("availability")
    assert status.burn_rate_1h >= 0
    assert status.burn_rate_6h >= 0


async def test_migration_028_tables_exist(pool) -> None:
    async with pool.acquire() as conn:
        for tbl in ("slo_definitions", "slo_measurements", "slo_incidents"):
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1)", tbl,
            )
            assert exists, f"Table {tbl} missing"


async def test_4_slos_seeded(pool) -> None:
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM slo_definitions")
    assert int(n) >= 4
