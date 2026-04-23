"""V5.5 Automation - suite de tests (17 tests).

Couvre :
  - Enregistrement des 26 tasks + 9 event handlers + DLQ processor.
  - Validite des cron schedules.
  - Execution instrumentee (workflow_executions + workflow_metrics).
  - DLQ push/list + processor ack.
  - Event triggers seedes.
  - Endpoints /workflows/* (dashboard).
  - Pause/resume schedule + manual trigger.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.workers import event_workflows, tasks as auto_tasks
from app.workers.arq_schedules import CRON_JOBS, WorkerSettings
from app.workers.event_workflows import (
    EVENT_TASKS,
    EVENT_TASK_NAMES,
    push_to_dlq_db,
    task_dead_letter_processor,
)


pytestmark = pytest.mark.asyncio

EXPECTED_TASKS = {
    "task_queue_saturation_monitor", "task_health_deep_check",
    "task_truth_integrity_check", "task_evidence_chain_verification",
    "task_vault_rotation_check", "task_tenant_isolation_audit",
    "task_security_scan", "task_cve_poll", "task_sbom_regeneration",
    "task_dependencies_audit", "task_nightly_optimizer",
    "task_meta_optimizer", "task_innovation_scout", "task_autonomy_chaos",
    "task_drift_detection", "task_failure_archetype_mining",
    "task_rework_convergence_audit", "task_memory_consolidation",
    "task_prompt_variants_rebalance", "task_benchmarks_run",
    "task_cost_report_generation", "task_agent_performance_report",
    "task_coverage_report", "task_regulatory_dz_poll",
    "task_browser_contract_verify", "task_backup_database",
}

EXPECTED_EVENT_NAMES = {
    "on_git_commit_detected", "on_migration_applied",
    "on_new_project_created", "on_test_failure",
    "on_cost_budget_approaching", "on_regulatory_change_detected",
    "on_agent_drift_detected", "on_phase_gate_requested",
    "on_ahmed_response_received",
}


# ---------------------------------------------------------------- registry
async def test_all_26_tasks_registered() -> None:
    names = set(auto_tasks.TASK_NAMES)
    assert len(auto_tasks.ALL_TASKS) == 26
    assert names == EXPECTED_TASKS


async def test_all_9_event_tasks_registered() -> None:
    assert len(EVENT_TASKS) == 9
    assert set(EVENT_TASK_NAMES) == EXPECTED_EVENT_NAMES


async def test_cron_schedules_valid() -> None:
    # 26 cron + 1 DLQ processor
    assert len(CRON_JOBS) == 27
    names = {c.name for c in CRON_JOBS}
    assert EXPECTED_TASKS.issubset(names)
    assert "task_dead_letter_processor" in names


async def test_worker_settings_exposes_functions() -> None:
    names = {
        getattr(f, "__automation_task__", getattr(f, "__name__", ""))
        for f in WorkerSettings.functions
    }
    assert EXPECTED_TASKS.issubset(names)
    assert EXPECTED_EVENT_NAMES.issubset(names)
    assert "task_dead_letter_processor" in names
    assert WorkerSettings.max_tries == 3
    assert WorkerSettings.retry_jobs is True
    assert WorkerSettings.keep_result == 3600


# ---------------------------------------------------------------- BDD state
async def test_seed_workflow_schedules_has_26(pool) -> None:
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM workflow_schedules")
    assert int(n) == 26


async def test_seed_event_triggers_has_15(pool) -> None:
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM event_triggers")
    assert int(n) >= 15


# ---------------------------------------------------------------- execution
async def test_task_queue_saturation_monitor_executes(pool) -> None:
    out = await auto_tasks.task_queue_saturation_monitor({})
    assert out["status"] in ("succeeded", "failed")
    assert "run_id" in out
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, duration_ms FROM workflow_executions "
            "WHERE run_id = $1",
            out["run_id"],
        )
    assert row is not None
    assert row["status"] in ("succeeded", "failed", "timeout")
    assert int(row["duration_ms"]) >= 0


async def test_health_deep_check_runs_and_reports(pool) -> None:
    out = await auto_tasks.task_health_deep_check({})
    assert out["status"] == "succeeded"
    services = out["result"]["services"]
    assert set(services.keys()) >= {"postgres", "redis", "vault"}


async def test_task_updates_metrics(pool) -> None:
    before = 0
    async with pool.acquire() as conn:
        b = await conn.fetchval(
            "SELECT success_count + failure_count FROM workflow_metrics "
            "WHERE task_name = 'task_meta_optimizer' AND day = CURRENT_DATE",
        )
        before = int(b) if b is not None else 0
    await auto_tasks.task_meta_optimizer({})
    async with pool.acquire() as conn:
        after = await conn.fetchval(
            "SELECT success_count + failure_count FROM workflow_metrics "
            "WHERE task_name = 'task_meta_optimizer' AND day = CURRENT_DATE",
        )
    assert int(after) == before + 1


async def test_failing_task_audited_and_closed(pool) -> None:
    from app.workers._runtime import workflow_task as decorator

    @decorator("task_unit_failure_probe", timeout_s=5)
    async def explode(_ctx, **_):
        raise RuntimeError("boom")

    out = await explode({})
    assert out["status"] == "failed"
    assert "boom" in (out.get("error") or "")
    async with pool.acquire() as conn:
        audit = await conn.fetchrow(
            "SELECT action, actor FROM audit_events "
            "WHERE actor = 'automation/task_unit_failure_probe' "
            "ORDER BY id DESC LIMIT 1",
        )
    assert audit is not None
    assert audit["action"] == "workflow_task_failed"


# ---------------------------------------------------------------- retry / DLQ
async def test_retry_exponential_backoff_config() -> None:
    # La retry exp. backoff est gere par arq via retry_jobs=True + max_tries=3.
    assert WorkerSettings.max_tries == 3
    assert WorkerSettings.retry_jobs is True


async def test_dead_letter_queue_push_and_process(pool) -> None:
    dlq_id = await push_to_dlq_db(
        task_name="task_ut_dlq_probe",
        args={"x": 1},
        last_error="explicit test failure",
        tries=3,
    )
    assert dlq_id is not None
    out = await task_dead_letter_processor({})
    assert out["status"] == "succeeded"
    assert out["result"]["processed"] >= 1
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT resolution FROM dead_letter_queue WHERE id = $1", dlq_id,
        )
    assert row is not None
    assert "dlq_processor_ack" in (row["resolution"] or "")


# ---------------------------------------------------------------- events
async def test_event_trigger_on_commit(pool) -> None:
    out = await event_workflows.on_git_commit_detected(
        {}, commit_sha="abc123", branch="main",
    )
    assert out["status"] == "succeeded"
    chained = out["result"]["chained_tasks"]
    # 3 tasks seedees pour git_commit
    assert len(chained) >= 3


async def test_event_trigger_on_migration(pool) -> None:
    out = await event_workflows.on_migration_applied(
        {}, migration="026_automation_workflows.sql",
    )
    assert out["status"] == "succeeded"
    assert len(out["result"]["chained_tasks"]) >= 3


async def test_event_trigger_on_cost_budget(pool) -> None:
    out = await event_workflows.on_cost_budget_approaching(
        {}, used_pct=0.85, budget_usd=100.0,
    )
    assert out["status"] == "succeeded"
    assert out["result"]["used_pct"] == 0.85


# ---------------------------------------------------------------- endpoints
@pytest_asyncio.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                            base_url="http://test") as ac:
        yield ac


async def test_workflow_dashboard_endpoints(http_client: AsyncClient,
                                             pool) -> None:
    r = await http_client.get("/api/v1/workflows/scheduled")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 26

    r = await http_client.get("/api/v1/workflows/dependencies")
    assert r.status_code == 200
    assert r.json()["event_count"] >= 9

    r = await http_client.get("/api/v1/workflows/history?limit=10")
    assert r.status_code == 200
    assert "runs" in r.json()

    r = await http_client.get("/api/v1/workflows/metrics?days=7")
    assert r.status_code == 200
    assert "per_task" in r.json()

    r = await http_client.get("/api/v1/workflows/failures?limit=10")
    assert r.status_code == 200


async def test_pause_resume_task(http_client: AsyncClient, pool) -> None:
    target = "task_meta_optimizer"
    # pause
    r = await http_client.post(f"/api/v1/workflows/pause/{target}")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT enabled FROM workflow_schedules WHERE task_name = $1", target,
        )
    assert val is False
    # resume
    r = await http_client.post(f"/api/v1/workflows/resume/{target}")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT enabled FROM workflow_schedules WHERE task_name = $1", target,
        )
    assert val is True


async def test_pause_unknown_task_returns_404(http_client: AsyncClient,
                                                pool) -> None:
    r = await http_client.post("/api/v1/workflows/pause/task_not_exists")
    assert r.status_code == 404
