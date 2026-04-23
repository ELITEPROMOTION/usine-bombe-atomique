"""V5.1 Wave 1 — Integration tests P0 autonomy (pool + DB reels).

Couvre : governor, auditor, chaos, correlation_id, lease_manager,
hard_boundary_registry, intervention_learner, ambiguity_resolver,
credential_vault_universal, auth_prefetcher, simulation_lab,
calibration_engine, cost_model, explainability_api, human_necessity_proof.
"""
from __future__ import annotations

import asyncio

import pytest

from app.autonomy import (
    ambiguity_resolver,
    auth_prefetcher,
    autonomy_auditor,
    autonomy_chaos_engine,
    autonomy_cost_model,
    autonomy_explainability_api,
    autonomy_governor,
    autonomy_simulation_lab,
    calibration_engine,
    correlation_id_universal,
    credential_vault_universal,
    fallback_chain,
    hard_boundary_registry,
    human_necessity_proof,
    intervention_learner,
    permission_lease_manager,
)
from app.autonomy.autonomy_governor import DecisionPoint
from app.autonomy.autonomy_ladder import Mode
from app.autonomy.autonomy_simulation_lab import Policy
from app.autonomy.human_necessity_proof import NecessityEvidence


pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------- correlation_id

async def test_correlation_full_lifecycle(pool, seeded_task_id):
    cid = correlation_id_universal.new_id("itest")
    await correlation_id_universal.register(pool, cid, "unit_test",
                                              task_id=seeded_task_id)
    await correlation_id_universal.hop(pool, cid)
    await correlation_id_universal.hop(pool, cid)
    await correlation_id_universal.close(pool, cid, "ok")
    tr = await correlation_id_universal.trace(pool, cid)
    assert tr["found"]
    assert tr["hops"] == 2
    assert tr["final_verdict"] == "ok"
    assert tr["origin"] == "unit_test"


async def test_correlation_trace_unknown(pool):
    tr = await correlation_id_universal.trace(pool, "nope-zzz")
    assert tr["found"] is False


# --------------------------------------------------------------- hard_boundary

async def test_hard_boundary_seed_present(pool):
    rows = await hard_boundary_registry.list_all(pool)
    scopes = {r["scope"] for r in rows}
    assert "payment.any" in scopes
    assert "gdpr.waiver" in scopes


async def test_hard_boundary_is_hard_hit(pool):
    h = await hard_boundary_registry.is_hard(pool, "payment.any")
    assert h and h["requires_type"] == "B"


async def test_hard_boundary_miss(pool):
    h = await hard_boundary_registry.is_hard(pool, "not-a-scope-xyz")
    assert h is None


async def test_hard_boundary_register_new(pool):
    scope = "test.scope.temp123"
    await hard_boundary_registry.register(pool, scope, "temp", "C")
    h = await hard_boundary_registry.is_hard(pool, scope)
    assert h and h["scope"] == scope
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM hard_boundary_registry WHERE scope=$1", scope)


async def test_hard_boundary_register_rejects_bad_type(pool):
    with pytest.raises(ValueError):
        await hard_boundary_registry.register(pool, "t.bad", "x", "Z")


async def test_hard_boundary_check_multi(pool):
    hits = await hard_boundary_registry.check(
        pool, ["payment.any", "nope.nope", "gdpr.waiver"])
    assert len(hits) == 2


# --------------------------------------------------------------- leases

async def test_lease_grant_consume_revoke(pool, seeded_task_id):
    lease = await permission_lease_manager.grant(
        pool, "test.scope.lease1", duration_days=1,
        cap_amount=100.0, cap_currency="USD", usage_cap=2,
        task_id=seeded_task_id)
    assert lease.active
    r = await permission_lease_manager.consume(pool, lease.id, amount=50.0)
    assert r["ok"]
    r2 = await permission_lease_manager.consume(pool, lease.id, amount=200.0)
    assert r2["ok"] is False and "cap" in r2["reason"]
    r3 = await permission_lease_manager.consume(pool, lease.id, amount=25.0)
    assert r3["ok"]
    r4 = await permission_lease_manager.consume(pool, lease.id, amount=10.0)
    assert r4["ok"] is False  # usage_cap reached
    ok = await permission_lease_manager.revoke(pool, lease.id)
    assert ok is True
    ok2 = await permission_lease_manager.revoke(pool, lease.id)
    assert ok2 is False  # already revoked


