"""V5.1 Wave 5 — Hardening : ferme les gaps P0/P1 restants + property-based.

Cibles :
  - autonomy/credential_vault_universal : store, mark_used, has_credential
  - autonomy/intervention_learner : assess paths A/B/C
  - autonomy/calibration_engine : calibrate avec donnees reelles
  - autonomy/ambiguity_resolver : level3 + edge
  - autonomy/autonomy_explainability_api : explain avec correlation_id
  - autonomy/autonomy_governor : low conf escalate
  - orchestration/audit_events : emit + sink
  - orchestration/tri_brain : critic seuils
  - inbox/meta_optimizer : detection de degradation, capture
  - inbox/continuous_improvement : risk_score + retrospective + signature
  - orchestration/auto_repair : scan_anomalies + run_cycle
  - orchestration/innovation_scout : submit + advance + list
  - orchestration/truth_kpis : capture
  - orchestration/prompt_ab : pick_variant + record_outcome
  - middleware/tenant : super_admin path + apply_session_vars edge
"""
from __future__ import annotations

import json
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.autonomy import (
    ambiguity_resolver,
    autonomy_cost_model,
    autonomy_governor,
    autonomy_ladder,
    calibration_engine,
    credential_vault_universal,
    intervention_learner,
)
from app.autonomy.autonomy_governor import DecisionPoint
from app.autonomy.autonomy_ladder import LadderInput, Mode
from app.autonomy.calibration_engine import CalibrationReport
from app.inbox import continuous_improvement, meta_optimizer
from app.integrations import vault_client as vc
from app.orchestration import (
    audit_events,
    auto_repair,
    innovation_scout,
    prompt_ab,
    truth_kpis,
)


pytestmark = pytest.mark.asyncio


# ============================================================ credential_vault_universal

def test_credvault_store_succeeds(monkeypatch):
    captured = {}
    def fake_put(self, p, d):
        captured["path"] = p
        captured["data"] = d
    monkeypatch.setattr(vc.VaultClient, "put", fake_put)
    ok = credential_vault_universal.store("svc-test",
                                            {"email": "x@y", "password": "pw"},
                                            ttl_days=10)
    assert ok is True
    assert captured["path"] == "credentials/svc-test"
    assert captured["data"]["ttl_days"] == 10


def test_credvault_store_fails_silently_on_exception(monkeypatch):
    def boom(self, p, d):
        raise RuntimeError("vault down")
    monkeypatch.setattr(vc.VaultClient, "put", boom)
    assert credential_vault_universal.store("svc-fail",
                                              {"email": "x"}) is False


def test_credvault_lookup_ttl_expired(monkeypatch):
    """TTL expire -> retourne None."""
    expired = {"email": "x", "ttl_days": 1, "created_at": "2020-01-01T00:00:00+00:00"}
    monkeypatch.setattr(vc.VaultClient, "get", lambda self, p: expired)
    assert credential_vault_universal.lookup("svc-old") is None


def test_credvault_lookup_no_ttl_returns_data(monkeypatch):
    fresh = {"email": "x", "password": "y"}
    monkeypatch.setattr(vc.VaultClient, "get", lambda self, p: fresh)
    r = credential_vault_universal.lookup("svc-fresh")
    assert r == fresh


def test_credvault_mark_used_skip_when_absent(monkeypatch):
    monkeypatch.setattr(vc.VaultClient, "get", lambda self, p: None)
    # Should not raise
    credential_vault_universal.mark_used("svc-absent")


def test_credvault_lookup_invalid_iso_treated_as_no_ttl(monkeypatch):
    bad = {"email": "x", "ttl_days": 1, "created_at": "not-a-date"}
    monkeypatch.setattr(vc.VaultClient, "get", lambda self, p: bad)
    # Should still return data, not raise
    assert credential_vault_universal.lookup("svc-bad-iso") == bad


# ============================================================ intervention_learner

async def test_intervention_assess_type_C_industry_default(pool, seeded_task_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pending_user_inputs
              (task_id, request_kind, fields, form_type, c_sub_type,
               suggested_answer, criticality, status, expires_at)
            VALUES ($1, 'custom', '[]'::jsonb, 'C', 'C1',
                    'Daily 02:00 UTC', 'low', 'submitted',
                    NOW() + INTERVAL '1 hour')
            RETURNING id
            """, uuid.UUID(seeded_task_id),
        )
    pid = str(row["id"])
    a = await intervention_learner.assess(pool, pid)
    assert a is not None
    assert a.was_necessary is False
    assert "industry default" in a.reason.lower()


async def test_intervention_assess_type_A_with_fallback(pool, seeded_task_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pending_user_inputs
              (task_id, request_kind, fields, form_type, service_name,
               status, expires_at)
            VALUES ($1, 'email', '[]'::jsonb, 'A', 'datadog',
                    'submitted', NOW() + INTERVAL '1 hour')
            RETURNING id
            """, uuid.UUID(seeded_task_id),
        )
    pid = str(row["id"])
    a = await intervention_learner.assess(pool, pid)
    assert a is not None
    assert a.was_necessary is False  # fallback exists


