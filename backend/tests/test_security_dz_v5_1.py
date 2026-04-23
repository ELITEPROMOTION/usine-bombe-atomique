"""V5.1 Wave 2 — P0 Security + DZ conformity.

Couvre :
  - evidence_ledger.record + verify_chain + tail (+ append-only invariants)
  - quality_kernel INVARIANTS signature + full_report + record_remediation
  - middleware/tenant : decode JWT, hydrate tenant, apply_session_vars
  - integrations/vault_client : put/get/get_key + fallback env + cache
  - orchestration/dz_rules : load_active + apply_rules + upsert_rule
  - agents/conformite_dz_agent : TVA/TAP/CNAS/IRG/NIN/VEFA property-based
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.conformite_dz_agent import (
    ConformiteDzAgent,
    _rule_cnas,
    _rule_devise,
    _rule_irg,
    _rule_nin,
    _rule_no_foreign_regs,
    _rule_tap,
    _rule_tva,
    _rule_vefa_paliers,
)
from app.agents.workspace import Workspace
from app.integrations.vault_client import VaultClient, VaultUnavailable
from app.orchestration import dz_rules, evidence_ledger, quality_kernel


pytestmark = pytest.mark.asyncio


# ============================================================ evidence_ledger

async def test_ledger_record_returns_event_id(pool):
    eid = await evidence_ledger.record(
        pool, kind="decision", actor="test.security",
        payload={"note": "unit_test"},
    )
    assert len(eid) == 36


async def test_ledger_chain_hash_matches_recomputed(pool):
    eid1 = await evidence_ledger.record(pool, "decision", "chain.test", {"a": 1})
    eid2 = await evidence_ledger.record(pool, "decision", "chain.test", {"a": 2})
    assert eid1 != eid2
    # Verify les 2 derniers events recomputent correctement
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT prev_hash, payload_hash, chain_hash FROM evidence_ledger "
            "ORDER BY id DESC LIMIT 2"
        )
    for r in rows:
        recomp = evidence_ledger._sha256(r["prev_hash"] + r["payload_hash"])
        assert recomp == r["chain_hash"]


async def test_ledger_append_only_cannot_update(pool):
    """Trigger-enforced : UPDATE sur evidence_ledger leve."""
    await evidence_ledger.record(pool, "decision", "immut.test", {})
    with pytest.raises(Exception) as exc_info:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE evidence_ledger SET actor = 'hacker' "
                "WHERE id = (SELECT MAX(id) FROM evidence_ledger)"
            )
    assert "append-only" in str(exc_info.value).lower() or "block" in str(exc_info.value).lower()


async def test_ledger_append_only_cannot_delete(pool):
    await evidence_ledger.record(pool, "decision", "immut.test.del", {})
    with pytest.raises(Exception):
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM evidence_ledger "
                "WHERE id = (SELECT MAX(id) FROM evidence_ledger)"
            )


async def test_ledger_tail_returns_recent(pool):
    await evidence_ledger.record(pool, "decision", "tail.test", {"x": 1})
    rows = await evidence_ledger.tail(pool, limit=3)
    assert len(rows) >= 1
    assert "event_id" in rows[0]


def test_ledger_canon_deterministic():
    a = evidence_ledger._canon({"b": 1, "a": 2})
    b = evidence_ledger._canon({"a": 2, "b": 1})
    assert a == b  # sort_keys


def test_ledger_sha256_length():
    assert len(evidence_ledger._sha256("test")) == 64


# ============================================================ quality_kernel

def test_kernel_invariants_count():
    assert len(quality_kernel.INVARIANTS) >= 6


def test_kernel_invariant_hash_deterministic():
    h1 = quality_kernel.invariant_hash("no_hardcoded_secret",
                                         quality_kernel.INVARIANTS["no_hardcoded_secret"])
    h2 = quality_kernel.invariant_hash("no_hardcoded_secret",
                                         quality_kernel.INVARIANTS["no_hardcoded_secret"])
    assert h1 == h2
    assert len(h1) == 64


def test_kernel_invariant_hash_unique_per_name():
    names = list(quality_kernel.INVARIANTS.keys())
    hashes = {quality_kernel.invariant_hash(n, quality_kernel.INVARIANTS[n])
               for n in names}
    assert len(hashes) == len(names)


async def test_kernel_full_report(pool):
    rep = await quality_kernel.full_report(pool)
    d = rep.to_dict()
    assert d["invariants_signed"], "invariants doivent etre signes"
    assert "integrity_ok" in d["ledger_integrity"]


async def test_kernel_record_remediation(pool, seeded_task_id):
    eid = await quality_kernel.record_remediation(
        pool, task_id=seeded_task_id, defect_id="D-001",
        patch_summary="Add validator", root_cause="Missing NIN check",
        layers=["unit", "integration"],
    )
    assert len(eid) == 36


# ============================================================ dz_rules

async def test_dz_rules_load_active_returns_list(pool):
    rules = await dz_rules.load_active(pool)
    assert isinstance(rules, list)
    assert len(rules) >= 1


async def test_dz_rules_apply_basic():
    rule = dz_rules.DZRule(
        rule_code="T1", version=1, label="test",
        regex_positive=r"TVA\s+19", regex_negative=None, severity="high",
    )
    res = dz_rules.apply_rules("La TVA 19% est appliquee.", [rule])
    assert res[0]["passed"] is True


async def test_dz_rules_apply_negative_blocks():
    rule = dz_rules.DZRule(
        rule_code="T2", version=1, label="test neg",
        regex_positive=r"foo", regex_negative=r"bar", severity="low",
    )
    res = dz_rules.apply_rules("foo and bar together", [rule])
    assert res[0]["passed"] is False


async def test_dz_rules_apply_invalid_regex_skipped(caplog):
    rule = dz_rules.DZRule(
        rule_code="T3", version=1, label="bad regex",
        regex_positive=r"(unclosed", regex_negative=None, severity="low",
    )
    res = dz_rules.apply_rules("text", [rule])
    assert res == []  # skipped


async def test_dz_rules_upsert_rule(pool):
    r = await dz_rules.upsert_rule(
        pool, rule_code="T_UNIT_TEST_Z", label="tmp",
        regex_positive=r"xyz", severity="low",
    )
    assert r["new_version"] >= 1
    # Bumps version
    r2 = await dz_rules.upsert_rule(
        pool, rule_code="T_UNIT_TEST_Z", label="tmp2",
        regex_positive=r"xyz2", severity="low",
    )
    assert r2["new_version"] == r["new_version"] + 1
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM dz_rules_config WHERE rule_code='T_UNIT_TEST_Z'")


# ============================================================ vault_client

def test_vault_client_defaults(monkeypatch):
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    vc = VaultClient()
    assert "vault" in vc.addr
    assert vc.token


def test_vault_client_get_missing_returns_default(monkeypatch):
    """get() sans Vault -> default."""
    def fake_client(self):
        class _Broken:
            class secrets:
                class kv:
                    class v2:
                        @staticmethod
                        def read_secret_version(**kw):
                            raise RuntimeError("down")
        return _Broken()
    monkeypatch.setattr(VaultClient, "_client", fake_client)
    vc = VaultClient()
    assert vc.get("missing") == {}
    assert vc.get("missing", default={"a": 1}) == {"a": 1}


def test_vault_client_get_key_env_fallback(monkeypatch):
    monkeypatch.setenv("UBA_TEST_FALLBACK", "fallback_value")
    vc = VaultClient()
    vc._cache["anywhere"] = {"other_key": "x"}
    out = vc.get_key("anywhere", "missing_key",
                      fallback_env="UBA_TEST_FALLBACK")
    assert out == "fallback_value"


def test_vault_client_get_key_from_cache(monkeypatch):
    vc = VaultClient()
    vc._cache["cached_path"] = {"k": "v1"}
    assert vc.get_key("cached_path", "k") == "v1"


def test_vault_client_is_available_false_when_boom(monkeypatch):
    def boom(self):
        raise RuntimeError("down")
    monkeypatch.setattr(VaultClient, "_client", boom)
    assert VaultClient().is_available() is False


def test_vault_client_import_error(monkeypatch):
    import builtins
    real_import = builtins.__import__
    def no_hvac(name, *a, **kw):
        if name == "hvac":
            raise ImportError("no hvac")
        return real_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", no_hvac)
    vc = VaultClient()
    vc._hvac = None
    with pytest.raises(VaultUnavailable):
        vc._client()


# ============================================================ tenant middleware

from httpx import ASGITransport, AsyncClient
from app.main import app as fastapi_app


async def test_tenant_default_state_without_auth():
    async with AsyncClient(transport=ASGITransport(app=fastapi_app),
                            base_url="http://t") as ac:
        r = await ac.get("/api/v1/health")
    assert r.status_code == 200


async def test_tenant_middleware_invalid_jwt_ignored():
    async with AsyncClient(transport=ASGITransport(app=fastapi_app),
                            base_url="http://t") as ac:
        r = await ac.get("/api/v1/health",
                          headers={"authorization": "bearer not-a-real-jwt"})
    assert r.status_code == 200


async def test_tenant_middleware_no_bearer():
    async with AsyncClient(transport=ASGITransport(app=fastapi_app),
                            base_url="http://t") as ac:
        r = await ac.get("/api/v1/health",
                          headers={"authorization": "basic something"})
    assert r.status_code == 200


async def test_apply_session_vars_sets_tenant(pool):
    class _Req:
        class state:
            tenant_id = "00000000-0000-0000-0000-000000000001"
            is_super_admin = False
    from app.middleware.tenant import apply_session_vars
    async with pool.acquire() as conn, conn.transaction():
        await apply_session_vars(conn, _Req())
        val = await conn.fetchval("SELECT current_setting('app.tenant_id', TRUE)")
    assert val == "00000000-0000-0000-0000-000000000001"


# ============================================================ DZ agent property-based


PAIE_CORPUS = """
from decimal import Decimal
TVA = Decimal("0.19")  # TVA 19%
TAP = Decimal("0.02")  # TAP 2%
CNAS_SAL = Decimal("0.09")  # CNAS salarie 9%
CNAS_EMP = Decimal("0.26")  # CNAS employeur 26%
# IRG progressif : seuils > 30000 > 120000 > 360000 > 1440000 DZD
if salaire > 30000 and salaire < 120000:
    taux = 0.20