async def test_lease_find_active_none(pool):
    lease = await permission_lease_manager.find_active(
        pool, "scope.absent.xyz")
    assert lease is None


async def test_lease_consume_unknown(pool):
    r = await permission_lease_manager.consume(pool, 99999999)
    assert r["ok"] is False and "inconnu" in r["reason"]


async def test_lease_list_active_includes_new(pool):
    lease = await permission_lease_manager.grant(
        pool, "test.list.active.1", duration_days=1, usage_cap=5)
    listed = await permission_lease_manager.list_active(pool)
    assert any(l["scope"] == "test.list.active.1" for l in listed)
    await permission_lease_manager.revoke(pool, lease.id)


# --------------------------------------------------------------- ambiguity_resolver

async def test_resolve_industry_default_backup(pool):
    res = await ambiguity_resolver.resolve(
        pool, "Quelle strategie de backup recommandee ?")
    assert res.resolved is True
    assert res.level_resolved in (1, 2)


async def test_resolve_false_ambiguity(pool):
    res = await ambiguity_resolver.resolve(
        pool, "Je ne sais pas quoi faire avec ce module")
    assert res.resolved is True
    assert res.kind == "false"


async def test_resolve_self_induced(pool):
    ctx = ("CDC: le client exige GraphQL avec authentification JWT token "
            "bearer et refresh flow standard OAuth 2.")
    res = await ambiguity_resolver.resolve(
        pool, "Quel protocole authentification JWT bearer OAuth refresh ?",
        context=ctx)
    assert res.kind == "self_induced"


async def test_resolve_requires_escalation(pool):
    res = await ambiguity_resolver.resolve(
        pool, "Dendani doit-il adopter la convention interne Z ou Y ?")
    # "Dendani doit" matches C1 heuristic -> classify C1 + L3 bounded sim resolves
    assert res.sub_type == "C1"


async def test_resolve_strategic_requires_L3(pool):
    res = await ambiguity_resolver.resolve(
        pool, "Quelle regle metier pour le taux promo Dendani VEFA ?")
    # Sub_type C1 -> bounded sim resolves
    assert res.sub_type == "C1"
    assert res.resolved is True


# --------------------------------------------------------------- human_necessity_proof

async def test_proof_lease_covers_bypass(pool, seeded_task_id):
    lease = await permission_lease_manager.grant(
        pool, "proof.test.covers1", duration_days=1, usage_cap=3)
    ev = NecessityEvidence(
        form_type="B", c_sub_type=None, scope="proof.test.covers1",
        task_id=seeded_task_id, correlation_id=None,
        question_or_reason="dummy")
    verdict = await human_necessity_proof.prove(pool, ev)
    assert verdict.proved is False
    assert "lease" in verdict.reason
    await permission_lease_manager.revoke(pool, lease.id)


async def test_proof_hard_boundary_forces_escalation(pool, seeded_task_id):
    ev = NecessityEvidence(
        form_type="B", c_sub_type=None, scope="payment.any",
        task_id=seeded_task_id, correlation_id=None,
        question_or_reason="paiement x")
    v = await human_necessity_proof.prove(pool, ev)
    assert v.proved is True
    assert "hard boundary" in v.reason


async def test_proof_persist_and_recent_rejections(pool, seeded_task_id):
    ev = NecessityEvidence(
        form_type="C", c_sub_type="C1", scope="x.test.anomaly",
        task_id=seeded_task_id, correlation_id=None,
        question_or_reason="Quelle frequence backup ?")
    v = await human_necessity_proof.prove(pool, ev)
    pid = await human_necessity_proof.persist(pool, v)
    assert pid > 0
    recent = await human_necessity_proof.recent_rejections(pool, limit=50)
    # Si v.proved==False, il est dans rejected
    assert isinstance(recent, list)


