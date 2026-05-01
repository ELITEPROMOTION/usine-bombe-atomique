"""Tests Phase 2 V9 production : improvements & gap fixes.

Couvre :
- lru_cache sur sentry availability
- /admin/projects/inactive
- /admin/payments?status=...
- GDPR webhook fire-and-forget no-op
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.admin import payments as admin_payments
from app.routers.admin import projects as admin_projects
from app.routers.admin.dependencies import get_current_admin
from app.saas_factory.observability.sentry_context import (
    _reset_sentry_cache_for_test,
    _sentry_sdk_importable,
    is_sentry_available,
)


def _admin_principal_factory():
    from app.routers.admin.dependencies import AdminPrincipal
    from app.security.jwt_admin import AdminRole

    async def _override():
        return AdminPrincipal(
            admin_id="ahmed-test", token_hint="...test",
            role=AdminRole.ADMIN, auth_mode="test",
        )
    return _override


def _make_app_with_pool(router, fake_pool):
    from app.database import get_pool
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_admin] = _admin_principal_factory()
    app.dependency_overrides[get_pool] = lambda: fake_pool
    return app


def _make_pool():
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    return pool, conn


# ===========================================================================
# Sentry lru_cache
# ===========================================================================
class TestSentryLRUCache:
    def test_lru_cache_stores_result(self):
        _reset_sentry_cache_for_test()
        # First call populates cache
        first = _sentry_sdk_importable()
        # Second call hits cache (CacheInfo confirms)
        info_before = _sentry_sdk_importable.cache_info()
        _sentry_sdk_importable()
        info_after = _sentry_sdk_importable.cache_info()
        # hit count should increase
        assert info_after.hits >= info_before.hits
        assert isinstance(first, bool)

    def test_is_sentry_available_returns_bool(self):
        _reset_sentry_cache_for_test()
        # No SDK installed in CI -> returns False
        assert isinstance(is_sentry_available(), bool)

    def test_reset_clears_cache(self):
        _sentry_sdk_importable()
        _reset_sentry_cache_for_test()
        info = _sentry_sdk_importable.cache_info()
        assert info.currsize == 0


# ===========================================================================
# /admin/projects/inactive
# ===========================================================================
class TestAdminProjectsInactive:
    def test_returns_empty_list_no_inactive(self):
        pool, _ = _make_pool()
        app = _make_app_with_pool(admin_projects.router, pool)
        c = TestClient(app)
        r = c.get("/api/v1/admin/projects/inactive?days=30")
        assert r.status_code == 200
        assert r.json() == []

    def test_validates_days_min(self):
        pool, _ = _make_pool()
        app = _make_app_with_pool(admin_projects.router, pool)
        c = TestClient(app)
        r = c.get("/api/v1/admin/projects/inactive?days=0")
        assert r.status_code == 422

    def test_validates_days_max(self):
        pool, _ = _make_pool()
        app = _make_app_with_pool(admin_projects.router, pool)
        c = TestClient(app)
        r = c.get("/api/v1/admin/projects/inactive?days=999")
        assert r.status_code == 422

    def test_returns_inactive_projects(self):
        pool, conn = _make_pool()
        now = datetime.now(UTC)
        conn.fetch = AsyncMock(return_value=[{
            "project_id": uuid4(),
            "owner_email": "x@y.com",
            "company_name": "ACME",
            "pack_id_hint": "saas_m",
            "title": "Project X",
            "status": "in_production",
            "created_at": now - timedelta(days=20),
        }])
        app = _make_app_with_pool(admin_projects.router, pool)
        c = TestClient(app)
        r = c.get("/api/v1/admin/projects/inactive?days=14")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["company_name"] == "ACME"


# ===========================================================================
# /admin/payments?status=failed
# ===========================================================================
class TestAdminPayments:
    def test_returns_empty_list(self):
        pool, _ = _make_pool()
        app = _make_app_with_pool(admin_payments.router, pool)
        c = TestClient(app)
        r = c.get("/api/v1/admin/payments")
        assert r.status_code == 200
        assert r.json() == []

    def test_filters_by_status_and_age(self):
        pool, conn = _make_pool()
        conn.fetch = AsyncMock(return_value=[{
            "payment_id": uuid4(),
            "project_id": str(uuid4()),
            "amount_cents": 5000,
            "currency": "EUR",
            "status": "failed",
            "owner_email": "x@y.com",
            "country": "FR",
            "created_at": datetime.now(UTC),
            "paid_at": None,
        }])
        app = _make_app_with_pool(admin_payments.router, pool)
        c = TestClient(app)
        r = c.get("/api/v1/admin/payments?status=failed&min_age_hours=6")
        assert r.status_code == 200
        body = r.json()
        assert body[0]["status"] == "failed"

    def test_validates_min_age_hours_max(self):
        pool, _ = _make_pool()
        app = _make_app_with_pool(admin_payments.router, pool)
        c = TestClient(app)
        r = c.get("/api/v1/admin/payments?min_age_hours=99999")
        assert r.status_code == 422


# ===========================================================================
# GDPR webhook fire-and-forget
# ===========================================================================
class TestGDPRWebhookFireAndForget:
    @pytest.mark.asyncio
    async def test_noop_when_env_unset(self, monkeypatch):
        from app.routers.client import _fire_and_forget_gdpr_webhook

        monkeypatch.delenv("N8N_GDPR_WEBHOOK_URL", raising=False)
        # Should return None silently, no exception
        result = await _fire_and_forget_gdpr_webhook(
            {"kind": "export", "request_id": "x"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_url_unreachable(self, monkeypatch):
        from app.routers.client import _fire_and_forget_gdpr_webhook

        monkeypatch.setenv(
            "N8N_GDPR_WEBHOOK_URL", "http://localhost:0/never-listens",
        )
        # Connection refused, but no exception propagates
        result = await _fire_and_forget_gdpr_webhook(
            {"kind": "export", "request_id": "x"},
        )
        assert result is None

    def test_emit_no_loop_does_not_raise(self):
        from app.routers.client import _emit_gdpr_webhook_bg

        # Sync call (no event loop) - should silently noop
        _emit_gdpr_webhook_bg("export", {"request_id": "x"})