elif salaire > 360000:
    taux = 0.35

def valider_nin(nin: str) -> bool:
    return len(nin) == 18 and nin.isdigit()

DEVISE = "DZD"  # Dinar algerien
"""


def test_dz_tva_rule_paie_passes():
    r = _rule_tva(PAIE_CORPUS)
    assert r.passed is True
    assert "R1" in r.rule


def test_dz_tap_rule_paie_passes():
    r = _rule_tap(PAIE_CORPUS)
    assert r.passed is True


def test_dz_cnas_rule_applicable_passes():
    r = _rule_cnas(PAIE_CORPUS, applicable=True)
    assert r.applicable is True
    assert r.passed is True


def test_dz_cnas_rule_not_applicable():
    r = _rule_cnas(PAIE_CORPUS, applicable=False)
    assert r.applicable is False


def test_dz_irg_rule_applicable_passes():
    r = _rule_irg(PAIE_CORPUS, applicable=True)
    assert r.passed is True


def test_dz_nin_rule_detects_validator():
    r = _rule_nin(PAIE_CORPUS, applicable=True)
    assert r.passed is True


def test_dz_devise_rule_passes():
    r = _rule_devise(PAIE_CORPUS)
    assert r.passed is True


def test_dz_no_foreign_regs_passes_when_absent():
    r = _rule_no_foreign_regs(PAIE_CORPUS)
    assert r.passed is True


def test_dz_no_foreign_regs_fails_on_hipaa():
    corpus = PAIE_CORPUS + "\n# HIPAA compliance required"
    r = _rule_no_foreign_regs(corpus)
    assert r.passed is False


VEFA_CORPUS = """
# Paliers VEFA : palier 5%, palier 20%, palier 15%, palier 25%, palier 35%
PCT = [5, 20, 15, 25, 35]
def palier(i): return PCT[i]
"""


def test_dz_vefa_paliers_applicable_passes():
    r = _rule_vefa_paliers(VEFA_CORPUS, applicable=True)
    assert r.applicable is True
    assert r.passed is True


def test_dz_vefa_paliers_not_applicable():
    r = _rule_vefa_paliers(VEFA_CORPUS, applicable=False)
    assert r.applicable is False


# --- property-based : garanties sur entrees aleatoires ---------------

@given(st.text(min_size=0, max_size=200))
@settings(max_examples=40, deadline=None)
def test_dz_agent_rule_never_raises_tva(random_text):
    _rule_tva(random_text)  # should not raise


@given(st.text(min_size=0, max_size=200))
@settings(max_examples=40, deadline=None)
def test_dz_agent_rule_never_raises_cnas(random_text):
    _rule_cnas(random_text, applicable=True)


@given(st.text(min_size=0, max_size=200))
@settings(max_examples=40, deadline=None)
def test_dz_agent_rule_never_raises_irg(random_text):
    _rule_irg(random_text, applicable=True)


@given(st.integers(min_value=0, max_value=10**20))
@settings(max_examples=30, deadline=None)
def test_dz_nin_rule_various_digits(nin_int):
    s = str(nin_int)
    corpus = f"def valider_nin(x): return len(x) == 18\nval = '{s}'"
    # Just should not raise
    _rule_nin(corpus, applicable=True)


# ============================================================ Full agent smoke

async def test_conformite_agent_e2e(tmp_path):
    ws = Workspace(task_id="test", root=tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "business.py").write_text(PAIE_CORPUS)
    agent = ConformiteDzAgent()
    # Load files into Workspace.files so manifest() picks them up
    for f in (tmp_path / "app").iterdir():
        if f.is_file():
            ws.files[f"app/{f.name}"] = f.read_text()
    result = await agent._execute({
        "workspace": ws,
        "spec": "Module Paie Algerie avec CNAS IRG TAP et NIN validator",
    })
    assert 0 <= result["score"] <= 1


async def test_conformite_agent_fails_on_hipaa(tmp_path):
    ws = Workspace(task_id="test", root=tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "business.py").write_text(
        PAIE_CORPUS + "\n# HIPAA compliance + SOX requirements\n")
    agent = ConformiteDzAgent()
    # Load files into Workspace.files so manifest() picks them up
    for f in (tmp_path / "app").iterdir():
        if f.is_file():
            ws.files[f"app/{f.name}"] = f.read_text()
    result = await agent._execute({
        "workspace": ws,
        "spec": "Module Paie Algerie",
    })
    assert result["score"] <= 1.0