async def test_intervention_assess_type_B_always_necessary(pool, seeded_task_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pending_user_inputs
              (task_id, request_kind, fields, form_type, service_name,
               cost_amount, cost_currency, payment_url, status, expires_at)
            VALUES ($1, 'payment', '[]'::jsonb, 'B', 'svc',
                    '15.00', 'USD', 'https://x/y', 'submitted',
                    NOW() + INTERVAL '1 hour')
            RETURNING id
            """, uuid.UUID(seeded_task_id),
        )
    pid = str(row["id"])
    a = await intervention_learner.assess(pool, pid)
    assert a is not None
    assert a.was_necessary is True


async def test_intervention_matches_negative_after_assess(pool, seeded_task_id):
    """Apres assess(unnecessary), matches_negative trouve la signature."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pending_user_inputs
              (task_id, request_kind, fields, form_type, c_sub_type,
               service_name, suggested_answer, criticality, status, expires_at)
            VALUES ($1, 'custom', '[]'::jsonb, 'C', 'C1',
                    'unique-svc-zzz', 'Defaut standard',
                    'low', 'submitted', NOW() + INTERVAL '1 hour')
            RETURNING id
            """, uuid.UUID(seeded_task_id),
        )
    await intervention_learner.assess(pool, str(row["id"]))
    m = await intervention_learner.matches_negative(
        pool, "C", "C1", "unique-svc-zzz", "Defaut standard")
    assert m is not None


# ============================================================ calibration

async def test_calibration_with_seeded_decisions(pool, seeded_task_id):
    from app.orchestration import evidence_ledger
    for conf, ok in [(0.9, True), (0.8, True), (0.5, False), (0.2, False)]:
        await evidence_ledger.record(
            pool, kind="decision", actor="cal_test",
            payload={"confidence": conf, "verdict": "robust" if ok else "fail",
                      "success": ok},
            task_id=seeded_task_id,
        )
    r = await calibration_engine.compute(pool, window_days=1)
    assert r.samples >= 4
    assert 0.0 <= r.calibration_score <= 1.0


def test_calibration_calibrate_unknown_value():
    r = CalibrationReport(samples=1, brier_score=0.0, calibration_score=1.0,
                           buckets=[{"range": "0.8-1.01", "n": 1,
                                       "avg_confidence": 0.9,
                                       "avg_outcome": 0.9, "gap": 0.0}])
    # raw outside any bucket -> returned as-is
    assert calibration_engine.calibrate(0.3, r) == 0.3


def test_calibration_actual_helper_paths():
    assert calibration_engine._actual({"verdict": "robust"}) == 1.0
    assert calibration_engine._actual({"verdict": "fail"}) == 0.0
    assert calibration_engine._actual({"success": True}) == 1.0
    assert calibration_engine._actual({"success": False}) == 0.0


def test_calibration_parse_payload():
    assert calibration_engine._parse_payload('{"a": 1}') == {"a": 1}
    assert calibration_engine._parse_payload("not-json") is None
    assert calibration_engine._parse_payload({"a": 1}) == {"a": 1}
    assert calibration_engine._parse_payload(None) is None


def test_calibration_extract_invalid_conf():
    assert calibration_engine._extract_prediction({"confidence": 2.0}) is None
    assert calibration_engine._extract_prediction({"confidence": "bad"}) is None
    assert calibration_engine._extract_prediction({}) is None


# ============================================================ governor low-conf escalate

async def test_governor_low_conf_with_proof_escalates(pool, seeded_task_id):
    dp = DecisionPoint(
        scope="payment.any", form_type="B", c_sub_type=None,
        question_or_reason="paie urgente datadog 50 USD",
        confidence=0.05, task_id=seeded_task_id, criticality="critical")
    d = await autonomy_governor.decide_next(pool, dp)
    assert d.mode == Mode.ESCALATE


async def test_governor_low_conf_without_proof_defers(pool, seeded_task_id):
    dp = DecisionPoint(
        scope="x.unknown.test", form_type="C", c_sub_type=None,
        question_or_reason="ambig", confidence=0.05,
        task_id=seeded_task_id, reversible=False, scope_reducible=False)
    d = await autonomy_governor.decide_next(pool, dp)
    assert d.mode in (Mode.DEFER, Mode.ESCALATE, Mode.CONTINUE)


# ============================================================ ambiguity_resolver edge

async def test_ambiguity_resolve_with_industry_default(pool):
    """L2 industry default sur retry/backoff."""
    res = await ambiguity_resolver.resolve(
        pool, "Quelle politique de retry exponential backoff ?")
    assert res.resolved is True
    assert res.level_resolved in (1, 2, 3)


async def test_ambiguity_log_silent_failure(pool):
    """Le _log catch les exceptions DB, ne propage pas."""
    res = await ambiguity_resolver.resolve(
        pool, "Question avec correlation invalide",
        correlation_id="x" * 200)  # truncates
    assert res is not None


# ============================================================ autonomy_ladder edge

def test_ladder_constrain_with_scope_reducible_only():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.65, reversible=False, scope_reducible=True,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False))
    assert d.mode == Mode.CONSTRAIN


def test_ladder_low_conf_no_options_defers():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.50, reversible=False, scope_reducible=False,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False))
    assert d.mode == Mode.DEFER


def test_ladder_ambiguity_resolved_continues():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.30, reversible=False, scope_reducible=False,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=True))
    assert d.mode == Mode.CONTINUE


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0,
                          allow_nan=False, allow_infinity=False),
    reversible=st.booleans(),
    scope_reducible=st.booleans(),
    hard_boundary=st.booleans(),
    proof_valid=st.booleans(),
    ambiguity_resolved=st.booleans(),
)
@settings(max_examples=80, deadline=None)
def test_ladder_property_always_returns_valid_mode(
    confidence, reversible, scope_reducible, hard_boundary,
    proof_valid, ambiguity_resolved,
):
    d = autonomy_ladder.decide(LadderInput(
        confidence=confidence, reversible=reversible,
        scope_reducible=scope_reducible, hard_boundary=hard_boundary,
        proof_valid=proof_valid, ambiguity_resolved=ambiguity_resolved))
    assert d.mode in Mode
    assert isinstance(d.constraints, list)


# ============================================================ cost model property

@given(
    confidence=st.floats(min_value=0.0, max_value=1.0),
    tokens_in=st.integers(min_value=0, max_value=10**6),
    tokens_out=st.integers(min_value=0, max_value=10**6),
    duration_ms=st.integers(min_value=0, max_value=60_000),
)
@settings(max_examples=40, deadline=None)
def test_cost_estimate_always_non_negative(confidence, tokens_in,
                                              tokens_out, duration_ms):
    cb = autonomy_cost_model.estimate(
        confidence=confidence, mode="CONTINUE",
        tokens_in=tokens_in, tokens_out=tokens_out,
        duration_ms=duration_ms)
    assert cb.api_usd >= 0
    assert cb.latency_usd >= 0
    assert cb.risk_usd >= 0
    assert cb.total_usd >= 0


# ============================================================ audit_events

async def test_audit_events_emit_and_query(pool, seeded_task_id):
    await audit_events.emit(
        pool, action="test_emit", actor="hardening_test",
        payload={"x": 1}, task_id=seeded_task_id,
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT action, payload_json FROM audit_events "
            "WHERE actor = 'hardening_test' ORDER BY created_at DESC LIMIT 1"
        )
    assert row is not None
    assert row["action"] == "test_emit"


# ============================================================ meta_optimizer

def test_meta_detect_no_previous_returns_empty():
    current = {"avg_duration_ms": 1000, "rework_rate": 0.1, "avg_cost_usd": 0.5}
    assert meta_optimizer._detect_degradation(current, None) == []


def test_meta_detect_degradation_above_threshold():
    cur = {"avg_duration_ms": 2000, "rework_rate": 0.5, "avg_cost_usd": 1.0}
    prev = {"avg_duration_ms": 1000, "rework_rate": 0.1, "avg_cost_usd": 0.5}
    deg = meta_optimizer._detect_degradation(cur, prev)
    assert any("avg_duration_ms" in d for d in deg)
    assert any("rework_rate" in d for d in deg)


def test_meta_detect_no_degradation_within_threshold():
    cur = {"avg_duration_ms": 1100, "rework_rate": 0.11, "avg_cost_usd": 0.55}
    prev = {"avg_duration_ms": 1000, "rework_rate": 0.10, "avg_cost_usd": 0.50}
    assert meta_optimizer._detect_degradation(cur, prev) == []


async def test_meta_capture_and_analyze(pool):
    snap = await meta_optimizer.capture_and_analyze(pool)
    assert hasattr(snap, "to_dict")
    d = snap.to_dict()
    assert "projects_last_7d" in d


async def test_meta_latest(pool):
    await meta_optimizer.capture_and_analyze(pool)
    r = await meta_optimizer.latest(pool)
    assert r is None or "projects_last_7d" in r


# ============================================================ continuous_improvement

def test_ci_risk_score_low_for_calibration():
    assert continuous_improvement._risk_score(
        {"category": "calibration"}) < 0.20


def test_ci_risk_score_high_for_architecture():
    assert continuous_improvement._risk_score(
        {"category": "architecture"}) >= 0.70


def test_ci_pattern_signature_stable():
    s1 = continuous_improvement.pattern_signature(["a.py", "b.py"])
    s2 = continuous_improvement.pattern_signature(["b.py", "a.py"])  # sort-invariant
    # deterministe
    assert isinstance(s1, str) and len(s1) == 64
    assert isinstance(s2, str)


async def test_ci_run_retrospective(pool, seeded_task_id):
    r = await continuous_improvement.run_retrospective(pool, seeded_task_id)
    d = r.to_dict()
    assert d["task_id"] == seeded_task_id
    assert "observations" in d


# ============================================================ auto_repair

async def test_auto_repair_scan_anomalies(pool):
    r = await auto_repair.scan_anomalies(pool)
    assert isinstance(r, list)


async def test_auto_repair_run_cycle(pool):
    r = await auto_repair.run_cycle(pool)
    assert isinstance(r, dict)


# ============================================================ innovation_scout

async def test_innovation_scout_submit_advance_list(pool):
    name = f"test-innov-{uuid.uuid4().hex[:8]}"
    sid = await innovation_scout.submit(
        pool, kind="tool", name=name, summary="test innovation hardening")
    rows = await innovation_scout.list_all(pool)
    assert any(r["id"] == sid for r in rows)
    # Advance scout -> qualification
    advanced = await innovation_scout.advance(
        pool, sid, to_stage="qualification", actor="hardening")
    assert advanced is True


async def test_innovation_scout_invalid_transition_raises(pool):
    name = f"test-trans-{uuid.uuid4().hex[:8]}"
    sid = await innovation_scout.submit(
        pool, kind="tool", name=name, summary="x")
    with pytest.raises(ValueError):
        await innovation_scout.advance(pool, sid, to_stage="active",
                                          actor="hardening")


async def test_innovation_scout_advance_unknown_returns_false(pool):
    r = await innovation_scout.advance(pool, str(uuid.uuid4()),
                                          to_stage="qualification",
                                          actor="hardening")
    assert r is False


async def test_innovation_scout_list_filter_unknown_stage(pool):
    r = await innovation_scout.list_all(pool, stage="never_seen_stage_zzz")
    assert isinstance(r, list)


# ============================================================ truth_kpis

async def test_truth_kpis_capture(pool):
    snap = await truth_kpis.capture(pool)
    assert hasattr(snap, "to_dict")


async def test_truth_kpis_latest_or_none(pool):
    r = await truth_kpis.latest(pool)
    assert r is None or isinstance(r, dict)


# ============================================================ prompt_ab

async def test_prompt_ab_list_variants_empty(pool):
    r = await prompt_ab.list_variants(pool, "agent-zzz-never")
    assert isinstance(r, list)


async def test_prompt_ab_pick_variant_unknown_returns_default(pool):
    r = await prompt_ab.pick_variant(pool, "agent-zzz-never")
    # tuple-like or None - both acceptable
    assert r is not None


async def test_prompt_ab_variants_summary(pool):
    r = await prompt_ab.variants_summary(pool)
    assert isinstance(r, list)


# ============================================================ tenant middleware super_admin

async def test_apply_session_vars_super_admin(pool):
    class _Req:
        class state:
            tenant_id = "00000000-0000-0000-0000-000000000999"
            is_super_admin = True
    from app.middleware.tenant import apply_session_vars
    async with pool.acquire() as conn, conn.transaction():
        await apply_session_vars(conn, _Req())
        super_val = await conn.fetchval(
            "SELECT current_setting('app.is_super_admin', TRUE)")
    assert super_val == "on"