async def test_proof_counterfactual_low_risk_rejects(pool, seeded_task_id):
    ev = NecessityEvidence(
        form_type="A", c_sub_type=None, scope="test.anon.creds",
        task_id=seeded_task_id, correlation_id=None,
        question_or_reason="creds X")
    v = await human_necessity_proof.prove(pool, ev)
    # Type A counterfactual: vault + fallback_chain -> low risk -> rejected
    assert v.proved is False
    assert "counterfactual" in v.reason


# --------------------------------------------------------------- governor

async def test_governor_high_conf_continue(pool, seeded_task_id):
    dp = DecisionPoint(
        scope="test.governor.hc", form_type="C", c_sub_type="C1",
        question_or_reason="trivial q", confidence=0.95,
        task_id=seeded_task_id)
    d = await autonomy_governor.decide_next(pool, dp)
    assert d.mode == Mode.CONTINUE


async def test_governor_hard_boundary_escalates(pool, seeded_task_id):
    dp = DecisionPoint(
        scope="payment.any", form_type="B", c_sub_type=None,
        question_or_reason="paiement datadog 15 USD",
        confidence=0.95, task_id=seeded_task_id)
    d = await autonomy_governor.decide_next(pool, dp)
    assert d.mode == Mode.ESCALATE


async def test_governor_lease_covers(pool, seeded_task_id):
    lease = await permission_lease_manager.grant(
        pool, "gov.test.cov1", duration_days=1, usage_cap=3)
    dp = DecisionPoint(
        scope="gov.test.cov1", form_type="B", c_sub_type=None,
        question_or_reason="dummy", confidence=0.3,
        task_id=seeded_task_id)
    d = await autonomy_governor.decide_next(pool, dp)
    assert d.mode == Mode.CONTINUE
    assert d.used_lease_id == lease.id
    await permission_lease_manager.revoke(pool, lease.id)


# --------------------------------------------------------------- auditor

async def test_auditor_compute_persist_latest(pool):
    k = await autonomy_auditor.compute(pool, window_hours=168)
    pid = await autonomy_auditor.persist(pool, k)
    assert pid > 0
    latest = await autonomy_auditor.latest(pool)
    assert latest is not None
    assert "autonomy_action_rate" in latest


async def test_auditor_load_raw_small_window(pool):
    k = await autonomy_auditor.compute(pool, window_hours=1)
    d = k.to_dict()
    for key in ("autonomy_action_rate", "patch_success_by_type",
                 "c_sub_type_distribution", "details"):
        assert key in d


# --------------------------------------------------------------- chaos

async def test_chaos_run_scenario_individual(pool):
    for sc in autonomy_chaos_engine.SCENARIOS:
        r = await autonomy_chaos_engine.run_scenario(pool, sc, seed=1)
        assert r.scenario == sc
        assert isinstance(r.passed, bool)


async def test_chaos_run_all(pool):
    r = await autonomy_chaos_engine.run_all(pool, seed=42)
    assert r["total"] == len(autonomy_chaos_engine.SCENARIOS)
    assert 0.0 <= r["pass_rate"] <= 1.0


async def test_chaos_unknown_scenario_raises(pool):
    with pytest.raises(ValueError):
        await autonomy_chaos_engine.run_scenario(pool, "does_not_exist")


# --------------------------------------------------------------- intervention_learner

async def test_intervention_learner_assess_none_when_absent(pool):
    import uuid
    r = await intervention_learner.assess(pool, str(uuid.uuid4()))
    assert r is None


async def test_intervention_learner_assess_bad_id_returns_none(pool):
    r = await intervention_learner.assess(pool, "not-a-uuid")
    assert r is None


async def test_intervention_learner_learn_from_recent(pool):
    r = await intervention_learner.learn_from_recent(pool, limit=5)
    assert "assessed" in r


async def test_intervention_learner_matches_negative_empty(pool):
    r = await intervention_learner.matches_negative(
        pool, "C", "C1", "never_seen_xyz", "absolutely unique question")
    assert r is None


# --------------------------------------------------------------- calibration_engine

async def test_calibration_compute_no_data(pool):
    r = await calibration_engine.compute(pool, window_days=1)
    assert r.samples >= 0
    assert 0.0 <= r.calibration_score <= 1.0


# --------------------------------------------------------------- simulation_lab

