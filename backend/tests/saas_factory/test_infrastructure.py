"""Tests Phase 9G — Hostinger Provisioning.

AUCUN appel reel a Hostinger. Tous les tests utilisent `StubHostingerClient`
pre-configure avec des reponses cannees, ou patchent UBA_LIVE_HOSTINGER.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.saas_factory.infrastructure.backup_manager import (
    BackupManager,
    BackupStatus,
)
from app.saas_factory.infrastructure.domain_manager import (
    DomainManager,
    DomainPurchaseRequest,
)
from app.saas_factory.infrastructure.hostinger_client import (
    LIVE_GATE_ENV,
    HostingerAPIError,
    HostingerCallResult,
    HostingerClient,
    HostingerLiveDisabledError,
    PaymentIdRequiredError,
    StubHostingerClient,
    is_live_enabled,
    require_payment_id,
)
from app.saas_factory.infrastructure.ssl_manager import (
    SSLCertStatus,
    SSLManager,
)
from app.saas_factory.infrastructure.types import (
    DomainSearchResult,
    HostingerResourceStatus,
    VPSCreateRequest,
    VPSPlan,
)
from app.saas_factory.infrastructure.vps_provisioner import VPSProvisioner


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
    conn.execute = AsyncMock()
    return pool, conn


# ===========================================================================
# Hostinger client (gate + stub + types)
# ===========================================================================
class TestHostingerClient:
    def test_construction_no_call(self) -> None:
        c = HostingerClient()
        assert c.name == "hostinger"

    def test_is_live_enabled_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(LIVE_GATE_ENV, raising=False)
        assert is_live_enabled() is False

    def test_is_live_enabled_true_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(LIVE_GATE_ENV, "1")
        assert is_live_enabled() is True

    def test_is_live_enabled_other_values_false(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for v in ("0", "yes", "true", "", " "):
            monkeypatch.setenv(LIVE_GATE_ENV, v)
            assert is_live_enabled() is False, f"value={v!r}"

    @pytest.mark.asyncio
    async def test_request_blocks_when_live_disabled(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(LIVE_GATE_ENV, raising=False)
        c = HostingerClient()
        with pytest.raises(HostingerLiveDisabledError):
            await c.request("POST", "/domains/purchase", json_body={"x": 1})

    @pytest.mark.asyncio
    async def test_request_with_require_live_false_does_not_check_gate(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Pour require_live=False, la gate n'est pas verifiee — mais
        # _do_request reste no-cover (on ne fait pas l'appel reseau).
        # On patche _do_request pour eviter d'appeler httpx reellement.
        monkeypatch.delenv(LIVE_GATE_ENV, raising=False)
        c = HostingerClient()
        canned = HostingerCallResult(
            status_code=200, json_body={"ok": True}, latency_ms=5, raw={},
        )
        with patch.object(c, "_do_request", AsyncMock(return_value=canned)):
            result = await c.request(
                "GET", "/health", require_live=False,
            )
        assert result.status_code == 200

    def test_headers_raises_when_no_api_key(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HOSTINGER_API_TOKEN", raising=False)
        c = HostingerClient()
        with pytest.raises(HostingerAPIError, match="HOSTINGER_API_TOKEN"):
            c._headers()

    def test_headers_present_when_api_key_set(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HOSTINGER_API_TOKEN", "test-token")
        c = HostingerClient()
        h = c._headers()
        assert h["Authorization"] == "Bearer test-token"
        assert "User-Agent" in h


class TestRequirePaymentId:
    def test_raises_when_none(self) -> None:
        with pytest.raises(PaymentIdRequiredError) as exc:
            require_payment_id("test_op", None)
        assert exc.value.operation == "test_op"

    def test_raises_when_empty(self) -> None:
        with pytest.raises(PaymentIdRequiredError):
            require_payment_id("op", "")

    def test_raises_when_too_short(self) -> None:
        with pytest.raises(PaymentIdRequiredError):
            require_payment_id("op", "short")

    def test_returns_stripped_when_valid(self) -> None:
        v = require_payment_id("op", "  abcd1234efgh  ")
        assert v == "abcd1234efgh"


class TestStubHostingerClient:
    @pytest.mark.asyncio
    async def test_returns_canned_response(self) -> None:
        client = StubHostingerClient()
        client.set_response(
            "GET", "/domains/check",
            json_body={"available": True, "tld": "fr"},
        )
        result = await client.request(
            "GET", "/domains/check", require_live=True,  # ignore par stub
        )
        assert result.status_code == 200
        assert result.json_body["available"] is True
        assert client.calls == [("GET", "/domains/check", None)]

    @pytest.mark.asyncio
    async def test_unset_response_raises(self) -> None:
        client = StubHostingerClient()
        with pytest.raises(HostingerAPIError, match="cannee"):
            await client.request("GET", "/unknown")


# ===========================================================================
# DTOs / types
# ===========================================================================
class TestTypes:
    def test_domain_search_normalizes_tld(self) -> None:
        r = DomainSearchResult(
            query="x.fr", available=True, tld=".FR",
        )
        assert r.tld == "fr"

    def test_vps_plan_validation(self) -> None:
        VPSPlan(
            plan_id="kvm2", label="KVM 2", cpu_cores=2, ram_gb=4,
            disk_gb=80, monthly_price_eur=10.0,
        )
        with pytest.raises(ValidationError):
            VPSPlan(
                plan_id="x", label="X", cpu_cores=0,    # ge=1
                ram_gb=4, disk_gb=80, monthly_price_eur=10.0,
            )

    def test_vps_create_request_validation(self) -> None:
        VPSCreateRequest(
            project_id="p", plan_id="kvm2", region="eu-west",
            hostname="my-host", payment_id="abcd1234ef",
        )
        # payment_id trop court -> Pydantic min_length=8
        with pytest.raises(ValidationError):
            VPSCreateRequest(
                project_id="p", plan_id="kvm2", region="eu-west",
                hostname="my-host", payment_id="short",
            )

    def test_vps_create_request_invalid_hostname(self) -> None:
        with pytest.raises(ValidationError):
            VPSCreateRequest(
                project_id="p", plan_id="kvm2", region="eu-west",
                hostname="MY HOST",  # majuscules + espace
                payment_id="validpayment123",
            )


# ===========================================================================
# DomainManager
# ===========================================================================
class TestDomainManager:
    @pytest.mark.asyncio
    async def test_search_records_and_returns(self) -> None:
        pool, conn = _mock_pool()
        client = StubHostingerClient()
        client.set_response(
            "GET", "/domains/check",
            json_body={"available": True, "price_eur": 12.99,
                       "suggested": ["alt.fr", "alt.eu"]},
        )
        dm = DomainManager(pool, client)
        result = await dm.search("mybusiness.fr")
        assert result.available is True
        assert result.price_eur == 12.99
        assert result.tld == "fr"
        # INSERT INTO domain_searches
        sql = conn.execute.await_args.args[0]
        assert "INSERT INTO domain_searches" in sql

    @pytest.mark.asyncio
    async def test_search_invalid_query_raises(self) -> None:
        pool, _ = _mock_pool()
        dm = DomainManager(pool, StubHostingerClient())
        with pytest.raises(ValueError, match="TLD"):
            await dm.search("notld")

    @pytest.mark.asyncio
    async def test_check_availability_helper(self) -> None:
        pool, _conn = _mock_pool()
        client = StubHostingerClient()
        client.set_response(
            "GET", "/domains/check",
            json_body={"available": False},
        )
        dm = DomainManager(pool, client)
        assert await dm.check_availability("taken.fr") is False

    @pytest.mark.asyncio
    async def test_purchase_blocks_without_payment_id(self) -> None:
        # Pydantic validation min_length=8 rejette d'abord
        with pytest.raises(ValidationError):
            DomainPurchaseRequest(
                project_id="p", domain="x.fr", years=1,
                payment_id="",
            )

    @pytest.mark.asyncio
    async def test_purchase_succeeds_with_stub(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {
            "resource_id": new_id, "created_at": now,
        }
        client = StubHostingerClient()
        client.set_response(
            "POST", "/domains/purchase",
            json_body={
                "domain_id": "host-123",
                "expires_at": (now + timedelta(days=365)).isoformat(),
            },
        )
        dm = DomainManager(pool, client)
        req = DomainPurchaseRequest(
            project_id="p1", domain="mybusiness.fr", years=1,
            payment_id="payment_id_12345",
        )
        record = await dm.purchase(req)
        assert record.status is HostingerResourceStatus.ACTIVE
        assert record.hostinger_id == "host-123"
        # INSERT + UPDATE
        executes = [c.args[0] for c in conn.execute.await_args_list]
        assert any("INSERT INTO hostinger_audit" in s for s in executes)

    @pytest.mark.asyncio
    async def test_purchase_failure_marks_failed_and_audits(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        conn.fetchrow.return_value = {
            "resource_id": new_id, "created_at": datetime.now(UTC),
        }
        client = StubHostingerClient()
        # Pas de canned response pour purchase -> stub leve HostingerAPIError
        dm = DomainManager(pool, client)
        with pytest.raises(HostingerAPIError):
            await dm.purchase(DomainPurchaseRequest(
                project_id="p", domain="boom.fr", years=1,
                payment_id="payment_id_12345",
            ))
        # _mark_failed + audit purchase_failed appeles
        executes = [c.args[0] for c in conn.execute.await_args_list]
        assert any("status = 'failed'" in s for s in executes)


# ===========================================================================
# VPSProvisioner
# ===========================================================================
class TestVPSProvisioner:
    @pytest.mark.asyncio
    async def test_list_plans(self) -> None:
        pool, _ = _mock_pool()
        client = StubHostingerClient()
        client.set_response(
            "GET", "/vps/plans",
            json_body={"items": [
                {"plan_id": "kvm1", "label": "KVM 1", "cpu_cores": 1,
                 "ram_gb": 2, "disk_gb": 50, "monthly_price_eur": 5.0},
                {"plan_id": "kvm2", "label": "KVM 2", "cpu_cores": 2,
                 "ram_gb": 4, "disk_gb": 80, "monthly_price_eur": 10.0},
            ]},
        )
        provisioner = VPSProvisioner(pool, client)
        plans = await provisioner.list_plans()
        assert len(plans) == 2
        assert plans[0].plan_id == "kvm1"

    @pytest.mark.asyncio
    async def test_create_blocks_invalid_payment_id_via_pydantic(self) -> None:
        # Validation Pydantic min_length=8 rejette avant qu'on arrive au
        # require_payment_id.
        with pytest.raises(ValidationError):
            VPSCreateRequest(
                project_id="p", plan_id="kvm2", region="eu",
                hostname="x", payment_id="bad",
            )

    @pytest.mark.asyncio
    async def test_create_succeeds(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "resource_id": uuid4(),
            "created_at": datetime.now(UTC),
        }
        client = StubHostingerClient()
        client.set_response(
            "POST", "/vps/instances",
            json_body={"instance_id": "vps-42", "ipv4": "1.2.3.4"},
        )
        provisioner = VPSProvisioner(pool, client)
        req = VPSCreateRequest(
            project_id="p1", plan_id="kvm2", region="eu-west",
            hostname="my-host", payment_id="paymentid12345",
            ssh_keys=["ssh-rsa AAA..."],
        )
        instance = await provisioner.create_instance(req)
        assert instance.status is HostingerResourceStatus.ACTIVE
        assert instance.ipv4 == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_create_failure_audits(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "resource_id": uuid4(),
            "created_at": datetime.now(UTC),
        }
        client = StubHostingerClient()  # no canned -> raises
        provisioner = VPSProvisioner(pool, client)
        with pytest.raises(HostingerAPIError):
            await provisioner.create_instance(VPSCreateRequest(
                project_id="p", plan_id="kvm2", region="eu",
                hostname="boom-host", payment_id="paymentid12345",
            ))

    @pytest.mark.asyncio
    async def test_status_returns_local_only_when_no_hostinger_id(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "hostinger_id": None, "status": "provisioning",
        }
        client = StubHostingerClient()
        provisioner = VPSProvisioner(pool, client)
        result = await provisioner.status(uuid4())
        assert result == {"local_status": "provisioning", "remote": None}

    @pytest.mark.asyncio
    async def test_status_unknown_resource_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        provisioner = VPSProvisioner(pool, StubHostingerClient())
        with pytest.raises(LookupError):
            await provisioner.status(uuid4())

    @pytest.mark.asyncio
    async def test_status_with_hostinger_id_calls_remote(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "hostinger_id": "host-1", "status": "active",
        }
        client = StubHostingerClient()
        client.set_response(
            "GET", "/vps/instances/host-1",
            json_body={"state": "running", "ipv4": "1.2.3.4"},
        )
        provisioner = VPSProvisioner(pool, client)
        result = await provisioner.status(uuid4())
        assert result["remote"]["state"] == "running"

    @pytest.mark.asyncio
    async def test_destroy_unknown_returns_false(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        provisioner = VPSProvisioner(pool, StubHostingerClient())
        ok = await provisioner.destroy(uuid4(), reason="test")
        assert ok is False

    @pytest.mark.asyncio
    async def test_destroy_succeeds(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "hostinger_id": "host-x", "status": "active",
        }
        client = StubHostingerClient()
        client.set_response("DELETE", "/vps/instances/host-x",
                            json_body={"deleted": True})
        provisioner = VPSProvisioner(pool, client)
        ok = await provisioner.destroy(uuid4(), reason="cleanup")
        assert ok is True


# ===========================================================================
# SSLManager
# ===========================================================================
class TestSSLManager:
    @pytest.mark.asyncio
    async def test_request_cert_invalid_domain_raises(self) -> None:
        pool, _ = _mock_pool()
        sm = SSLManager(pool, StubHostingerClient())
        with pytest.raises(ValueError):
            await sm.request_cert(project_id="p", domain="invalid")

    @pytest.mark.asyncio
    async def test_request_cert_succeeds(self) -> None:
        pool, conn = _mock_pool()
        cid = uuid4()
        conn.fetchrow.return_value = {"cert_id": cid}
        client = StubHostingerClient()
        now = datetime.now(UTC)
        client.set_response(
            "POST", "/ssl/certificates",
            json_body={
                "issued_at": now.isoformat(),
                "expires_at": (now + timedelta(days=90)).isoformat(),
            },
        )
        sm = SSLManager(pool, client)
        cert = await sm.request_cert(project_id="p", domain="my.example.com")
        assert cert.status is SSLCertStatus.ISSUED
        assert cert.cert_id == cid
        assert cert.domain == "my.example.com"

    @pytest.mark.asyncio
    async def test_renew_unknown_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        sm = SSLManager(pool, StubHostingerClient())
        with pytest.raises(LookupError):
            await sm.renew_cert(uuid4())

    @pytest.mark.asyncio
    async def test_renew_success(self) -> None:
        pool, conn = _mock_pool()
        cid = uuid4()
        conn.fetchrow.return_value = {
            "domain": "x.com", "project_id": "p",
        }
        client = StubHostingerClient()
        future = datetime.now(UTC) + timedelta(days=90)
        client.set_response(
            "POST", f"/ssl/certificates/{cid}/renew",
            json_body={"expires_at": future.isoformat()},
        )
        sm = SSLManager(pool, client)
        cert = await sm.renew_cert(cid)
        assert cert.status is SSLCertStatus.ISSUED
        assert cert.last_renewed_at is not None

    @pytest.mark.asyncio
    async def test_request_cert_failure_marks_failed(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"cert_id": uuid4()}
        client = StubHostingerClient()  # pas de canned -> raise
        sm = SSLManager(pool, client)
        with pytest.raises(HostingerAPIError):
            await sm.request_cert(project_id="p", domain="x.com")
        # _mark_failed appelle UPDATE status='failed'
        executes = [c.args[0] for c in conn.execute.await_args_list]
        assert any("status = 'failed'" in s for s in executes)

    @pytest.mark.asyncio
    async def test_renew_failure_marks_failed(self) -> None:
        pool, conn = _mock_pool()
        cid = uuid4()
        conn.fetchrow.return_value = {"domain": "x.com", "project_id": "p"}
        client = StubHostingerClient()  # pas de canned pour renew -> raise
        sm = SSLManager(pool, client)
        with pytest.raises(HostingerAPIError):
            await sm.renew_cert(cid)
        executes = [c.args[0] for c in conn.execute.await_args_list]
        assert any("status = 'failed'" in s for s in executes)

    @pytest.mark.asyncio
    async def test_list_certs(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "cert_id": uuid4(), "project_id": "p", "domain": "x.com",
                "status": "issued",
                "issued_at": datetime.now(UTC),
                "expires_at": datetime.now(UTC) + timedelta(days=90),
                "last_renewed_at": None,
            },
        ]
        sm = SSLManager(pool, StubHostingerClient())
        certs = await sm.list_certs("p")
        assert len(certs) == 1
        assert certs[0].status is SSLCertStatus.ISSUED


# ===========================================================================
# BackupManager
# ===========================================================================
class TestBackupManager:
    @pytest.mark.asyncio
    async def test_schedule_daily_invalid_retention(self) -> None:
        pool, _ = _mock_pool()
        bm = BackupManager(pool, StubHostingerClient())
        with pytest.raises(ValueError):
            await bm.schedule_daily(
                project_id="p", vps_resource_id=uuid4(), retention_days=0,
            )
        with pytest.raises(ValueError):
            await bm.schedule_daily(
                project_id="p", vps_resource_id=uuid4(), retention_days=400,
            )

    @pytest.mark.asyncio
    async def test_schedule_daily_succeeds(self) -> None:
        pool, conn = _mock_pool()
        client = StubHostingerClient()
        vps_id = uuid4()
        client.set_response(
            "POST", f"/vps/instances/{vps_id}/backup/schedule",
            json_body={"scheduled": True},
        )
        bm = BackupManager(pool, client)
        result = await bm.schedule_daily(
            project_id="p", vps_resource_id=vps_id, retention_days=30,
        )
        assert result["retention_days"] == 30

    @pytest.mark.asyncio
    async def test_record_completed(self) -> None:
        pool, conn = _mock_pool()
        backup_id = uuid4()
        conn.fetchrow.return_value = {"backup_id": backup_id}
        bm = BackupManager(pool, StubHostingerClient())
        now = datetime.now(UTC)
        result = await bm.record_completed(
            project_id="p", vps_resource_id=uuid4(),
            hostinger_backup_id="hb-1",
            size_bytes=1_000_000,
            started_at=now - timedelta(minutes=5),
            completed_at=now,
        )
        assert result == backup_id

    @pytest.mark.asyncio
    async def test_list_backups(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {
                "backup_id": uuid4(), "project_id": "p",
                "vps_resource_id": uuid4(), "status": "completed",
                "size_bytes": 5000, "started_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
                "hostinger_backup_id": "hb-1",
            },
        ]
        bm = BackupManager(pool, StubHostingerClient())
        backups = await bm.list_backups("p")
        assert len(backups) == 1
        assert backups[0].status is BackupStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_restore_unknown_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        bm = BackupManager(pool, StubHostingerClient())
        with pytest.raises(LookupError):
            await bm.restore(uuid4())

    @pytest.mark.asyncio
    async def test_restore_succeeds(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "project_id": "p", "vps_resource_id": uuid4(),
            "hostinger_backup_id": "hb-1",
        }
        client = StubHostingerClient()
        client.set_response(
            "POST", "/vps/backups/hb-1/restore",
            json_body={"restored": True},
        )
        bm = BackupManager(pool, client)
        info = await bm.restore(uuid4())
        assert info.status is BackupStatus.RESTORED
