"""Tests Phase 9I — Legal framework (documents + consent + GDPR)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.saas_factory.legal.consent_manager import (
    ConsentAlreadyRecordedError,
    ConsentManager,
    ConsentRecord,
    _hash_ip,
    _row_to_record,
)
from app.saas_factory.legal.documents import (
    CURRENT_VERSION,
    LegalDocument,
    load_default_legal_catalog,
)
from app.saas_factory.legal.gdpr_erasure import (
    ERASED_EMAIL_PLACEHOLDER,
    ERASED_TEXT_PLACEHOLDER,
    REVERSAL_WINDOW,
    ErasureNotPermittedError,
    ErasureStatus,
    GDPREraser,
    _parse_update_count,
)
from app.saas_factory.legal.gdpr_export import (
    GDPRExporter,
    GDPRExportPackage,
    _serialize_value,
)
from app.saas_factory.legal.types import (
    SUPPORTED_LEGAL_LOCALES,
    ConsentScope,
    DocumentType,
)


def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    return pool, conn


# ===========================================================================
# Documents catalog
# ===========================================================================
class TestLegalDocumentCatalog:
    def test_default_loads(self) -> None:
        cat = load_default_legal_catalog()
        assert cat.version == CURRENT_VERSION

    def test_each_doc_in_each_locale(self) -> None:
        cat = load_default_legal_catalog()
        # 3 doc types x 4 locales = 12 documents minimum
        for doc_type in (DocumentType.TOS, DocumentType.PRIVACY,
                         DocumentType.COOKIE_POLICY):
            for locale in SUPPORTED_LEGAL_LOCALES:
                assert cat.has(doc_type, locale)
                doc = cat.get(doc_type, locale)
                assert doc.title
                assert doc.body_md
                assert doc.locale == locale
                assert doc.version == CURRENT_VERSION

    def test_checksum_computed(self) -> None:
        cat = load_default_legal_catalog()
        doc = cat.get(DocumentType.TOS, "en")
        assert len(doc.checksum_sha256) == 64
        # Le checksum est deterministe
        doc2 = LegalDocument(
            document_type=DocumentType.TOS, locale="en",
            version=doc.version, title=doc.title, body_md=doc.body_md,
        )
        assert doc.checksum_sha256 == doc2.checksum_sha256

    def test_unknown_locale_falls_back_to_en(self) -> None:
        cat = load_default_legal_catalog()
        doc = cat.get(DocumentType.TOS, "zz")
        assert doc.locale == "en"

    def test_unknown_doc_type_raises(self) -> None:
        cat = load_default_legal_catalog()
        with pytest.raises(KeyError):
            cat.get(DocumentType.DATA_PROCESSING_ADDENDUM, "en")  # pas dans les templates

    def test_supported_locales_constant(self) -> None:
        assert "en" in SUPPORTED_LEGAL_LOCALES
        assert "fr" in SUPPORTED_LEGAL_LOCALES
        assert "ar" in SUPPORTED_LEGAL_LOCALES
        assert "es" in SUPPORTED_LEGAL_LOCALES

    def test_privacy_policy_mentions_gdpr(self) -> None:
        cat = load_default_legal_catalog()
        privacy_en = cat.get(DocumentType.PRIVACY, "en")
        assert "GDPR" in privacy_en.body_md
        privacy_fr = cat.get(DocumentType.PRIVACY, "fr")
        assert "RGPD" in privacy_fr.body_md

    def test_arabic_doc_present(self) -> None:
        cat = load_default_legal_catalog()
        ar = cat.get(DocumentType.TOS, "ar")
        # Au moins un caractere arabe
        assert any("؀" <= c <= "ۿ" for c in ar.body_md)


# ===========================================================================
# Consent manager
# ===========================================================================
class TestConsentManager:
    def test_hash_ip_helper(self) -> None:
        assert _hash_ip(None) is None
        assert _hash_ip("") is None
        h = _hash_ip("1.2.3.4")
        assert h is not None
        assert len(h) == 64

    @pytest.mark.asyncio
    async def test_record_consent_succeeds(self) -> None:
        pool, conn = _mock_pool()
        # 1er fetchrow : check existing -> None (pas de consent existant)
        # 2e fetchrow : INSERT RETURNING
        conn.fetchrow.side_effect = [
            None,
            {"consent_id": uuid4(), "accepted_at": datetime.now(UTC)},
        ]
        cm = ConsentManager(pool)
        rec = await cm.record_consent(
            owner_email="ahmed@example.com",
            scope=ConsentScope.TOS_ACCEPTANCE,
            doc_version="2026-04-30",
            ip="1.2.3.4",
        )
        assert rec.scope is ConsentScope.TOS_ACCEPTANCE
        assert rec.is_active is True
        assert rec.owner_email == "ahmed@example.com"

    @pytest.mark.asyncio
    async def test_record_consent_already_exists_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"consent_id": uuid4()}
        cm = ConsentManager(pool)
        with pytest.raises(ConsentAlreadyRecordedError):
            await cm.record_consent(
                owner_email="x@y.com",
                scope=ConsentScope.MARKETING_OPT_IN,
                doc_version="v1",
            )

    @pytest.mark.asyncio
    async def test_record_invalid_email_raises(self) -> None:
        pool, _ = _mock_pool()
        cm = ConsentManager(pool)
        with pytest.raises(ValueError, match="email"):
            await cm.record_consent(
                owner_email="not-an-email",
                scope=ConsentScope.TOS_ACCEPTANCE,
                doc_version="v1",
            )

    @pytest.mark.asyncio
    async def test_record_empty_version_raises(self) -> None:
        pool, _ = _mock_pool()
        cm = ConsentManager(pool)
        with pytest.raises(ValueError, match="version"):
            await cm.record_consent(
                owner_email="x@y.com",
                scope=ConsentScope.TOS_ACCEPTANCE,
                doc_version="",
            )

    @pytest.mark.asyncio
    async def test_revoke_consent(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"consent_id": uuid4()}
        cm = ConsentManager(pool)
        ok = await cm.revoke_consent(
            owner_email="x@y.com",
            scope=ConsentScope.MARKETING_OPT_IN,
            reason="user changed mind",
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_revoke_consent_not_found(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        cm = ConsentManager(pool)
        ok = await cm.revoke_consent(
            owner_email="x@y.com",
            scope=ConsentScope.MARKETING_OPT_IN,
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_has_active_consent_true(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"?": 1}
        cm = ConsentManager(pool)
        ok = await cm.has_active_consent(
            owner_email="x@y.com", scope=ConsentScope.TOS_ACCEPTANCE,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_has_active_consent_false(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        cm = ConsentManager(pool)
        ok = await cm.has_active_consent(
            owner_email="x@y.com", scope=ConsentScope.MARKETING_OPT_IN,
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_list_consents_active_only(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "consent_id": uuid4(), "owner_email": "x@y.com",
                "scope": "tos_acceptance", "doc_version": "v1",
                "accepted_at": datetime.now(UTC),
                "revoked_at": None, "ip_hash": None,
                "metadata_json": {},
            },
        ]
        cm = ConsentManager(pool)
        result = await cm.list_consents("x@y.com", active_only=True)
        assert len(result) == 1
        assert result[0].is_active

    @pytest.mark.asyncio
    async def test_list_consents_all(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        cm = ConsentManager(pool)
        result = await cm.list_consents("x@y.com")
        assert result == []
        # SQL utilise sans clause WHERE revoked_at
        sql = conn.fetch.await_args.args[0]
        assert "revoked_at IS NULL" not in sql

    def test_row_to_record_parses_str_metadata(self) -> None:
        row = {
            "consent_id": uuid4(),
            "owner_email": "x@y.com",
            "scope": "tos_acceptance",
            "doc_version": "v1",
            "accepted_at": datetime.now(UTC),
            "revoked_at": None,
            "ip_hash": "h",
            "metadata_json": '{"k":"v"}',
        }
        rec = _row_to_record(row)
        assert rec.metadata == {"k": "v"}


# ===========================================================================
# GDPR Exporter (Article 20)
# ===========================================================================
class TestGDPRExporter:
    def test_serialize_value_handles_types(self) -> None:
        from uuid import UUID as UUID_
        u = UUID_("12345678-1234-5678-1234-567812345678")
        assert _serialize_value(u) == str(u)
        now = datetime.now(UTC)
        assert _serialize_value(now) == now.isoformat()
        assert _serialize_value(b"hello") == "hello"
        assert _serialize_value([1, 2]) == [1, 2]
        assert _serialize_value({"a": 1}) == {"a": 1}
        assert _serialize_value(None) is None

    def test_serialize_value_parses_json_string(self) -> None:
        result = _serialize_value('{"k": "v"}')
        assert result == {"k": "v"}

    def test_serialize_value_keeps_non_json_string(self) -> None:
        result = _serialize_value("not json")
        assert result == "not json"

    @pytest.mark.asyncio
    async def test_export_unknown_project_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        exp = GDPRExporter(pool)
        with pytest.raises(LookupError, match="introuvable"):
            await exp.export_for_project(uuid4())

    @pytest.mark.asyncio
    async def test_export_aggregates_all_tables(self) -> None:
        pool, conn = _mock_pool()
        proj_id = uuid4()
        # 1ere fetchrow : SELECT projects -> owner_email
        conn.fetchrow.return_value = {"owner_email": "ahmed@example.com"}
        # fetch retourne [] pour toutes les tables
        conn.fetch.return_value = []
        exp = GDPRExporter(pool)
        package = await exp.export_for_project(proj_id)
        assert isinstance(package, GDPRExportPackage)
        assert package.project_id == proj_id
        assert package.owner_email == "ahmed@example.com"
        # Le package contient les cles attendues
        expected_keys = {
            "project", "onboarding_sessions", "qualifications",
            "pricings", "assemblies", "progression",
            "handoff_requests", "payments", "invoices",
            "hostinger_resources", "ssl_certificates", "backups",
            "ai_decisions_summary", "consents",
        }
        assert expected_keys <= set(package.data)
        assert all(c == 0 for c in package.record_counts.values())

    @pytest.mark.asyncio
    async def test_export_serializes_data(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"owner_email": "x@y.com"}
        proj_uuid = uuid4()
        sample_row = {
            "project_id": proj_uuid,
            "owner_email": "x@y.com",
            "company_name": "X Inc",
            "country": "FR", "locale": "fr", "currency": "EUR",
            "pack_id_hint": "saas_small", "title": "Test",
            "status": "submitted",
            "summary_json": {"a": 1},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "archived_at": None,
        }
        # 1er fetch (project) retourne 1 row, le reste retourne []
        fetch_results = [[sample_row]] + [[]] * 13
        conn.fetch.side_effect = fetch_results
        exp = GDPRExporter(pool)
        package = await exp.export_for_project(proj_uuid)
        assert package.record_counts["project"] == 1
        # UUID serialise en string
        assert package.data["project"][0]["project_id"] == str(proj_uuid)
        assert package.data["project"][0]["company_name"] == "X Inc"

    def test_to_json_format(self) -> None:
        package = GDPRExportPackage(
            project_id=uuid4(),
            owner_email="x@y.com",
            exported_at=datetime.now(UTC),
            data={"project": [{"k": "v"}]},
            record_counts={"project": 1},
        )
        json_str = package.to_json()
        assert "format_version" in json_str
        assert "exported_at" in json_str
        assert '"project": [' in json_str


# ===========================================================================
# GDPR Eraser (Article 17)
# ===========================================================================
class TestGDPREraser:
    def test_constants(self) -> None:
        assert REVERSAL_WINDOW == timedelta(days=30)
        assert "@" in ERASED_EMAIL_PLACEHOLDER
        assert ERASED_TEXT_PLACEHOLDER == "[ERASED]"

    def test_parse_update_count(self) -> None:
        assert _parse_update_count("UPDATE 5") == 5
        assert _parse_update_count("UPDATE 0") == 0
        assert _parse_update_count("not a count") == 0
        assert _parse_update_count("") == 0
        assert _parse_update_count(None) == 0  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_request_erasure_succeeds(self) -> None:
        pool, conn = _mock_pool()
        proj_id = uuid4()
        conn.fetchrow.side_effect = [
            None,                                  # pas d'erasure existante
            {"?": 1},                              # projet existe
            {"request_id": uuid4()},               # INSERT RETURNING
        ]
        eraser = GDPREraser(pool)
        rec = await eraser.request_erasure(
            project_id=proj_id,
            reason="GDPR Art 17 demande user",
            requester_email="user@example.com",
        )
        assert rec.status is ErasureStatus.PENDING
        assert (rec.executable_after - rec.requested_at).days == 30

    @pytest.mark.asyncio
    async def test_request_erasure_already_pending_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"request_id": uuid4()}
        eraser = GDPREraser(pool)
        with pytest.raises(ErasureNotPermittedError, match="deja"):
            await eraser.request_erasure(
                project_id=uuid4(), reason="duplicate",
            )

    @pytest.mark.asyncio
    async def test_request_erasure_unknown_project_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [
            None,                # no existing erasure
            None,                # project not found
        ]
        eraser = GDPREraser(pool)
        with pytest.raises(LookupError):
            await eraser.request_erasure(
                project_id=uuid4(), reason="r",
            )

    @pytest.mark.asyncio
    async def test_request_erasure_empty_reason_raises(self) -> None:
        pool, _ = _mock_pool()
        eraser = GDPREraser(pool)
        with pytest.raises(ValueError, match="reason"):
            await eraser.request_erasure(
                project_id=uuid4(), reason="   ",
            )

    @pytest.mark.asyncio
    async def test_cancel_erasure(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"request_id": uuid4()}
        eraser = GDPREraser(pool)
        ok = await eraser.cancel_erasure(uuid4())
        assert ok is True

    @pytest.mark.asyncio
    async def test_cancel_erasure_not_pending(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        eraser = GDPREraser(pool)
        ok = await eraser.cancel_erasure(uuid4())
        assert ok is False

    @pytest.mark.asyncio
    async def test_execute_erasure_force_anonymises_columns(self) -> None:
        pool, conn = _mock_pool()
        proj_id = uuid4()
        # 1er fetchrow : SELECT request FOR UPDATE
        conn.fetchrow.return_value = {
            "project_id": proj_id,
            "executable_after": datetime.now(UTC) + timedelta(days=30),
            "status": "pending",
        }
        # execute renvoie 'UPDATE N' pour chaque table
        conn.execute.side_effect = [
            "UPDATE 1",   # projects
            "UPDATE 1",   # payments
            "UPDATE 2",   # invoices
            "UPDATE 1",   # handoff_requests
            "UPDATE 1",   # onboarding_sessions
            "UPDATE 1",   # final mark executed
        ]
        eraser = GDPREraser(pool)
        counts = await eraser.execute_erasure(uuid4(), force=True)
        assert counts["projects"] == 1
        assert counts["invoices"] == 2
        # Verif que les UPDATEs utilisent les placeholders d'anonymisation
        sql_args = [c.args for c in conn.execute.await_args_list]
        # 1er UPDATE projects : args contient ERASED_EMAIL et ERASED_TEXT
        first_update = sql_args[0]
        assert ERASED_EMAIL_PLACEHOLDER in first_update
        assert ERASED_TEXT_PLACEHOLDER in first_update

    @pytest.mark.asyncio
    async def test_execute_erasure_blocked_when_window_not_elapsed(
        self,
    ) -> None:
        pool, conn = _mock_pool()
        future = datetime.now(UTC) + timedelta(days=10)
        conn.fetchrow.return_value = {
            "project_id": uuid4(),
            "executable_after": future,
            "status": "pending",
        }
        eraser = GDPREraser(pool)
        with pytest.raises(ErasureNotPermittedError, match="executable_after"):
            await eraser.execute_erasure(uuid4(), force=False)

    @pytest.mark.asyncio
    async def test_execute_erasure_unknown_request_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        eraser = GDPREraser(pool)
        with pytest.raises(LookupError):
            await eraser.execute_erasure(uuid4())

    @pytest.mark.asyncio
    async def test_execute_erasure_already_done_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": uuid4(),
            "executable_after": datetime.now(UTC) - timedelta(days=1),
            "status": "executed",
        }
        eraser = GDPREraser(pool)
        with pytest.raises(ErasureNotPermittedError, match="status"):
            await eraser.execute_erasure(uuid4())

    @pytest.mark.asyncio
    async def test_get_erasure_returns_record(self) -> None:
        pool, conn = _mock_pool()
        rid = uuid4()
        proj = uuid4()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {
            "request_id": rid,
            "project_id": proj,
            "requested_at": now,
            "executable_after": now + timedelta(days=30),
            "executed_at": None,
            "status": "pending",
            "reason": "test",
            "requester_email": "x@y.com",
        }
        eraser = GDPREraser(pool)
        rec = await eraser.get_erasure(rid)
        assert rec is not None
        assert rec.status is ErasureStatus.PENDING
        assert rec.project_id == proj

    @pytest.mark.asyncio
    async def test_get_erasure_unknown_returns_none(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        eraser = GDPREraser(pool)
        assert await eraser.get_erasure(uuid4()) is None


# ===========================================================================
# ConsentRecord property
# ===========================================================================
def test_consent_record_is_active() -> None:
    rec = ConsentRecord(
        consent_id=uuid4(),
        owner_email="x@y.com",
        scope=ConsentScope.TOS_ACCEPTANCE,
        doc_version="v1",
        accepted_at=datetime.now(UTC),
        revoked_at=None,
        ip_hash=None,
    )
    assert rec.is_active is True
    rec_revoked = ConsentRecord(
        consent_id=uuid4(),
        owner_email="x@y.com",
        scope=ConsentScope.TOS_ACCEPTANCE,
        doc_version="v1",
        accepted_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC),
        ip_hash=None,
    )
    assert rec_revoked.is_active is False


# ===========================================================================
# Migration 050 smoke
# ===========================================================================
class TestMigration050Smoke:
    def test_file_exists_with_expected_clauses(self) -> None:
        import pathlib

        p = (
            pathlib.Path(__file__).parent.parent.parent
            / "migrations" / "versions" / "050_legal_framework.sql"
        )
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS user_consents" in content
        assert "CREATE TABLE IF NOT EXISTS data_export_requests" in content
        assert "CREATE TABLE IF NOT EXISTS data_erasure_requests" in content
        assert "v_gdpr_compliance" in content
        assert "REFERENCES projects" in content   # FK garde
        assert "v9_phase9i_legal_framework" in content
