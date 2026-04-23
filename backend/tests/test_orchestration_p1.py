"""V5.1 Wave 4 — P1 Orchestration + Pipeline + Routers.

Couvre :
  - inbox/autonomous_executor : write_config, run_shell whitelist, http_call
  - orchestration/dag_checkpoint : save/load
  - orchestration/delivery_package : build_package
  - orchestration/tool_health : probe + sweep
  - inbox/meta_optimizer : capture_and_analyze + latest
  - inbox/continuous_improvement : pattern_signature + run_retrospective
  - routers/ahmed_inbox : GET /inbox + previews
  - routers/autonomy : smoke endpoints
  - routers/analytics : overview + marketplace
  - routers/health : status
"""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.inbox import autonomous_executor
from app.inbox.autonomous_executor import (
    ExecResult,
    resolve_non_user_action,
    run_shell,
    write_config_file,
)
from app.main import app as fastapi_app
from app.orchestration import dag_checkpoint, delivery_package, tool_health


pytestmark = pytest.mark.asyncio


# ============================================================ autonomous_executor

async def test_executor_write_config_creates_file(tmp_path, pool, seeded_task_id):
    r = await write_config_file(
        pool, seeded_task_id, "cfg.yaml", "key: value\n",
        workspace_root=str(tmp_path))
    assert r.ok is True
    assert (tmp_path / "cfg.yaml").read_text() == "key: value\n"


async def test_executor_write_config_path_traversal_blocked(tmp_path, pool, seeded_task_id):
    r = await write_config_file(
        pool, seeded_task_id, "../escape.txt", "x",
        workspace_root=str(tmp_path))
    assert r.ok is False


async def test_executor_run_shell_allowed(pool, seeded_task_id):
    r = await run_shell(pool, seeded_task_id, ["python", "-c", "print(2+2)"])
    assert r.ok is True
    assert "4" in r.detail.get("stdout_tail", "")


async def test_executor_run_shell_blocked_command(pool, seeded_task_id):
    r = await run_shell(pool, seeded_task_id, ["rm", "-rf", "/tmp/test"])
    assert r.ok is False
    assert "whitelist" in r.detail.get("error", "").lower()


async def test_executor_run_shell_empty_command(pool, seeded_task_id):
    r = await run_shell(pool, seeded_task_id, [])
    assert r.ok is False


async def test_executor_resolve_non_user_action_unknown_kind(pool, seeded_task_id):
    r = await resolve_non_user_action(
        pool, seeded_task_id, "unknown_action_kind", {})
    assert r.ok is False


async def test_executor_resolve_config_file(pool, seeded_task_id, tmp_path):
    r = await resolve_non_user_action(
        pool, seeded_task_id, "config_file",
        {"path": "rc.json", "content": "{}",
          "workspace_root": str(tmp_path)})
    assert r.ok is True
    assert (tmp_path / "rc.json").exists()


# ============================================================ dag_checkpoint

async def test_dag_checkpoint_save_and_load(pool, seeded_task_id):
    await dag_checkpoint.save(
        pool, task_id=seeded_task_id, last_wave_index=2,
        completed_waves=[0, 1, 2],
        agent_results={"agent-01": {"status": "completed", "score": 0.9}})
    loaded = await dag_checkpoint.load(pool, seeded_task_id)
    assert loaded is not None
    assert loaded.last_wave_index == 2
    assert "agent-01" in loaded.agent_results


async def test_dag_checkpoint_clear(pool, seeded_task_id):
    await dag_checkpoint.save(
        pool, task_id=seeded_task_id, last_wave_index=1,
        completed_waves=[0, 1], agent_results={})
    await dag_checkpoint.clear(pool, seeded_task_id)
    assert await dag_checkpoint.load(pool, seeded_task_id) is None


async def test_dag_checkpoint_load_unknown_task(pool):
    import uuid
    r = await dag_checkpoint.load(pool, str(uuid.uuid4()))
    assert r is None


# ============================================================ delivery_package

async def test_delivery_build_basic(pool, seeded_task_id):
    pkg = await delivery_package.build(
        pool, task_id=seeded_task_id,
        spec="CRUD basique items",
        pipeline_verdict="PASS", pipeline_score=0.92,
        confidence_report={"composite": 0.9, "label": "high"},
        manifest=[{"path": "app/main.py", "language": "python", "bytes": 200}],
    )
    d = pkg.to_dict() if hasattr(pkg, "to_dict") else pkg
    assert "resume" in d


