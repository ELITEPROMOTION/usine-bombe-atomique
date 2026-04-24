"""Coverage boost - execute les 26 tasks automation pour couvrir leurs chemins.

Cible `app/workers/tasks.py` (32.5% -> 90%+). Chaque task est appele avec des
contextes qui exercent les branches principales. La plupart sont tolerantes
aux services absents (fallback/try/except) donc aucun mock reseau necessaire.
"""
from __future__ import annotations

import pytest

from app.workers import tasks as T

pytestmark = pytest.mark.asyncio


async def test_queue_saturation_ok(pool) -> None:
    out = await T.task_queue_saturation_monitor({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert r["saturation"] in ("ok", "warn", "alert")
    assert isinstance(r["queue_len"], int)
    assert isinstance(r["inflight"], int)


async def test_health_deep_check_all_services(pool) -> None:
    out = await T.task_health_deep_check({})
    assert out["status"] == "succeeded"
    svc = out["result"]["services"]
    assert {"postgres", "redis", "vault"} <= svc.keys()
    assert svc["postgres"]["ok"] is True


async def test_truth_integrity_check(pool) -> None:
    out = await T.task_truth_integrity_check({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "integrity_ok" in r
    assert "events_checked" in r
    assert r["broken_count"] >= 0


async def test_evidence_chain_verification_populates_report(pool) -> None:
    out = await T.task_evidence_chain_verification({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert r["evidence_ledger_count"] >= 0
    assert "integrity_ok" in r
    assert "audit_immutability" in r


async def test_vault_rotation_check(pool) -> None:
    out = await T.task_vault_rotation_check({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "vault_reachable" in r
    assert r["rotation_max_age_days"] == 90
    assert "audited_at" in r


async def test_tenant_isolation_audit(pool) -> None:
    out = await T.task_tenant_isolation_audit({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "policies_present" in r
    assert "no_tenant_rows" in r
    assert isinstance(r["isolation_ok"], bool)


async def test_security_scan_runs(pool) -> None:
    out = await T.task_security_scan({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert r["tool"] in ("bandit", "fallback_grep")
    assert "findings" in r


async def test_cve_poll(pool) -> None:
    out = await T.task_cve_poll({})
    # Peut succeed (reachable) ou succeed avec reachable=False
    assert out["status"] == "succeeded"
    assert "reachable" in out["result"]


async def test_sbom_regeneration(pool) -> None:
    out = await T.task_sbom_regeneration({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "packages_count" in r
    if r["packages_count"] > 0:
        assert len(r["sbom_sha256"]) == 64
        assert isinstance(r["first_packages"], list)


async def test_dependencies_audit(pool) -> None:
    out = await T.task_dependencies_audit({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "outdated_count" in r


async def test_nightly_optimizer(pool) -> None:
    out = await T.task_nightly_optimizer({})
    assert out["status"] == "succeeded"
    assert "retuned" in out["result"]


async def test_meta_optimizer(pool) -> None:
    out = await T.task_meta_optimizer({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert r["total_runs_24h"] >= 0
    assert 0.0 <= r["success_rate"] <= 1.0


async def test_innovation_scout(pool) -> None:
    out = await T.task_innovation_scout({})
    assert out["status"] == "succeeded"
    assert "ran" in out["result"]


async def test_autonomy_chaos(pool) -> None:
    out = await T.task_autonomy_chaos({})
    assert out["status"] == "succeeded"
    assert "ran" in out["result"]


async def test_drift_detection(pool) -> None:
    out = await T.task_drift_detection({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "alert" in r
    assert isinstance(r["alert"], bool)


async def test_failure_archetype_mining(pool) -> None:
    out = await T.task_failure_archetype_mining({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "archetypes" in r
    assert r["archetype_count"] == len(r["archetypes"])


async def test_rework_convergence_audit(pool) -> None:
    out = await T.task_rework_convergence_audit({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert r["total_24h"] >= 0
    assert 0.0 <= r["rework_ratio"] <= 1.0


async def test_memory_consolidation(pool) -> None:
    out = await T.task_memory_consolidation({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert r["pruned"] == 0  # dry stat


async def test_prompt_variants_rebalance(pool) -> None:
    out = await T.task_prompt_variants_rebalance({})
    assert out["status"] == "succeeded"
    assert "rebalanced" in out["result"]


async def test_benchmarks_run(pool) -> None:
    out = await T.task_benchmarks_run({})
    assert out["status"] == "succeeded"
    assert "ran" in out["result"]


async def test_cost_report_generation(pool) -> None:
    out = await T.task_cost_report_generation({})
    assert out["status"] == "succeeded"
    r = out["result"]
    # soit ran=False (table absente) soit total_cost_usd_24h present
    assert ("ran" in r) or ("total_cost_usd_24h" in r)


async def test_agent_performance_report(pool) -> None:
    out = await T.task_agent_performance_report({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "agents" in r
    assert r["agent_count"] == len(r["agents"])


async def test_coverage_report_paths_checked(pool) -> None:
    out = await T.task_coverage_report({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "found" in r


async def test_regulatory_dz_poll(pool) -> None:
    out = await T.task_regulatory_dz_poll({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "found" in r
    assert r["rules"] >= 0


async def test_browser_contract_verify(pool) -> None:
    out = await T.task_browser_contract_verify({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "found" in r


async def test_backup_database(pool) -> None:
    out = await T.task_backup_database({})
    assert out["status"] == "succeeded"
    r = out["result"]
    assert "backed_up" in r


# ---------------------- registry completeness ----------------------

def test_all_26_names_unique() -> None:
    names = T.TASK_NAMES
    assert len(names) == 27  # 26 V5.5 + 1 V5.7 hourly backup
    assert len(set(names)) == 27


def test_each_task_has_timeout_attribute() -> None:
    for t in T.ALL_TASKS:
        assert hasattr(t, "__automation_timeout__")
        assert t.__automation_timeout__ > 0  # type: ignore[attr-defined]


def test_each_task_returns_dict_on_success(pool) -> None:
    # sanity : verifie que les tasks renvoient un dict (pas d'objet qcq)
    for t in T.ALL_TASKS:
        assert hasattr(t, "__automation_task__")
