"""Tests chaos framework + runbooks V5.7."""
from __future__ import annotations

import pytest

from app.resilience.chaos import SCENARIOS, ChaosRunner, list_scenarios
from app.resilience.runbooks import ALL_RUNBOOKS, RunbookOrchestrator, list_runbooks

pytestmark = pytest.mark.asyncio


# ---------- Chaos ----------

def test_20_scenarios_defined() -> None:
    assert len(SCENARIOS) == 20


def test_scenarios_unique_ids() -> None:
    ids = [s.scenario_id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_list_scenarios_api() -> None:
    scenarios = list_scenarios()
    assert len(scenarios) == 20
    assert all("scenario_id" in s for s in scenarios)
    assert all("impact" in s for s in scenarios)


def test_scenario_categories() -> None:
    cats = {s.category for s in SCENARIOS}
    assert {"network", "storage", "compute"} <= cats


async def test_chaos_runner_dry_run() -> None:
    runner = ChaosRunner(dry_run=True)
    result = await runner.run_scenario(SCENARIOS[0])
    assert result["dry_run"] is True
    assert result["outcome"] == "executed"
    assert result["system_recovered"] is True


async def test_chaos_runner_by_ids() -> None:
    runner = ChaosRunner(dry_run=True)
    results = await runner.run_by_ids(["kill_redis_connection", "slow_claude_api"])
    assert len(results) == 2
    assert results[0]["scenario_id"] == "kill_redis_connection"


async def test_chaos_runner_unknown_id() -> None:
    runner = ChaosRunner(dry_run=True)
    results = await runner.run_by_ids(["nonexistent"])
    assert len(results) == 0


async def test_chaos_runner_run_all_completes(pool) -> None:
    runner = ChaosRunner(dry_run=True)
    results = await runner.run_all()
    assert len(results) == 20
    assert all(r["outcome"] == "executed" for r in results)


# ---------- Runbooks ----------

def test_15_runbooks_defined() -> None:
    assert len(ALL_RUNBOOKS) == 15


def test_runbooks_unique_ids() -> None:
    ids = [cls.runbook_id for cls in ALL_RUNBOOKS]
    assert len(ids) == len(set(ids))
    # Format RB-001..RB-015
    assert all(rid.startswith("RB-") for rid in ids)


def test_list_runbooks_api() -> None:
    rbs = list_runbooks()
    assert len(rbs) == 15


async def test_runbook_orchestrator_scan_all(pool) -> None:
    orch = RunbookOrchestrator()
    results = await orch.scan_all()
    assert len(results) == 15
    # Pas de remediation auto en env saine
    assert all(not r.detected or not r.remediated for r in results) \
        or all(r.detected == r.verified or not r.detected for r in results)


async def test_runbook_detect_returns_bool(pool) -> None:
    from app.resilience.runbooks import RB001_PostgresDown
    rb = RB001_PostgresDown()
    result = await rb.detect()
    assert isinstance(result, bool)
    # Postgres is up in test env, should be False
    assert result is False


async def test_runbook_document() -> None:
    from app.resilience.runbooks import RB001_PostgresDown
    rb = RB001_PostgresDown()
    doc = rb.document()
    assert "RB-001" in doc


async def test_runbook_default_remediate_returns_false() -> None:
    from app.resilience.runbooks import RB010_SSLExpiry
    rb = RB010_SSLExpiry()
    assert await rb.remediate() is False


async def test_runbook_default_verify() -> None:
    from app.resilience.runbooks import RB010_SSLExpiry
    rb = RB010_SSLExpiry()
    # detect() retourne False (placeholder) -> verify() True
    assert await rb.verify() is True