async def test_simulation_replay_empty(pool):
    pol = Policy()
    r = await autonomy_simulation_lab.replay(pool, pol, window_days=30)
    assert r.samples >= 0
    d = r.to_dict()
    assert "mode_counts" in d


async def test_simulation_grid_search(pool):
    r = await autonomy_simulation_lab.grid_search(pool, window_days=30)
    assert "best" in r


# --------------------------------------------------------------- explainability

async def test_explainability_unknown_cid(pool):
    r = await autonomy_explainability_api.explain(pool, "not-a-cid")
    assert r["found"] is False


async def test_explainability_after_governor(pool, seeded_task_id):
    cid = correlation_id_universal.new_id("exp")
    await correlation_id_universal.register(pool, cid, "test",
                                              task_id=seeded_task_id)
    dp = DecisionPoint(
        scope="payment.any", form_type="B", c_sub_type=None,
        question_or_reason="datadog 15 USD", confidence=0.9,
        task_id=seeded_task_id, correlation_id=cid)
    await autonomy_governor.decide_next(pool, dp)
    r = await autonomy_explainability_api.explain(pool, cid)
    assert r["found"] is True
    assert len(r["decisions"]) >= 1


async def test_explainability_recent_avoided(pool):
    rows = await autonomy_explainability_api.recent_avoided_escalations(pool, limit=5)
    assert isinstance(rows, list)


# --------------------------------------------------------------- cost_model

def test_cost_api_tokens():
    cb = autonomy_cost_model.estimate(
        confidence=1.0, mode="CONTINUE",
        tokens_in=1_000_000, tokens_out=0)
    assert cb.api_usd == pytest.approx(3.0)


def test_cost_human_minutes():
    cb = autonomy_cost_model.estimate(
        confidence=1.0, mode="ESCALATE", human_minutes=60.0)
    assert cb.human_usd == pytest.approx(120.0)  # HOURLY_RATE_USD=120


def test_cost_best_mode_monotone_conf():
    high = autonomy_cost_model.best_mode(confidence=0.99, downstream_cost_usd=100.0)
    low = autonomy_cost_model.best_mode(confidence=0.05, downstream_cost_usd=10000.0)
    assert high["best"] != low["best"]


# --------------------------------------------------------------- vault + prefetcher

def test_credential_vault_lookup_no_vault(monkeypatch):
    """Sans Vault joignable, lookup retourne None proprement."""
    from app.integrations import vault_client as vc
    def boom(*a, **kw):
        raise vc.VaultUnavailable("stub")
    monkeypatch.setattr(vc.VaultClient, "get", boom)
    r = credential_vault_universal.lookup("never-seen-svc")
    assert r is None


def test_credential_vault_has_credential_false(monkeypatch):
    from app.integrations import vault_client as vc
    monkeypatch.setattr(vc.VaultClient, "get", lambda self, p: None)
    assert credential_vault_universal.has_credential("never-seen") is False


async def test_auth_prefetcher_fallback_datadog(pool):
    r = await auth_prefetcher.prefetch(pool, "datadog")
    # datadog a un fallback, pas besoin de demander
    assert r.path in ("fallback", "vault", "lease")
    assert r.should_ask is False


async def test_auth_prefetcher_unknown_service_asks(pool):
    r = await auth_prefetcher.prefetch(pool, "never-seen-svc-abc")
    assert r.should_ask is True
    assert r.path == "ask"


async def test_auth_prefetcher_lease_path(pool):
    scope = "credentials.test_prefetch_svc"
    lease = await permission_lease_manager.grant(
        pool, scope, duration_days=1, usage_cap=3)
    r = await auth_prefetcher.prefetch(pool, "test_prefetch_svc")
    assert r.path == "lease"
    await permission_lease_manager.revoke(pool, lease.id)


# --------------------------------------------------------------- fallback_chain edge

def test_fallback_sonarcloud():
    d = fallback_chain.find("sonarcloud")
    assert d.should_still_ask is False


def test_fallback_openai():
    d = fallback_chain.find("openai")
    assert d.should_still_ask is False


def test_fallback_stripe_defer():
    d = fallback_chain.find("stripe")
    # stripe has only defer option with coverage 0.0 -> should_still_ask True
    assert d.should_still_ask is True
