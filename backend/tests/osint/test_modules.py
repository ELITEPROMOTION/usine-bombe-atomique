"""V8 tests : 12 OSINT modules — guards + happy path with mocks."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.osint import legal_framework as lf
from app.osint.legal_framework import ScopeViolationError


# Re-use FakePool from test_legal_framework
from tests.osint.test_legal_framework import FakePool


@pytest.fixture
def pool():
    p = FakePool()
    lf.inject_pool_for_test(p)
    yield p
    lf.inject_pool_for_test(None)


# ---------------------------------------------------------------------------
# 1) dendani_ssl_audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssl_audit_dendani_only(pool):
    from app.osint import dendani_ssl_audit as m
    with pytest.raises(ScopeViolationError):
        await m.audit_ssl(target="example.com")


@pytest.mark.asyncio
async def test_ssl_audit_dendani_runs(pool):
    from app.osint import dendani_ssl_audit as m
    with patch.object(m, "_probe_ssl", new=AsyncMock(return_value={
        "version": "TLSv1.3", "cipher": "TLS_AES_256_GCM_SHA384",
        "issuer": {"commonName": "Let's Encrypt"},
        "subject": {"commonName": "api.dendani.dz"},
        "not_after": "Dec 31 23:59:59 2026 GMT", "der_size": 1234,
    })):
        out = await m.audit_ssl(target="api.dendani.dz")
    assert out["grade"] == "A"
    assert out["target"] == "api.dendani.dz"


@pytest.mark.asyncio
async def test_ssl_audit_grade_F_on_ssl3(pool):
    from app.osint import dendani_ssl_audit as m
    g = m._grade({"protocols": ["SSLv3"], "issues": [], "weak_ciphers": []})
    assert g == "F"


@pytest.mark.asyncio
async def test_ssl_audit_grade_C_weak(pool):
    from app.osint import dendani_ssl_audit as m
    g = m._grade({"protocols": ["TLSv1.3"], "issues": [], "weak_ciphers": ["RC4-MD5"]})
    assert g == "C"


# ---------------------------------------------------------------------------
# 2) dendani_breach_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breach_check_refuses_external_email(pool):
    from app.osint import dendani_breach_check as m
    with pytest.raises(ScopeViolationError):
        await m.check_email_breach(target="someone@example.com")


@pytest.mark.asyncio
async def test_breach_check_no_api_key_skipped(pool, monkeypatch):
    from app.osint import dendani_breach_check as m
    monkeypatch.delenv("HIBP_API_KEY", raising=False)
    out = await m.check_email_breach(target="ahmed@dendani.dz")
    assert out.get("skipped")


@pytest.mark.asyncio
async def test_password_pwned_mocked(pool, monkeypatch):
    from app.osint import dendani_breach_check as m
    fake_resp = MagicMock(status_code=200, text="0018A45C4D1DEF81644B54AB7F969B88D65:5")
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        # password 'password' SHA1 prefix=5BAA6, suffix=1E4C9B93F3F0682250B6CF8331B7EE68FD8
        out = await m.check_password_pwned(target="random_pw_xyz")
    assert "pwned" in out


# ---------------------------------------------------------------------------
# 3) dendani_dependency_scanner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dep_scanner_refuses_external_path(pool):
    from app.osint import dendani_dependency_scanner as m
    with pytest.raises(ScopeViolationError):
        await m.scan_python(target="/etc/sudoers")


@pytest.mark.asyncio
async def test_dep_scanner_handles_missing_tools(pool):
    from app.osint import dendani_dependency_scanner as m
    with patch.object(m, "_run", return_value={"rc": -127, "skipped": "pip-audit not installed"}):
        out = await m.scan_python(target="/app")
    assert out["target"] == "/app"


@pytest.mark.asyncio
async def test_dep_scanner_npm_no_package_json(pool):
    from app.osint import dendani_dependency_scanner as m
    out = await m.scan_npm(target="/app")
    assert out.get("skipped") == "no package.json"


@pytest.mark.asyncio
async def test_dep_scanner_docker_image_must_be_dendani(pool):
    from app.osint import dendani_dependency_scanner as m
    with pytest.raises(ScopeViolationError):
        await m.scan_docker_image(target="nginx:1.27")


# ---------------------------------------------------------------------------
# 4) dendani_dns_audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dns_audit_refuses_external(pool):
    from app.osint import dendani_dns_audit as m
    with pytest.raises(ScopeViolationError):
        await m.audit_typosquatting(target="example.com")


@pytest.mark.asyncio
async def test_dns_audit_permutations(pool):
    from app.osint import dendani_dns_audit as m
    perms = m._permute_domain("dendani.dz", max_variants=10)
    assert len(perms) > 0
    assert all(p.endswith((".dz", ".dx", ".da", ".dn", ".dc", ".dr")) for p in perms)


@pytest.mark.asyncio
async def test_dns_audit_dendani_with_no_resolves(pool):
    from app.osint import dendani_dns_audit as m
    with patch.object(m, "_resolve", return_value={"resolves": False}):
        out = await m.audit_typosquatting(target="dendani.dz", max_variants=5)
    assert out["alerts_count"] == 0


# ---------------------------------------------------------------------------
# 5) dendani_brand_monitor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brand_monitor_invalid_url(pool):
    from app.osint import dendani_brand_monitor as m
    out = await m.fetch_rss(target="not-a-url")
    assert out.get("error") == "rss-url-required"


@pytest.mark.asyncio
async def test_brand_monitor_sentiment():
    from app.osint import dendani_brand_monitor as m
    assert m._sentiment("excellente qualite top") == "positive"
    assert m._sentiment("scandale arnaque deception") == "negative"
    assert m._sentiment("article neutre standard") == "neutral"


@pytest.mark.asyncio
async def test_brand_monitor_reddit_invalid(pool):
    from app.osint import dendani_brand_monitor as m
    out = await m.fetch_reddit_mentions(target="")
    assert out.get("error") == "invalid-keyword"


# ---------------------------------------------------------------------------
# 6) competitor_public_watch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_competitor_unknown_feed(pool):
    from app.osint import competitor_public_watch as m
    out = await m.fetch_competitor_news(target="not-a-feed")
    assert out.get("error", "").startswith("unknown-feed")


@pytest.mark.asyncio
async def test_competitor_known_feeds():
    from app.osint import competitor_public_watch as m
    assert "algerie_eco" in m.DEFAULT_FEEDS


# ---------------------------------------------------------------------------
# 7) market_intelligence_dz
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_market_intel_unknown_source(pool):
    from app.osint import market_intelligence_dz as m
    out = await m.fetch_public_indicator(target="not-a-source")
    assert out.get("error", "").startswith("unknown-source")


@pytest.mark.asyncio
async def test_market_intel_sectors():
    from app.osint import market_intelligence_dz as m
    assert "immobilier" in m.SECTOR_KEYWORDS
    assert "fiscal" in m.SECTOR_KEYWORDS


# ---------------------------------------------------------------------------
# 8) regulatory_watch_dz
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regulatory_unknown_source(pool):
    from app.osint import regulatory_watch_dz as m
    out = await m.fetch_jora(target="not-a-feed")
    assert out.get("error", "").startswith("unknown-source")


@pytest.mark.asyncio
async def test_regulatory_default_keywords():
    from app.osint import regulatory_watch_dz as m
    assert "fiscal" in m.DEFAULT_KEYWORDS
    assert "vefa" in m.DEFAULT_KEYWORDS


# ---------------------------------------------------------------------------
# 9) consented_pentest_engine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pentest_refuses_without_consent(pool):
    from app.osint import consented_pentest_engine as m
    with pytest.raises(ScopeViolationError):
        await m.port_scan(target="random.example")


@pytest.mark.asyncio
async def test_pentest_validates_target_format(pool):
    from app.osint import consented_pentest_engine as m
    mgr = lf.ConsentManager(pool)
    await mgr.add_consent(
        target="bad target with spaces", actions=["port_scan"], contractor="X",
        contract_pdf_sha256="0" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )
    with pytest.raises(ScopeViolationError):
        await m.port_scan(target="bad target with spaces")


@pytest.mark.asyncio
async def test_pentest_with_consent_scaffold(pool):
    from app.osint import consented_pentest_engine as m
    mgr = lf.ConsentManager(pool)
    await mgr.add_consent(
        target="scope.example", actions=["port_scan"], contractor="Acme",
        contract_pdf_sha256="9" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )

    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"", b""))
    fake_proc.returncode = 0
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc)):
        out = await m.port_scan(target="scope.example")
    assert out["target"] == "scope.example"


@pytest.mark.asyncio
async def test_subdomain_enum_refuses_without_consent(pool):
    from app.osint import consented_pentest_engine as m
    with pytest.raises(ScopeViolationError):
        await m.subdomain_enum(target="random.example")


# ---------------------------------------------------------------------------
# 10) vulnerability_assessment_consented
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vuln_trivy_refuses_without_consent(pool):
    from app.osint import vulnerability_assessment_consented as m
    with pytest.raises(ScopeViolationError):
        await m.trivy_assess(target="random.example")


@pytest.mark.asyncio
async def test_vuln_grype_refuses_without_consent(pool):
    from app.osint import vulnerability_assessment_consented as m
    with pytest.raises(ScopeViolationError):
        await m.grype_assess(target="random.example")


@pytest.mark.asyncio
async def test_vuln_executive_summary():
    from app.osint import vulnerability_assessment_consented as m
    rep = {"target": "x", "tool": "trivy", "findings_count": 3,
           "by_severity": {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 0, "LOW": 0}}
    md = m.render_executive_summary(rep)
    assert "Vulnerability Assessment" in md
    assert "CRITICAL | 1" in md


# ---------------------------------------------------------------------------
# 11) threat_intel_aggregator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_threat_intel_no_otx_key_skipped(pool, monkeypatch):
    from app.osint import threat_intel_aggregator as m
    monkeypatch.delenv("OTX_API_KEY", raising=False)
    out = await m.fetch_otx_pulses(target="example.com")
    assert out.get("skipped")


@pytest.mark.asyncio
async def test_threat_intel_stack_keywords():
    from app.osint import threat_intel_aggregator as m
    assert "fastapi" in m.DENDANI_STACK_KEYWORDS
    assert "postgresql" in m.DENDANI_STACK_KEYWORDS


# ---------------------------------------------------------------------------
# 12) dark_web_monitor_lite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_darkweb_dendani_only_hibp(pool):
    from app.osint import dark_web_monitor_lite as m
    with pytest.raises(ScopeViolationError):
        await m.hibp_enterprise_lookup(target="example.com")


@pytest.mark.asyncio
async def test_darkweb_dendani_only_spycloud(pool):
    from app.osint import dark_web_monitor_lite as m
    with pytest.raises(ScopeViolationError):
        await m.spycloud_lookup(target="example.com")


@pytest.mark.asyncio
async def test_darkweb_marketplace_scrape_refused(pool):
    from app.osint import dark_web_monitor_lite as m
    with pytest.raises(ScopeViolationError):
        await m.attempt_marketplace_scrape(target="any")


@pytest.mark.asyncio
async def test_darkweb_no_api_key_skipped(pool, monkeypatch):
    from app.osint import dark_web_monitor_lite as m
    monkeypatch.delenv("HIBP_ENTERPRISE_API_KEY", raising=False)
    out = await m.hibp_enterprise_lookup(target="dendani.dz")
    assert out.get("skipped")


# ---------------------------------------------------------------------------
# Cross-cutting : audit trail records ALL module actions (denied + allowed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_trail_records_module_denial(pool):
    from app.osint import dendani_ssl_audit as m
    with pytest.raises(ScopeViolationError):
        await m.audit_ssl(target="external.example")
    # FakePool stores audit list
    assert any(e["decision"] == "denied" for e in pool.audit)
    assert any(e["module"] == "dendani_ssl_audit" for e in pool.audit)


@pytest.mark.asyncio
async def test_audit_trail_records_module_allowed(pool):
    from app.osint import dendani_ssl_audit as m
    with patch.object(m, "_probe_ssl", new=AsyncMock(return_value={
        "version": "TLSv1.3", "cipher": "TLS_AES_256",
        "issuer": {"commonName": "X"}, "subject": {},
        "not_after": "Dec 31 23:59:59 2026 GMT", "der_size": 100,
    })):
        await m.audit_ssl(target="api.dendani.dz")
    assert any(e["decision"] == "allowed" and e["module"] == "dendani_ssl_audit"
                for e in pool.audit)


# ---------------------------------------------------------------------------
# Integrity end-to-end : decoder appended events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_module_actions_chain_intact(pool):
    from app.osint import dendani_ssl_audit as m
    with patch.object(m, "_probe_ssl", new=AsyncMock(return_value={
        "version": "TLSv1.3", "cipher": "x",
        "issuer": {"commonName": "X"}, "subject": {},
        "not_after": "Dec 31 23:59:59 2026 GMT", "der_size": 1,
    })):
        await m.audit_ssl(target="api.dendani.dz")
        await m.audit_ssl(target="api.dendani.dz")
    trail = lf.AuditTrail(pool)
    rep = await trail.verify_chain()
    assert rep["integrity_ok"]
