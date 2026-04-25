"""V8 tests : legal_framework guards (consent + scope + audit + decorators).

Mocks asyncpg.Pool to keep tests fully isolated from DB.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.osint import legal_framework as lf


# ---------------------------------------------------------------------------
# In-memory fake pool
# ---------------------------------------------------------------------------


class FakeConnection:
    def __init__(self, store: "FakePool"):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def fetch(self, sql, *args):
        return self._store.exec(sql, args, mode="fetch")

    async def fetchrow(self, sql, *args):
        rows = self._store.exec(sql, args, mode="fetch")
        return rows[0] if rows else None

    async def fetchval(self, sql, *args):
        row = await self.fetchrow(sql, *args)
        if not row:
            return None
        return list(row.values())[0]

    async def execute(self, sql, *args):
        self._store.exec(sql, args, mode="exec")

    def transaction(self):
        class _Tx:
            async def __aenter__(self_):
                return None

            async def __aexit__(self_, *a):
                return False
        return _Tx()


class FakePool:
    def __init__(self):
        self.consents: list[dict] = []
        self.audit: list[dict] = []
        self._counter = 0

    def acquire(self):
        conn = FakeConnection(self)

        class _Ctx:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False
        return _Ctx()

    def exec(self, sql: str, args: tuple, mode: str):
        s = sql.strip().upper()
        if "INSERT INTO OSINT_CONSENTS" in s:
            cid, target, actions, contractor, h, signed, expires = args
            self.consents.append({
                "consent_id": cid, "target": target, "actions": actions,
                "contractor": contractor, "contract_pdf_sha256": h,
                "signed_at": signed, "expires_at": expires,
                "revoked_at": None, "revoked_reason": None,
            })
            return None
        if "UPDATE OSINT_CONSENTS" in s:
            cid, reason = args
            for c in self.consents:
                if c["consent_id"] == cid and c["revoked_at"] is None:
                    c["revoked_at"] = datetime.now(timezone.utc)
                    c["revoked_reason"] = reason
            return None
        if "FROM OSINT_CONSENTS" in s and "WHERE TARGET" in s:
            target = args[0]
            now = datetime.now(timezone.utc)
            for c in sorted(self.consents, key=lambda x: x["signed_at"], reverse=True):
                if c["target"] == target and c["revoked_at"] is None and c["expires_at"] > now:
                    return [c]
            return []
        if "FROM OSINT_CONSENTS" in s:
            now = datetime.now(timezone.utc)
            return [c for c in self.consents
                    if c["revoked_at"] is None and c["expires_at"] > now]
        if "INSERT INTO OSINT_AUDIT_TRAIL" in s:
            self._counter += 1
            ev = {
                "id": self._counter,
                "event_id": args[0],
                "actor": args[1], "module": args[2], "action": args[3],
                "target": args[4], "risk_level": args[5], "decision": args[6],
                "consent_id": args[7],
                "payload_hash": args[8], "prev_hash": args[9], "chain_hash": args[10],
                "payload_json": args[11],
                "created_at": datetime.now(timezone.utc),
            }
            self.audit.append(ev)
            return [{"event_id": ev["event_id"]}]
        if "FROM OSINT_AUDIT_TRAIL" in s and "ORDER BY ID DESC LIMIT 1" in s:
            return [self.audit[-1]] if self.audit else []
        if "FROM OSINT_AUDIT_TRAIL" in s and "ORDER BY ID ASC" in s:
            return list(self.audit)
        return []


@pytest.fixture
def pool():
    p = FakePool()
    lf.inject_pool_for_test(p)
    yield p
    lf.inject_pool_for_test(None)


# ---------------------------------------------------------------------------
# 1) ConsentManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consent_dendani_target_always_granted(pool):
    mgr = lf.ConsentManager(pool)
    res = await mgr.check_consent("api.dendani.dz", "scan")
    assert res.granted
    assert res.reason == "dendani-whitelisted"


@pytest.mark.asyncio
async def test_consent_unknown_target_denied(pool):
    mgr = lf.ConsentManager(pool)
    res = await mgr.check_consent("example.com", "scan")
    assert not res.granted
    assert "no-active-consent" in res.reason


@pytest.mark.asyncio
async def test_consent_add_and_check(pool):
    mgr = lf.ConsentManager(pool)
    h = "a" * 64
    cid = await mgr.add_consent(
        target="client-a.example", actions=["scan", "subdomain_enum"],
        contractor="Acme Inc", contract_pdf_sha256=h,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert UUID(cid)
    ok = await mgr.check_consent("client-a.example", "scan")
    assert ok.granted

    nope = await mgr.check_consent("client-a.example", "destructive_test")
    assert not nope.granted
    assert "destructive_test not covered" in nope.reason


@pytest.mark.asyncio
async def test_consent_revoke(pool):
    mgr = lf.ConsentManager(pool)
    cid = await mgr.add_consent(
        target="t.example", actions=["*"], contractor="X",
        contract_pdf_sha256="b" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    await mgr.revoke_consent(cid, "client request")
    res = await mgr.check_consent("t.example", "scan")
    assert not res.granted


@pytest.mark.asyncio
async def test_consent_invalid_hash_rejected(pool):
    mgr = lf.ConsentManager(pool)
    with pytest.raises(ValueError):
        await mgr.add_consent(
            target="t.example", actions=["*"], contractor="X",
            contract_pdf_sha256="too-short",
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
    with pytest.raises(ValueError):
        await mgr.add_consent(
            target="t.example", actions=["*"], contractor="X",
            contract_pdf_sha256="ZZZ" + "0" * 61,
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )


@pytest.mark.asyncio
async def test_consent_expired_not_returned(pool):
    mgr = lf.ConsentManager(pool)
    # Insert directly to bypass future-date check
    pool.consents.append({
        "consent_id": uuid4(),
        "target": "expired.example", "actions": ["scan"],
        "contractor": "Old", "contract_pdf_sha256": "c" * 64,
        "signed_at": datetime.now(timezone.utc) - timedelta(days=60),
        "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
        "revoked_at": None, "revoked_reason": None,
    })
    res = await mgr.check_consent("expired.example", "scan")
    assert not res.granted


# ---------------------------------------------------------------------------
# 2) ScopeEnforcer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_authorize_dendani(pool):
    enforcer = lf.ScopeEnforcer(lf.ConsentManager(pool))
    d = await enforcer.authorize("api.dendani.dz", "scan")
    assert d.allowed


@pytest.mark.asyncio
async def test_scope_authorize_empty_target(pool):
    enforcer = lf.ScopeEnforcer(lf.ConsentManager(pool))
    d = await enforcer.authorize("", "scan")
    assert not d.allowed
    assert "empty-target" in d.reason


@pytest.mark.asyncio
async def test_scope_authorize_gov_without_consent(pool):
    enforcer = lf.ScopeEnforcer(lf.ConsentManager(pool))
    d = await enforcer.authorize("ministere.gov.dz", "scan")
    assert not d.allowed
    assert "gov-edu-target-without-consent" in d.reason


@pytest.mark.asyncio
async def test_scope_authorize_unknown_without_consent(pool):
    enforcer = lf.ScopeEnforcer(lf.ConsentManager(pool))
    d = await enforcer.authorize("random.example", "scan")
    assert not d.allowed


@pytest.mark.asyncio
async def test_scope_authorize_with_consent(pool):
    mgr = lf.ConsentManager(pool)
    await mgr.add_consent(
        target="client.example", actions=["scan"], contractor="X",
        contract_pdf_sha256="d" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    enforcer = lf.ScopeEnforcer(mgr)
    d = await enforcer.authorize("client.example", "scan")
    assert d.allowed
    assert d.consent_id


# ---------------------------------------------------------------------------
# 3) AuditTrail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_append_and_chain(pool):
    trail = lf.AuditTrail(pool)
    e1 = await trail.append(actor="t1", module="m", action="a", target="x.dendani.dz",
                             risk_level="low", decision="allowed", payload={"k": 1})
    e2 = await trail.append(actor="t1", module="m", action="b", target="x.dendani.dz",
                             risk_level="low", decision="allowed", payload={"k": 2})
    assert e1 != e2
    rep = await trail.verify_chain()
    assert rep["events_checked"] == 2
    assert rep["integrity_ok"]


@pytest.mark.asyncio
async def test_audit_export(pool):
    trail = lf.AuditTrail(pool)
    await trail.append(actor="t", module="m", action="a", target="api.dendani.dz",
                       risk_level="low", decision="allowed", payload={"v": 42})
    out = await trail.export()
    assert len(out) == 1
    assert out[0]["target"] == "api.dendani.dz"
    assert out[0]["decision"] == "allowed"


@pytest.mark.asyncio
async def test_audit_chain_corruption_detected(pool):
    trail = lf.AuditTrail(pool)
    await trail.append(actor="t", module="m", action="a", target="x.dendani.dz",
                       risk_level="low", decision="allowed")
    # tamper
    pool.audit[0]["chain_hash"] = "0" * 64
    rep = await trail.verify_chain()
    assert not rep["integrity_ok"]
    assert len(rep["broken"]) == 1


# ---------------------------------------------------------------------------
# 4) Decorators
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dendani_only_accepts_dendani(pool):
    @lf.dendani_only("target")
    async def scan(target: str):
        return {"ok": True}
    out = await scan(target="api.dendani.dz")
    assert out == {"ok": True}


@pytest.mark.asyncio
async def test_dendani_only_refuses_other(pool):
    @lf.dendani_only("target")
    async def scan(target: str):
        return {"ok": True}
    with pytest.raises(lf.ScopeViolationError):
        await scan(target="example.com")


@pytest.mark.asyncio
async def test_requires_consent_blocks_without_consent(pool):
    @lf.requires_consent("target", action="scan")
    async def pentest(target: str, **kw):
        return {"ok": True}
    with pytest.raises(lf.ScopeViolationError):
        await pentest(target="random.example")


@pytest.mark.asyncio
async def test_requires_consent_allows_with_consent(pool):
    mgr = lf.ConsentManager(pool)
    await mgr.add_consent(
        target="ok.example", actions=["scan"], contractor="X",
        contract_pdf_sha256="e" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )

    @lf.requires_consent("target", action="scan")
    async def pentest(target: str, **kw):
        return {"ok": True}

    out = await pentest(target="ok.example")
    assert out == {"ok": True}


@pytest.mark.asyncio
async def test_log_osint_action_records_allowed(pool):
    @lf.log_osint_action(risk_level="low", module="testmod")
    async def safe(target: str = "api.dendani.dz"):
        return {"v": 1}
    await safe(target="api.dendani.dz")
    assert len(pool.audit) == 1
    assert pool.audit[0]["decision"] == "allowed"


@pytest.mark.asyncio
async def test_log_osint_action_records_denied(pool):
    # log_osint_action must be the OUTER decorator so it can catch
    # ScopeViolationError raised by inner dendani_only.
    @lf.log_osint_action(risk_level="medium", module="testmod")
    @lf.dendani_only("target")
    async def block(target: str):
        return {"v": 1}
    with pytest.raises(lf.ScopeViolationError):
        await block(target="external.example")
    assert any(e["decision"] == "denied" for e in pool.audit)


@pytest.mark.asyncio
async def test_log_osint_action_records_error(pool):
    @lf.log_osint_action(risk_level="low", module="testmod")
    async def boom(target: str = "api.dendani.dz"):
        raise RuntimeError("kaboom")
    with pytest.raises(RuntimeError):
        await boom(target="api.dendani.dz")
    assert any(e["decision"] == "error" for e in pool.audit)


@pytest.mark.asyncio
async def test_rate_limit_strict(pool):
    @lf.rate_limit_strict(max_per_hour=3)
    async def limited():
        return 1
    await limited()
    await limited()
    await limited()
    with pytest.raises(lf.ScopeViolationError):
        await limited()


@pytest.mark.asyncio
async def test_normalize_target_lowercase(pool):
    enforcer = lf.ScopeEnforcer(lf.ConsentManager(pool))
    d = await enforcer.authorize("API.DENDANI.DZ", "scan")
    assert d.allowed
    assert d.target == "api.dendani.dz"


@pytest.mark.asyncio
async def test_dendani_subdomain_match(pool):
    assert lf._is_dendani_target("anything.dendani.dz")
    assert lf._is_dendani_target("api.dendani.dz")
    assert not lf._is_dendani_target("dendani.example.com")
    assert not lf._is_dendani_target("fake-dendani.dz")


def test_genesis_hash_constant():
    assert lf.GENESIS_HASH == "0" * 64


@pytest.mark.asyncio
async def test_consent_listing_excludes_revoked(pool):
    mgr = lf.ConsentManager(pool)
    cid = await mgr.add_consent(
        target="t.example", actions=["*"], contractor="X",
        contract_pdf_sha256="f" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    await mgr.add_consent(
        target="t2.example", actions=["*"], contractor="Y",
        contract_pdf_sha256="0" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    await mgr.revoke_consent(cid, "test")
    active = await mgr.list_active_consents()
    assert len(active) == 1
    assert active[0].target == "t2.example"


@pytest.mark.asyncio
async def test_scope_decision_dataclass():
    d = lf.ScopeDecision(allowed=True, target="x", reason="ok")
    assert d.allowed
    assert d.target == "x"


@pytest.mark.asyncio
async def test_consent_result_dataclass():
    r = lf.ConsentResult(granted=False, consent_id=None, target="x", reason="no")
    assert not r.granted


@pytest.mark.asyncio
async def test_audit_payload_canonical_hash(pool):
    trail = lf.AuditTrail(pool)
    e1 = await trail.append(actor="a", module="m", action="x", target="api.dendani.dz",
                             risk_level="low", decision="allowed", payload={"a": 1, "b": 2})
    h1 = pool.audit[-1]["payload_hash"]
    pool.audit.clear()
    pool.audit = []
    # reset chain - approximate test that same canonical input yields same hash
    e2 = await trail.append(actor="a", module="m", action="x", target="api.dendani.dz",
                             risk_level="low", decision="allowed", payload={"b": 2, "a": 1})
    h2 = pool.audit[-1]["payload_hash"]
    assert h1 == h2  # canonical sort_keys


@pytest.mark.asyncio
async def test_dendani_only_refuses_empty(pool):
    @lf.dendani_only("target")
    async def scan(target: str = ""):
        return True
    with pytest.raises(lf.ScopeViolationError):
        await scan(target="")
    with pytest.raises(lf.ScopeViolationError):
        await scan()


@pytest.mark.asyncio
async def test_requires_consent_missing_target(pool):
    @lf.requires_consent("target", action="scan")
    async def pentest(target=None, **kw):
        return True
    with pytest.raises(lf.ScopeViolationError):
        await pentest(target=None)


@pytest.mark.asyncio
async def test_audit_export_filtering_by_date(pool):
    trail = lf.AuditTrail(pool)
    await trail.append(actor="a", module="m", action="x", target="api.dendani.dz",
                       risk_level="low", decision="allowed")
    out = await trail.export(since=datetime.now(timezone.utc) - timedelta(hours=1))
    assert len(out) == 1


def test_risk_level_enum_values():
    assert lf.RiskLevel.LOW.value == "low"
    assert lf.RiskLevel.HIGH.value == "high"
    assert lf.RiskLevel.CRITICAL.value == "critical"


def test_canon_sorted():
    a = lf._canon({"b": 1, "a": 2})
    b = lf._canon({"a": 2, "b": 1})
    assert a == b


def test_sha256_helper():
    assert lf._sha256("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.mark.asyncio
async def test_consent_action_wildcard(pool):
    mgr = lf.ConsentManager(pool)
    await mgr.add_consent(
        target="wild.example", actions=["*"], contractor="X",
        contract_pdf_sha256="9" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    res = await mgr.check_consent("wild.example", "anything-here")
    assert res.granted


@pytest.mark.asyncio
async def test_scope_decision_normalizes_case(pool):
    enforcer = lf.ScopeEnforcer(lf.ConsentManager(pool))
    d = await enforcer.authorize("RANDOM.example", "scan")
    assert d.target == "random.example"


@pytest.mark.asyncio
async def test_audit_records_consent_id(pool):
    @lf.log_osint_action(risk_level="high", module="testmod")
    async def withc(target: str = "api.dendani.dz", _consent_id: str | None = None):
        return {"ok": True}
    cid = str(uuid4())
    await withc(target="api.dendani.dz", _consent_id=cid)
    assert str(pool.audit[-1]["consent_id"]) == cid


@pytest.mark.asyncio
async def test_log_osint_action_handles_actor_kwarg(pool):
    @lf.log_osint_action(risk_level="low", module="testmod")
    async def scan(target: str = "api.dendani.dz", _actor: str = "system"):
        return {"v": 1}
    await scan(target="api.dendani.dz", _actor="ahmed")
    assert pool.audit[-1]["actor"] == "ahmed"


@pytest.mark.asyncio
async def test_consent_action_unmatched_returns_consent_id(pool):
    mgr = lf.ConsentManager(pool)
    cid = await mgr.add_consent(
        target="x.example", actions=["scan"], contractor="X",
        contract_pdf_sha256="1" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    res = await mgr.check_consent("x.example", "exfiltrate")
    assert not res.granted
    assert res.consent_id == cid


@pytest.mark.asyncio
async def test_audit_segments_are_chained(pool):
    trail = lf.AuditTrail(pool)
    await trail.append(actor="a", module="m", action="x", target="api.dendani.dz",
                       risk_level="low", decision="allowed")
    await trail.append(actor="a", module="m", action="y", target="api.dendani.dz",
                       risk_level="low", decision="allowed")
    rep = await trail.verify_chain()
    assert rep["integrity_ok"]
    assert pool.audit[1]["prev_hash"] == pool.audit[0]["chain_hash"]


@pytest.mark.asyncio
async def test_scope_enforcer_with_subdomain_consent(pool):
    mgr = lf.ConsentManager(pool)
    await mgr.add_consent(
        target="sub.client.example", actions=["scan"], contractor="X",
        contract_pdf_sha256="2" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    enforcer = lf.ScopeEnforcer(mgr)
    d = await enforcer.authorize("sub.client.example", "scan")
    assert d.allowed
    # Sister sub-domain should NOT be implicitly covered
    d2 = await enforcer.authorize("other.client.example", "scan")
    assert not d2.allowed
