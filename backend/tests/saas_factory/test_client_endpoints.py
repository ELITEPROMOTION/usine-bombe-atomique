"""Tests Phase 9M-bis — endpoints `/client/*` (services + integration)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.saas_factory.client_area import (
    ClientDashboardService,
    ClientPaymentsService,
    ClientProfileService,
)
from app.saas_factory.client_area._milestones import (
    derive_milestones,
    derive_next_milestone,
)
from app.saas_factory.client_area._status_mapping import (
    derive_progress_pct,
    derive_ui_status,
)
from app.saas_factory.client_area.dashboard_service import (
    ProjectNotFoundError,
)


def _make_pool(side_effects=None):
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    if side_effects is not None:
        conn.fetchrow = AsyncMock(side_effect=side_effects)
    else:
        conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    return pool, conn


# ===========================================================================
# Mappings
# ===========================================================================
class TestStatusMapping:
    def test_derive_ui_status_known(self):
        assert derive_ui_status("submitted") == "discovery"
        assert derive_ui_status("in_production") == "in_build"
        assert derive_ui_status("delivered") == "delivered"

    def test_derive_ui_status_unknown(self):
        assert derive_ui_status("???") == "discovery"

    def test_progress_pct_increases_along_status(self):
        assert derive_progress_pct("submitted") == 5
        assert derive_progress_pct("in_production") == 65
        assert derive_progress_pct("delivered") == 95

    def test_progress_pct_unknown_zero(self):
        assert derive_progress_pct("???") == 0


class TestMilestones:
    def test_5_milestones_generated(self):
        pid = uuid4()
        items = derive_milestones(
            pid, "submitted", datetime.now(UTC),
        )
        assert len(items) == 5
        assert items[0]["label"] == "Qualification"

    def test_milestone_status_tracks_project(self):
        pid = uuid4()
        items = derive_milestones(pid, "delivered", datetime.now(UTC))
        # 4/5 done, last (m-delivery) in_progress
        statuses = [m["status"] for m in items]
        assert statuses[0:4] == ["done"] * 4
        assert statuses[4] == "in_progress"

    def test_next_milestone_for_in_production(self):
        out = derive_next_milestone("in_production", datetime.now(UTC))
        assert out is not None
        label, _ = out
        assert label == "Build interne"

    def test_next_milestone_after_archived(self):
        # tous done -> None
        assert derive_next_milestone("archived", datetime.now(UTC)) is None


# ===========================================================================
# ClientDashboardService
# ===========================================================================
class TestClientDashboardService:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        pool, _ = _make_pool([None])
        svc = ClientDashboardService(pool)
        with pytest.raises(ProjectNotFoundError):
            await svc.get_project(uuid4())

    @pytest.mark.asyncio
    async def test_get_project_aggregates_fields(self):
        pid = uuid4()
        created = datetime.now(UTC) - timedelta(days=5)
        pool, _ = _make_pool([{
            "project_id": pid,
            "owner_email": "a@b.com",
            "company_name": "ACME",
            "pack_id_hint": "saas_m",
            "status": "in_production",
            "created_at": created,
            "updated_at": created + timedelta(days=1),
        }])
        svc = ClientDashboardService(pool)
        out = await svc.get_project(pid)
        assert out.project_id == pid
        assert out.pack_name == "SaaS Studio M"
        assert out.status == "in_build"
        assert out.progress_pct == 65
        assert out.estimated_delivery_at == created + timedelta(days=38)
        assert out.next_milestone == "Build interne"

    @pytest.mark.asyncio
    async def test_unknown_pack_id_falls_back(self):
        pool, _ = _make_pool([{
            "project_id": uuid4(),
            "owner_email": "a@b.com",
            "company_name": "X",
            "pack_id_hint": "very_special",
            "status": "submitted",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }])
        svc = ClientDashboardService(pool)
        out = await svc.get_project(uuid4())
        assert out.pack_name == "Very Special"

    @pytest.mark.asyncio
    async def test_list_milestones_uses_status(self):
        pool, _ = _make_pool([{
            "status": "in_production",
            "created_at": datetime.now(UTC) - timedelta(days=10),
        }])
        svc = ClientDashboardService(pool)
        items = await svc.list_milestones(uuid4())
        assert len(items) == 5
        labels = [m.label for m in items]
        assert "Qualification" in labels and "Livraison" in labels

    @pytest.mark.asyncio
    async def test_list_milestones_404(self):
        pool, _ = _make_pool([None])
        svc = ClientDashboardService(pool)
        with pytest.raises(ProjectNotFoundError):
            await svc.list_milestones(uuid4())

    @pytest.mark.asyncio
    async def test_list_activity_invalid_limit(self):
        pool, _ = _make_pool()
        svc = ClientDashboardService(pool)
        with pytest.raises(ValueError, match="limit"):
            await svc.list_activity(uuid4(), limit=0)
        with pytest.raises(ValueError, match="limit"):
            await svc.list_activity(uuid4(), limit=200)

    @pytest.mark.asyncio
    async def test_list_activity_maps_action_to_kind(self):
        pid = uuid4()
        pool, conn = _make_pool()
        conn.fetch = AsyncMock(return_value=[
            {
                "event_id": uuid4(),
                "action": "payment.succeeded",
                "created_at": datetime.now(UTC),
                "payload_json": '{"title": "Paiement OK"}',
            },
            {
                "event_id": uuid4(),
                "action": "deliverable.released",
                "created_at": datetime.now(UTC),
                "payload_json": {"title": "Maquette livree", "detail": "v2"},
            },
            {
                "event_id": uuid4(),
                "action": "unknown.event",
                "created_at": datetime.now(UTC),
                "payload_json": None,
            },
        ])
        svc = ClientDashboardService(pool)
        out = await svc.list_activity(pid, limit=3)
        assert len(out) == 3
        assert out[0].kind == "payment"
        assert out[0].title == "Paiement OK"
        assert out[1].kind == "deliverable"
        assert out[1].detail == "v2"
        assert out[2].kind == "comms"   # fallback
        assert out[2].detail is None


# ===========================================================================
# ClientPaymentsService
# ===========================================================================
class TestClientPaymentsService:
    @pytest.mark.asyncio
    async def test_list_invoices_maps_status(self):
        pool, conn = _make_pool()
        now = datetime.now(UTC)
        conn.fetch = AsyncMock(return_value=[
            {
                "invoice_id": uuid4(),
                "invoice_number": "INV-2026-001",
                "gross_amount_cents": 12000,
                "currency": "EUR",
                "issued_at": now,
                "payment_status": "succeeded",
                "paid_at": now,
            },
            {
                "invoice_id": uuid4(),
                "invoice_number": "INV-2026-002",
                "gross_amount_cents": 5000,
                "currency": "EUR",
                "issued_at": now,
                "payment_status": "pending",
                "paid_at": None,
            },
            {
                "invoice_id": uuid4(),
                "invoice_number": "INV-2026-003",
                "gross_amount_cents": 8000,
                "currency": "EUR",
                "issued_at": now,
                "payment_status": "refunded",
                "paid_at": now - timedelta(days=2),
            },
        ])
        svc = ClientPaymentsService(pool)
        out = await svc.list_invoices(uuid4())
        statuses = [i.status for i in out]
        assert statuses == ["paid", "issued", "refunded"]
        assert out[0].pdf_token == str(out[0].invoice_id)

    @pytest.mark.asyncio
    async def test_list_invoices_empty(self):
        pool, conn = _make_pool()
        conn.fetch = AsyncMock(return_value=[])
        svc = ClientPaymentsService(pool)
        assert await svc.list_invoices(uuid4()) == []

    @pytest.mark.asyncio
    async def test_list_handoffs_cta_label(self):
        pool, conn = _make_pool()
        now = datetime.now(UTC)
        conn.fetch = AsyncMock(return_value=[
            {
                "handoff_id": uuid4(),
                "action_type": "payment_confirm",
                "state": "requested",
                "title": "Confirmer le paiement",
                "body": "Cliquez ici pour valider",
                "cta_url": "/x/y",
                "expires_at": now + timedelta(days=1),
                "created_at": now,
            },
            {
                "handoff_id": uuid4(),
                "action_type": "review_approve",
                "state": "notified",
                "title": "Revue UI",
                "body": "Approbation requise",
                "cta_url": "/r/1",
                "expires_at": now + timedelta(days=2),
                "created_at": now,
            },
            {
                "handoff_id": uuid4(),
                "action_type": "unknown_action",
                "state": "requested",
                "title": "Action mystere",
                "body": "...",
                "cta_url": "/?x",
                "expires_at": now + timedelta(days=3),
                "created_at": now,
            },
        ])
        svc = ClientPaymentsService(pool)
        out = await svc.list_handoffs(uuid4())
        assert out[0].cta_label == "Confirmer le paiement"
        assert out[1].cta_label == "Ouvrir la revue"
        assert out[2].cta_label == "Voir l'action"


# ===========================================================================
# ClientProfileService
# ===========================================================================
class TestClientProfileService:
    @pytest.mark.asyncio
    async def test_get_profile_aggregates_consents(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value={
            "owner_email": "client@x.com",
            "company_name": "X Corp",
            "locale": "fr",
            "created_at": datetime.now(UTC),
        })
        conn.fetch = AsyncMock(return_value=[
            {"scope": "marketing_opt_in", "revoked_at": None},
            {"scope": "cookie_analytics", "revoked_at": datetime.now(UTC)},
        ])
        svc = ClientProfileService(pool)
        out = await svc.get_profile(uuid4())
        assert out.owner_email == "client@x.com"
        assert out.consent_marketing is True
        assert out.consent_analytics is False

    @pytest.mark.asyncio
    async def test_get_profile_404(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        svc = ClientProfileService(pool)
        with pytest.raises(ProjectNotFoundError):
            await svc.get_profile(uuid4())

    @pytest.mark.asyncio
    async def test_request_export_404(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        svc = ClientProfileService(pool)
        with pytest.raises(ProjectNotFoundError):
            await svc.request_export(uuid4(), requester_email="x@y.com")

    @pytest.mark.asyncio
    async def test_request_export_inserts(self):
        pool, conn = _make_pool()
        new_request_id = uuid4()
        conn.fetchrow = AsyncMock(side_effect=[
            {"_": 1},                       # project exists
            {"request_id": new_request_id}, # insert
        ])
        svc = ClientProfileService(pool)
        out = await svc.request_export(uuid4(), requester_email="x@y.com")
        assert out["request_id"] == str(new_request_id)


# ===========================================================================
# Endpoints integration (auth + routes)
# ===========================================================================
class TestEndpointsAuth:
    @pytest.fixture
    def client_app(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.routers import client as client_router

        monkeypatch.setenv("JWT_CLIENT_SECRET", "x" * 40)

        app = FastAPI()
        app.include_router(client_router.router, prefix="/api/v1")
        return TestClient(app)

    def test_no_auth_returns_401(self, client_app):
        r = client_app.get("/api/v1/client/project")
        assert r.status_code == 401

    def test_garbage_bearer_returns_403(self, client_app):
        r = client_app.get(
            "/api/v1/client/project",
            headers={"Authorization": "Bearer not.a.token"},
        )
        assert r.status_code == 403

    def test_no_secret_returns_503(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.routers import client as client_router

        monkeypatch.delenv("JWT_CLIENT_SECRET", raising=False)
        app = FastAPI()
        app.include_router(client_router.router, prefix="/api/v1")
        c = TestClient(app)
        r = c.get(
            "/api/v1/client/project",
            headers={"Authorization": "Bearer xx"},
        )
        assert r.status_code == 503

    def test_deliverables_returns_empty_list(self, client_app):
        from app.security.jwt_client import create_client_token

        token = create_client_token(
            owner_email="x@y.com", project_id=uuid4(),
        )
        r = client_app.get(
            "/api/v1/client/deliverables",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json() == []