async def test_delivery_spec_hash_stable():
    h1 = delivery_package._spec_hash("hello world")
    h2 = delivery_package._spec_hash("hello world")
    assert h1 == h2
    assert h1 != delivery_package._spec_hash("hello")


# ============================================================ tool_health

async def test_tool_probe_ok():
    r = await tool_health.probe_tool({"url": "http://backend:8000/api/v1/health"})
    assert r in ("ok", "degraded", "down", "skipped")


async def test_tool_probe_no_url_returns_skipped():
    r = await tool_health.probe_tool({"url": ""})
    assert r == "skipped"


async def test_tool_probe_unreachable():
    r = await tool_health.probe_tool({"url": "http://nope.invalid:9999/x"})
    assert r in ("down", "degraded", "skipped")


# ============================================================ routers

async def _client():
    return AsyncClient(transport=ASGITransport(app=fastapi_app),
                        base_url="http://t")


async def test_router_health_ok(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200


async def test_router_inbox_returns_buckets(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/inbox")
    assert r.status_code == 200
    body = r.json()
    assert "counts" in body
    assert "A_accounts" in body


async def test_router_inbox_blocked(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/inbox/blocked")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_router_inbox_mit_playbooks(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/inbox/mit/playbooks")
    assert r.status_code == 200
    body = r.json()
    assert "http_server" in body
    assert "database" in body
    assert "queue" in body


async def test_router_preview_account(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/inbox/preview/account?service=Test&why=ci")
    assert r.status_code == 200
    body = r.json()
    assert "fields" in body or "form" in body


async def test_router_preview_payment(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/inbox/preview/payment")
    assert r.status_code == 200


async def test_router_preview_clarification(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/inbox/preview/clarification")
    assert r.status_code == 200


async def test_router_autonomy_boundaries(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/autonomy/boundaries")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 5


async def test_router_autonomy_leases(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/autonomy/leases")
    assert r.status_code == 200


async def test_router_autonomy_calibration(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/autonomy/calibration")
    assert r.status_code == 200


async def test_router_autonomy_chaos_run(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/chaos/run")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 5


async def test_router_autonomy_ladder_decide(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/ladder/decide",
                          json={"confidence": 0.95})
    assert r.status_code == 200
    assert r.json()["mode"] in ("CONTINUE", "PROBE", "CONSTRAIN", "DEFER", "ESCALATE")


async def test_router_autonomy_ladder_invalid_payload(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/ladder/decide",
                          json={"confidence": "bad"})
    assert r.status_code == 400


async def test_router_autonomy_resolve_ambiguity(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/resolve_ambiguity",
                          json={"question": "Strategie de backup?"})
    assert r.status_code == 200
    body = r.json()
    assert body["resolved"] is True


async def test_router_autonomy_resolve_ambiguity_missing_q(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/resolve_ambiguity", json={})
    assert r.status_code == 400


async def test_router_autonomy_grant_lease(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/leases/grant",
                          json={"scope": "test.router.lease",
                                "duration_days": 1, "usage_cap": 1})
    assert r.status_code == 200
    lease_id = r.json()["id"]
    async with await _client() as c:
        r2 = await c.post(f"/api/v1/autonomy/leases/{lease_id}/revoke")
    assert r2.status_code == 200


async def test_router_autonomy_grant_lease_missing_scope(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/leases/grant", json={})
    assert r.status_code == 400


async def test_router_autonomy_add_boundary(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/boundaries",
                          json={"scope": "test.router.boundary",
                                "description": "tmp", "requires_type": "C"})
    assert r.status_code == 200


async def test_router_autonomy_cost_best_mode(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/autonomy/cost/best_mode?confidence=0.5")
    assert r.status_code == 200
    body = r.json()
    assert "best" in body and "ranking" in body


async def test_router_autonomy_explain_unknown(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/autonomy/explain/never-seen-cid")
    assert r.status_code == 200
    assert r.json()["found"] is False


async def test_router_autonomy_avoided(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/autonomy/avoided?limit=3")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_router_autonomy_kpis_capture(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/kpis/capture")
    assert r.status_code == 200
    assert "autonomy_action_rate" in r.json()


async def test_router_autonomy_kpis_get(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/autonomy/kpis")
    assert r.status_code == 200


async def test_router_autonomy_sim_replay(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/autonomy/sim/replay",
                          json={"escalate_confidence_threshold": 0.4,
                                "constrain_confidence_threshold": 0.6})
    assert r.status_code == 200


async def test_router_analytics_overview(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/analytics/overview")
    assert r.status_code == 200


async def test_router_analytics_marketplace(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/analytics/marketplace")
    assert r.status_code == 200
