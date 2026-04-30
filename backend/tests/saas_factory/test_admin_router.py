"""Tests Phase 9N — Dashboard Admin Ahmed (routers /admin/*).

Strategy : minimal FastAPI app par test, dependency_overrides pour
get_pool / get_current_admin / get_admin_audit_logger. Aucun appel reel
DB / Claude / Stripe.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_pool
from app.routers.admin import (
    ai as admin_ai,
)
from app.routers.admin import (
    direct_links as admin_dl,
)
from app.routers.admin import (
    handoffs as admin_handoffs,
)
from app.routers.admin import (
    onboarding as admin_onboarding,
)
from app.routers.admin import (
    projects as admin_projects,
)
from app.routers.admin import (
    setup_wizard as admin_wizard,
)
from app.routers.admin.dependencies import (
    AdminAuditLogger,
    AdminPrincipal,
    get_admin_audit_logger,
    get_current_admin,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    return pool, conn


def _fake_admin() -> AdminPrincipal:
    return AdminPrincipal(admin_id="ahmed", token_hint="...test")


def _fake_auditor() -> MagicMock:
    auditor = MagicMock(spec=AdminAuditLogger)
    auditor.log = AsyncMock(return_value=uuid4())
    return auditor


def _make_app(
    *routers, with_auth: bool = True,
    pool: MagicMock | None = None,
    auditor: MagicMock | None = None,
) -> tuple[FastAPI, MagicMock, MagicMock]:
    app = FastAPI()
    for r in routers:
        app.include_router(r)
    pool_ref = pool or _mock_pool()[0]
    auditor_ref = auditor or _fake_auditor()
    app.dependency_overrides[get_pool] = lambda: pool_ref
    if with_auth:
        app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_admin_audit_logger] = lambda: auditor_ref
    return app, pool_ref, auditor_ref


# ===========================================================================
# Auth dependency
# ===========================================================================
class TestAdminAuth:
    @pytest.fixture(autouse=True)
    def _ensure_token_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Par defaut, on garantit un token connu.
        monkeypatch.setenv("UBA_ADMIN_TOKEN", "secret-test-token")

    def test_no_token_returns_401(self) -> None:
        # Pas de dependency_overrides : on utilise la vraie dependency.
        app = FastAPI()
        app.include_router(admin_ai.router)
        # Override get_pool pour eviter init DB.
        pool, _conn = _mock_pool()
        app.dependency_overrides[get_pool] = lambda: pool
        client = TestClient(app)
        r = client.get("/admin/ai/decisions")
        assert r.status_code == 401

    def test_wrong_token_returns_403(self) -> None:
        app = FastAPI()
        app.include_router(admin_ai.router)
        pool, _conn = _mock_pool()
        app.dependency_overrides[get_pool] = lambda: pool
        client = TestClient(app)
        r = client.get(
            "/admin/ai/decisions",
            headers={"X-Admin-Token": "wrong-token"},
        )
        assert r.status_code == 403

    def test_correct_token_passes_auth(self) -> None:
        app = FastAPI()
        app.include_router(admin_ai.router)
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        app.dependency_overrides[get_pool] = lambda: pool
        client = TestClient(app)
        r = client.get(
            "/admin/ai/decisions",
            headers={"X-Admin-Token": "secret-test-token"},
        )
        assert r.status_code == 200

    def test_env_unset_returns_503(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("UBA_ADMIN_TOKEN", raising=False)
        app = FastAPI()
        app.include_router(admin_ai.router)
        pool, _conn = _mock_pool()
        app.dependency_overrides[get_pool] = lambda: pool
        client = TestClient(app)
        r = client.get(
            "/admin/ai/decisions",
            headers={"X-Admin-Token": "anything"},
        )
        assert r.status_code == 503


# ===========================================================================
# /admin/ai
# ===========================================================================
class TestAdminAi:
    def test_decisions_list_default(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "decision_id": uuid4(), "project_id": "p", "requested_provider": "claude",
                "actual_provider": "claude", "status": "ok", "cost_usd": 0.005,
                "tokens_in": 100, "tokens_out": 200, "latency_ms": 300,
                "fallback_used": False, "retries": 0, "loop_detected": False,
                "created_at": datetime.now(UTC),
            },
        ]
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/decisions?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["status"] == "ok"

    def test_decisions_filtered_by_project(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/decisions?project_id=p1")
        assert r.status_code == 200
        # Le SQL "WHERE project_id = $1" a bien ete utilise
        args = conn.fetch.await_args.args
        assert "WHERE project_id" in args[0]
        assert args[1] == "p1"

    def test_cost_dashboard(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "project_id": "p1", "calls": 5, "total_cost_usd": 0.5,
                "tokens_in": 1000, "tokens_out": 2000,
                "fallbacks": 0, "loops": 0, "errors": 0,
            },
        ]
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/cost-dashboard")
        assert r.status_code == 200
        assert r.json()[0]["project_id"] == "p1"

    def test_cost_by_project_404_when_missing(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/cost-by-project/ghost-project")
        assert r.status_code == 404

    def test_cost_by_project_200_when_present(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": "p", "calls": 3, "total_cost_usd": 0.10,
            "tokens_in": 50, "tokens_out": 100,
            "fallbacks": 0, "loops": 0, "errors": 0,
        }
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/cost-by-project/p")
        assert r.status_code == 200
        assert r.json()["calls"] == 3

    def test_get_router_policy(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "operations_json": {
                "ai_router_claude_pct": 80,
                "ai_router_perplexity_pct": 15,
                "ai_router_manus_pct": 5,
                "ai_router_internal_pct": 0,
            },
        }
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/router-policy")
        assert r.status_code == 200
        data = r.json()
        assert data["weights"]["claude"] == 80
        assert sum(data["weights"].values()) == 100

    def test_get_router_policy_404_when_no_config(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/router-policy")
        assert r.status_code == 404

    def test_get_router_policy_parses_string_json(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "operations_json": (
                '{"ai_router_claude_pct": 70, "ai_router_perplexity_pct": 20,'
                ' "ai_router_manus_pct": 10, "ai_router_internal_pct": 0}'
            ),
        }
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/ai/router-policy")
        assert r.status_code == 200
        assert r.json()["weights"]["perplexity"] == 20

    def test_override_router_policy_success(self) -> None:
        pool, conn = _mock_pool()
        conn.execute.return_value = "UPDATE 1"
        auditor = _fake_auditor()
        app, _, _ = _make_app(admin_ai.router, pool=pool, auditor=auditor)
        client = TestClient(app)
        r = client.post(
            "/admin/ai/router-policy",
            json={
                "weights": {
                    "claude": 70, "perplexity": 20, "manus": 10, "internal": 0,
                },
            },
        )
        assert r.status_code == 200
        # Audit logger appele
        auditor.log.assert_awaited_once()
        kw = auditor.log.await_args.kwargs
        assert kw["action_type"] == "override_router_policy"

    def test_override_router_policy_invalid_sum(self) -> None:
        pool, _conn = _mock_pool()
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            "/admin/ai/router-policy",
            json={"weights": {"claude": 50, "perplexity": 30}},  # =80
        )
        assert r.status_code == 422

    def test_override_router_policy_no_config(self) -> None:
        pool, conn = _mock_pool()
        conn.execute.return_value = "UPDATE 0"
        app, _, _ = _make_app(admin_ai.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            "/admin/ai/router-policy",
            json={
                "weights": {
                    "claude": 100, "perplexity": 0, "manus": 0, "internal": 0,
                },
            },
        )
        assert r.status_code == 404


# ===========================================================================
# /admin/handoffs
# ===========================================================================
class TestAdminHandoffs:
    def test_list_default(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "handoff_id": uuid4(), "project_id": "p",
                "action_type": "kyc_validation", "state": "notified",
                "target_email": "x@y.z", "title": "T",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
            },
        ]
        app, _, _ = _make_app(admin_handoffs.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/handoffs")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_list_filtered_by_state(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        app, _, _ = _make_app(admin_handoffs.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/handoffs?state=escalated")
        assert r.status_code == 200
        # SQL WHERE state = $1 utilise
        sql = conn.fetch.await_args.args[0]
        assert "WHERE state" in sql

    def test_cancel_success(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"handoff_id": uuid4()}
        auditor = _fake_auditor()
        app, _, _ = _make_app(
            admin_handoffs.router, pool=pool, auditor=auditor,
        )
        client = TestClient(app)
        hid = uuid4()
        r = client.post(
            f"/admin/handoffs/{hid}/cancel",
            json={"reason": "user-requested"},
        )
        assert r.status_code == 200
        auditor.log.assert_awaited_once()

    def test_cancel_not_found(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_handoffs.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            f"/admin/handoffs/{uuid4()}/cancel",
            json={"reason": "user-requested"},
        )
        assert r.status_code == 404

    def test_cancel_validates_reason(self) -> None:
        pool, _ = _mock_pool()
        app, _, _ = _make_app(admin_handoffs.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            f"/admin/handoffs/{uuid4()}/cancel",
            json={"reason": ""},   # min_length=1
        )
        assert r.status_code == 422

    def test_escalate_success(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"handoff_id": uuid4()}
        auditor = _fake_auditor()
        app, _, _ = _make_app(
            admin_handoffs.router, pool=pool, auditor=auditor,
        )
        client = TestClient(app)
        r = client.post(
            f"/admin/handoffs/{uuid4()}/escalate",
            json={"reason": "stuck >24h"},
        )
        assert r.status_code == 200

    def test_escalate_not_found(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_handoffs.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            f"/admin/handoffs/{uuid4()}/escalate",
            json={"reason": "stuck"},
        )
        assert r.status_code == 404


# ===========================================================================
# /admin/projects
# ===========================================================================
class TestAdminProjects:
    def test_list(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "project_id": uuid4(), "owner_email": "x@y.z",
                "company_name": "C", "pack_id_hint": "saas_small",
                "title": "T", "status": "submitted",
                "created_at": datetime.now(UTC),
            },
        ]
        app, _, _ = _make_app(admin_projects.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/projects")
        assert r.status_code == 200

    def test_list_filtered_by_status(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        app, _, _ = _make_app(admin_projects.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/projects?status=submitted")
        assert r.status_code == 200
        sql = conn.fetch.await_args.args[0]
        assert "WHERE status" in sql

    def test_status_override_success(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": uuid4(), "status": "in_production",
        }
        auditor = _fake_auditor()
        app, _, _ = _make_app(
            admin_projects.router, pool=pool, auditor=auditor,
        )
        client = TestClient(app)
        r = client.patch(
            f"/admin/projects/{uuid4()}/status",
            json={"new_status": "in_production", "reason": "manual"},
        )
        assert r.status_code == 200
        auditor.log.assert_awaited_once()

    def test_status_override_invalid_status(self) -> None:
        pool, _ = _mock_pool()
        app, _, _ = _make_app(admin_projects.router, pool=pool)
        client = TestClient(app)
        r = client.patch(
            f"/admin/projects/{uuid4()}/status",
            json={"new_status": "ghost_status", "reason": "test"},
        )
        assert r.status_code == 422

    def test_status_override_unknown_project(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_projects.router, pool=pool)
        client = TestClient(app)
        r = client.patch(
            f"/admin/projects/{uuid4()}/status",
            json={"new_status": "delivered", "reason": "test"},
        )
        assert r.status_code == 404


# ===========================================================================
# /admin/direct-links
# ===========================================================================
class TestAdminDirectLinks:
    def test_list_default(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "link_id": uuid4(), "action_type": "kyc_validation",
                "target_id": "h1", "principal_id": None,
                "single_use": True, "consumed_at": None,
                "revoked_at": None,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
            },
        ]
        app, _, _ = _make_app(admin_dl.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/direct-links")
        assert r.status_code == 200

    def test_list_active_only_with_action_type(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        app, _, _ = _make_app(admin_dl.router, pool=pool)
        client = TestClient(app)
        r = client.get(
            "/admin/direct-links?action_type=kyc_validation&only_active=true",
        )
        assert r.status_code == 200
        sql = conn.fetch.await_args.args[0]
        assert "consumed_at IS NULL" in sql

    def test_list_active_only_no_filter(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        app, _, _ = _make_app(admin_dl.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/direct-links?only_active=true")
        assert r.status_code == 200
        sql = conn.fetch.await_args.args[0]
        assert "consumed_at IS NULL" in sql

    def test_revoke_success(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"link_id": uuid4()}
        auditor = _fake_auditor()
        app, _, _ = _make_app(admin_dl.router, pool=pool, auditor=auditor)
        client = TestClient(app)
        r = client.post(
            f"/admin/direct-links/{uuid4()}/revoke?reason=manual+admin",
        )
        assert r.status_code == 200
        auditor.log.assert_awaited_once()

    def test_revoke_already_revoked(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_dl.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            f"/admin/direct-links/{uuid4()}/revoke?reason=test",
        )
        assert r.status_code == 404


# ===========================================================================
# /admin/setup-wizard
# ===========================================================================
class TestAdminSetupWizard:
    def test_start(self) -> None:
        pool, conn = _mock_pool()
        wid = uuid4()
        conn.fetchrow.return_value = {
            "wizard_id": wid, "started_at": datetime.now(UTC),
        }
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.post("/admin/setup-wizard/start")
        assert r.status_code == 201
        assert r.json()["wizard_id"] == str(wid)

    def test_get_state_404(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.get(f"/admin/setup-wizard/{uuid4()}")
        assert r.status_code == 404

    def test_save_step_invalid_step_key(self) -> None:
        pool, _ = _mock_pool()
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            f"/admin/setup-wizard/{uuid4()}/step/ghost_step",
            json={},
        )
        assert r.status_code == 400

    def test_save_step_validation_error(self) -> None:
        pool, conn = _mock_pool()
        # save_step appellera Pydantic.model_validate qui plante avant DB.
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.post(
            f"/admin/setup-wizard/{uuid4()}/step/brand_identity",
            json={},  # incomplet
        )
        assert r.status_code == 422

    def test_commit_not_ready(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "wizard_id": uuid4(),
            "current_step": "pricing_baseline",
            "completed_steps": ["brand_identity"],
            "partial_config_json": {},
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "committed_at": None,
        }
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.post(f"/admin/setup-wizard/{uuid4()}/commit")
        assert r.status_code == 409

    def test_commit_unknown(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.post(f"/admin/setup-wizard/{uuid4()}/commit")
        assert r.status_code == 404

    def test_abandon_success(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            {"session_id": uuid4()},   # pour l'UPDATE -> RETURNING
            # Note : abandon utilise WizardEngine.abandon qui ne fait qu'UPDATE
            # On simplifie en simulant un get_state apres
            {
                "wizard_id": uuid4(),
                "current_step": "brand_identity",
                "completed_steps": [],
                "partial_config_json": {},
                "status": "abandoned",
                "started_at": datetime.now(UTC),
                "committed_at": None,
            },
        ]
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.post(f"/admin/setup-wizard/{uuid4()}/abandon?reason=test")
        assert r.status_code == 200

    def test_abandon_409_when_not_in_progress(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        app, _, _ = _make_app(admin_wizard.router, pool=pool)
        client = TestClient(app)
        r = client.post(f"/admin/setup-wizard/{uuid4()}/abandon")
        assert r.status_code == 409


# ===========================================================================
# /admin/onboarding
# ===========================================================================
class TestAdminOnboarding:
    def test_funnel(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "current_step": "identity", "in_progress": 5,
                "abandoned": 1, "submitted": 0,
            },
            {
                "current_step": "review_submit", "in_progress": 2,
                "abandoned": 0, "submitted": 10,
            },
        ]
        app, _, _ = _make_app(admin_onboarding.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/onboarding/funnel")
        assert r.status_code == 200
        data = r.json()
        assert any(d["current_step"] == "identity" for d in data)

    def test_sessions_list(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "session_id": uuid4(), "current_step": "identity",
                "status": "in_progress", "owner_email": "a@b.com",
                "project_id": None,
                "started_at": datetime.now(UTC),
                "submitted_at": None,
            },
        ]
        app, _, _ = _make_app(admin_onboarding.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/onboarding/sessions")
        assert r.status_code == 200

    def test_sessions_filtered_by_status(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        app, _, _ = _make_app(admin_onboarding.router, pool=pool)
        client = TestClient(app)
        r = client.get("/admin/onboarding/sessions?status=submitted")
        assert r.status_code == 200
        sql = conn.fetch.await_args.args[0]
        assert "WHERE status" in sql


# ===========================================================================
# AdminAuditLogger
# ===========================================================================
class TestAdminAuditLogger:
    @pytest.mark.asyncio
    async def test_log_persists(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        conn.fetchrow.return_value = {"action_id": new_id}
        logger = AdminAuditLogger(pool)
        result = await logger.log(
            admin=AdminPrincipal(admin_id="ahmed", token_hint="...test"),
            action_type="cancel_handoff",
            target_type="handoff",
            target_id="h1",
            payload={"reason": "test"},
        )
        assert result == new_id
        sql = conn.fetchrow.await_args.args[0]
        assert "INSERT INTO admin_actions" in sql

    @pytest.mark.asyncio
    async def test_log_truncates_long_strings(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"action_id": uuid4()}
        logger = AdminAuditLogger(pool)
        await logger.log(
            admin=AdminPrincipal(admin_id="ahmed", token_hint="...x"),
            action_type="x" * 200,        # tronque a 64
            target_type="y" * 200,
            target_id="z" * 200,
        )
        args = conn.fetchrow.await_args.args
        # action_type, target_type, target_id (positions 2, 3, 4)
        assert len(args[2]) <= 64
        assert len(args[3]) <= 64
        assert len(args[4]) <= 120
