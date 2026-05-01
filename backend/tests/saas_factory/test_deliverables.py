"""Tests Phase 9P — DeliverableLinkInjector + migration 049 smoke."""
from __future__ import annotations

import pathlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.saas_factory.deliverables.link_injector import (
    DEFAULT_DELIVERABLE_TTL,
    ELIGIBLE_PROJECT_STATUSES,
    DeliverableLinkInjector,
    DeliverableMetadata,
    ProjectNotDeliverableError,
)
from app.saas_factory.direct_links.direct_link_generator import IssuedLink


def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    return pool, conn


def _stub_generator() -> MagicMock:
    """Stub DirectLinkGenerator qui retourne un IssuedLink simule."""
    gen = MagicMock()

    async def _issue(*, action_type, target_id, principal_id=None,
                     metadata=None, ttl=None):
        link_id = uuid4()
        return IssuedLink(
            link_id=link_id,
            token="t" * 32,
            url=f"https://app.uba.studio/deliverables/download?t={link_id}",
            action_type=action_type,
            target_id=target_id,
            expires_at=datetime.now(UTC) + (ttl or timedelta(days=7)),
            single_use=False,
        )

    gen.issue = AsyncMock(side_effect=_issue)
    return gen


# ===========================================================================
# DeliverableMetadata schema
# ===========================================================================
class TestDeliverableMetadata:
    def test_valid(self) -> None:
        d = DeliverableMetadata(name="frontend", kind="web", description="React app")
        assert d.name == "frontend"

    def test_short_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DeliverableMetadata(name="", kind="web")

    def test_long_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DeliverableMetadata(name="x" * 200, kind="web")

    def test_optional_description(self) -> None:
        d = DeliverableMetadata(name="x", kind="web")
        assert d.description == ""


# ===========================================================================
# DeliverableLinkInjector
# ===========================================================================
class TestDeliverableLinkInjector:
    @pytest.mark.asyncio
    async def test_inject_succeeds_for_delivered_project(self) -> None:
        pool, conn = _mock_pool()
        proj_id = uuid4()
        conn.fetchrow.return_value = {
            "project_id": proj_id, "owner_email": "client@example.com",
            "title": "MonSaaS", "status": "delivered",
        }
        gen = _stub_generator()
        injector = DeliverableLinkInjector(pool, gen)

        deliverables = [
            DeliverableMetadata(name="Frontend", kind="web"),
            DeliverableMetadata(name="Admin", kind="web"),
            DeliverableMetadata(name="API", kind="backend"),
        ]
        result = await injector.inject_for_project(
            proj_id, deliverables=deliverables,
        )
        assert len(result) == 3
        for inj, d in zip(result, deliverables, strict=False):
            assert inj.project_id == proj_id
            assert inj.deliverable_name == d.name
            assert "deliverables/download" in inj.url
        # 3 appels generator
        assert gen.issue.await_count == 3
        # Verif que action_type est correct
        first_call = gen.issue.await_args_list[0]
        assert first_call.kwargs["action_type"] == "deliverable_download"
        assert first_call.kwargs["target_id"] == str(proj_id)
        assert first_call.kwargs["principal_id"] == "client@example.com"

    @pytest.mark.asyncio
    async def test_inject_succeeds_for_in_production_project(self) -> None:
        pool, conn = _mock_pool()
        proj_id = uuid4()
        conn.fetchrow.return_value = {
            "project_id": proj_id, "owner_email": "x@y.com",
            "title": "T", "status": "in_production",
        }
        injector = DeliverableLinkInjector(pool, _stub_generator())
        result = await injector.inject_for_project(
            proj_id, deliverables=[DeliverableMetadata(name="x", kind="api")],
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_unknown_project_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        injector = DeliverableLinkInjector(pool, _stub_generator())
        with pytest.raises(ProjectNotDeliverableError, match="introuvable"):
            await injector.inject_for_project(
                uuid4(),
                deliverables=[DeliverableMetadata(name="x", kind="web")],
            )

    @pytest.mark.asyncio
    async def test_invalid_status_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": uuid4(), "owner_email": "x@y.com",
            "title": "T", "status": "submitted",  # pas eligible
        }
        injector = DeliverableLinkInjector(pool, _stub_generator())
        with pytest.raises(ProjectNotDeliverableError, match="status"):
            await injector.inject_for_project(
                uuid4(),
                deliverables=[DeliverableMetadata(name="x", kind="web")],
            )

    @pytest.mark.asyncio
    async def test_empty_deliverables_raises(self) -> None:
        pool, _ = _mock_pool()
        injector = DeliverableLinkInjector(pool, _stub_generator())
        with pytest.raises(ValueError, match="non vide"):
            await injector.inject_for_project(uuid4(), deliverables=[])

    @pytest.mark.asyncio
    async def test_owner_email_override(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": uuid4(), "owner_email": "default@example.com",
            "title": "T", "status": "delivered",
        }
        gen = _stub_generator()
        injector = DeliverableLinkInjector(pool, gen)
        await injector.inject_for_project(
            uuid4(),
            deliverables=[DeliverableMetadata(name="x", kind="web")],
            owner_email_override="custom@example.com",
        )
        # principal_id = override
        assert gen.issue.await_args.kwargs["principal_id"] == "custom@example.com"

    @pytest.mark.asyncio
    async def test_custom_ttl(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": uuid4(), "owner_email": "x@y.com",
            "title": "T", "status": "delivered",
        }
        gen = _stub_generator()
        injector = DeliverableLinkInjector(pool, gen)
        custom_ttl = timedelta(days=30)
        await injector.inject_for_project(
            uuid4(),
            deliverables=[DeliverableMetadata(name="x", kind="web")],
            ttl=custom_ttl,
        )
        # ttl propage au generator
        assert gen.issue.await_args.kwargs["ttl"] == custom_ttl

    @pytest.mark.asyncio
    async def test_metadata_includes_project_and_deliverable_info(self) -> None:
        pool, conn = _mock_pool()
        proj_id = uuid4()
        conn.fetchrow.return_value = {
            "project_id": proj_id, "owner_email": "x@y.com",
            "title": "Mon Super Projet", "status": "delivered",
        }
        gen = _stub_generator()
        injector = DeliverableLinkInjector(pool, gen)
        await injector.inject_for_project(
            proj_id,
            deliverables=[
                DeliverableMetadata(
                    name="Frontend",
                    kind="web",
                    description="Site React production",
                ),
            ],
        )
        meta = gen.issue.await_args.kwargs["metadata"]
        assert meta["project_name"] == "Mon Super Projet"
        assert meta["deliverable_name"] == "Frontend"
        assert meta["deliverable_kind"] == "web"
        assert meta["deliverable_description"] == "Site React production"

    @pytest.mark.asyncio
    async def test_list_active_for_project(self) -> None:
        pool, conn = _mock_pool()
        proj_id = uuid4()
        conn.fetch.return_value = [
            {
                "link_id": uuid4(), "target_id": str(proj_id),
                "principal_id": "x@y.com",
                "expires_at": datetime.now(UTC) + timedelta(days=5),
                "created_at": datetime.now(UTC),
                "metadata_json": {"deliverable_name": "Frontend"},
            },
        ]
        injector = DeliverableLinkInjector(pool, _stub_generator())
        active = await injector.list_active_for_project(proj_id)
        assert len(active) == 1
        # Verifie que le SQL filtre les liens actifs
        sql = conn.fetch.await_args.args[0]
        assert "consumed_at IS NULL" in sql
        assert "revoked_at IS NULL" in sql
        assert "deliverable_download" in sql


