"""Phase 3 - Integration test automation workflows E2E.

Scenarios :
  1. Pause + trigger + resume un schedule -> verif BDD + workflow_executions
  2. DLQ push DB + process -> verif resolution
  3. Event handler chain: on_git_commit_detected -> 3 tasks chainees
  4. Metrics agregation : fire task + check metrics endpoint
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client(pool):
    async with AsyncClient(transport=ASGITransport(app=app),
                            base_url="http://test") as ac:
        yield ac


async def test_integration_pause_resume_audit(client: AsyncClient,
                                                 pool) -> None:
    """Pause a schedule -> verify DB enabled=FALSE -> resume -> enabled=TRUE."""
    target = "task_innovation_scout"
    # baseline
    async with pool.acquire() as conn:
        initial = await conn.fetchval(
            "SELECT enabled FROM workflow_schedules WHERE task_name = $1",
            target,
        )
    # pause
    r = await client.post(f"/api/v1/workflows/pause/{target}")
    assert r.status_code == 200
    async with pool.acquire() as conn:
        enabled = await conn.fetchval(
            "SELECT enabled FROM workflow_schedules WHERE task_name = $1",
            target,
        )
        paused_at = await conn.fetchval(
            "SELECT paused_at FROM workflow_schedules WHERE task_name = $1",
            target,
        )
    assert enabled is False
    assert paused_at is not None
    # resume
    r = await client.post(f"/api/v1/workflows/resume/{target}")
    assert r.status_code == 200
    async with pool.acquire() as conn:
        enabled_after = await conn.fetchval(
            "SELECT enabled FROM workflow_schedules WHERE task_name = $1",
            target,
        )
    assert enabled_after is True


async def test_integration_task_meta_optimizer_updates_metrics(pool) -> None:
    """Fire a real task -> check workflow_executions + workflow_metrics."""
    from app.workers.tasks import task_meta_optimizer
    out = await task_meta_optimizer({})
    assert out["status"] == "succeeded"
    async with pool.acquire() as conn:
        exec_row = await conn.fetchrow(
            "SELECT status, duration_ms FROM workflow_executions "
            "WHERE run_id = $1::uuid", out["run_id"],
        )
        metric_row = await conn.fetchrow(
            "SELECT success_count FROM workflow_metrics "
            "WHERE task_name = 'task_meta_optimizer' AND day = CURRENT_DATE",
        )
    assert exec_row["status"] == "succeeded"
    assert exec_row["duration_ms"] >= 0
    assert int(metric_row["success_count"]) >= 1


async def test_integration_event_git_commit_chain(pool) -> None:
    """Event handler delivers chained tasks from event_triggers seeds."""
    from app.workers.event_workflows import on_git_commit_detected
    out = await on_git_commit_detected(
        {}, commit_sha="deadbeef", branch="test-branch",
    )
    assert out["status"] == "succeeded"
    chained = out["result"]["chained_tasks"]
    # Seeds: task_run_tests_impacted, task_lint_check, task_security_diff_scan
    expected_names = {
        "task_run_tests_impacted", "task_lint_check", "task_security_diff_scan",
    }
    assert set(chained) == expected_names


async def test_integration_dlq_push_and_process_full_cycle(pool) -> None:
    """DLQ push -> process -> resolved flag persists."""
    from app.workers.event_workflows import (
        push_to_dlq_db,
        task_dead_letter_processor,
    )
    dlq_id = await push_to_dlq_db(
        task_name="task_integration_dlq_probe",
        args={"foo": "bar"},
        last_error="integration test synthetic failure",
        tries=3,
    )
    assert dlq_id is not None
    # process
    out = await task_dead_letter_processor({})
    assert out["status"] == "succeeded"
    assert out["result"]["processed"] >= 1
    # verify resolution applied
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT resolution FROM dead_letter_queue WHERE id = $1", dlq_id,
        )
    assert "dlq_processor_ack" in (row["resolution"] or "")


async def test_integration_metrics_endpoint_exposes_counts(
    client: AsyncClient, pool,
) -> None:
    """Fire 2 tasks -> check metrics endpoint shows them."""
    from app.workers.tasks import task_drift_detection
    await task_drift_detection({})
    await task_drift_detection({})
    r = await client.get("/api/v1/workflows/metrics?days=1")
    assert r.status_code == 200
    d = r.json()
    tasks_in_report = {t["task_name"] for t in d["per_task"]}
    assert "task_drift_detection" in tasks_in_report


async def test_integration_history_pagination(
    client: AsyncClient, pool,
) -> None:
    """History endpoint respects limit."""
    r = await client.get("/api/v1/workflows/history?limit=3")
    assert r.status_code == 200
    d = r.json()
    assert len(d["runs"]) <= 3


async def test_integration_failures_endpoint(
    client: AsyncClient, pool,
) -> None:
    """Failures endpoint aggregates workflow_executions + dlq."""
    r = await client.get("/api/v1/workflows/failures?limit=5")
    assert r.status_code == 200
    d = r.json()
    assert "failures" in d
    assert "dlq" in d