# ===========================================================================
# Constants
# ===========================================================================
def test_default_ttl_is_seven_days() -> None:
    assert DEFAULT_DELIVERABLE_TTL == timedelta(days=7)


def test_eligible_statuses() -> None:
    assert "delivered" in ELIGIBLE_PROJECT_STATUSES
    assert "in_production" in ELIGIBLE_PROJECT_STATUSES
    assert "submitted" not in ELIGIBLE_PROJECT_STATUSES


# ===========================================================================
# Migration 049 smoke
# ===========================================================================
class TestMigration049Smoke:
    @pytest.fixture
    def migration_path(self) -> pathlib.Path:
        return (
            pathlib.Path(__file__).parent.parent.parent
            / "migrations" / "versions" / "049_consolidation.sql"
        )

    def test_file_exists(self, migration_path: pathlib.Path) -> None:
        assert migration_path.exists()

    def test_contains_fk_for_all_dependent_tables(
        self, migration_path: pathlib.Path,
    ) -> None:
        content = migration_path.read_text(encoding="utf-8")
        # Toutes les tables qui devaient avoir une FK retroactive (cf. ADR-15)
        expected_fks = (
            "fk_iq_project",         # intelligence_qualifications
            "fk_ip_project",         # intelligence_pricings
            "fk_ia_project",         # intelligence_assemblies
            "fk_pp_project",         # project_progression
            "fk_hr_project",         # handoff_requests
            "fk_aidl_project",       # ai_decisions_log
            "fk_hres_project",       # hostinger_resources
            "fk_payments_project",   # payments
            "fk_backups_project",    # backups
            "fk_ssl_project",        # ssl_certificates
            "fk_invoices_project",   # invoices
        )
        for fk in expected_fks:
            assert fk in content, f"FK manquante : {fk}"

    def test_contains_alter_column_uuid(
        self, migration_path: pathlib.Path,
    ) -> None:
        content = migration_path.read_text(encoding="utf-8")
        # ALTER COLUMN ... TYPE UUID USING ... attendu pour chaque table
        assert content.count("TYPE UUID USING project_id::uuid") >= 11

    def test_contains_handoff_pending_direct_link_id(
        self, migration_path: pathlib.Path,
    ) -> None:
        content = migration_path.read_text(encoding="utf-8")
        assert "ALTER TABLE handoff_pending" in content
        assert "ADD COLUMN IF NOT EXISTS direct_link_id UUID" in content
        assert "REFERENCES direct_links(link_id)" in content

    def test_contains_consolidated_view(
        self, migration_path: pathlib.Path,
    ) -> None:
        content = migration_path.read_text(encoding="utf-8")
        assert "v_project_consolidated_status" in content
        # La vue doit aggreger les metriques cross-tables
        assert "qualifications_count" in content
        assert "paywall_triggered" in content
        assert "open_handoffs" in content
        assert "paid_amount_cents" in content
        assert "total_ai_cost_usd" in content

    def test_contains_orphan_cleanup(
        self, migration_path: pathlib.Path,
    ) -> None:
        content = migration_path.read_text(encoding="utf-8")
        # Au moins 11 DELETE WHERE NOT IN (cleanup orphans)
        assert content.count("DELETE FROM") >= 11
        assert content.count("NOT IN (SELECT project_id::text FROM projects)") >= 11

    def test_contains_seal(self, migration_path: pathlib.Path) -> None:
        content = migration_path.read_text(encoding="utf-8")
        assert "v9_phase9p_consolidation" in content
        assert "evidence_ledger" in content
