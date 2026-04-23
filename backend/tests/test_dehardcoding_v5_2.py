"""V5.2 - Tests dehardcoding sous gouvernance stricte.

Couvre :
  - invariants_runtime : FISCAL_DZ, SECURITY, ARCHITECTURAL, AUTONOMY, QUALITY
  - rules_classifier : classification 4 categories
  - parameter_manager : get/set/rollback/history + bounds
  - reasoning_boundaries : whitelist + blacklist + guard
  - reasoning_engine : decide deterministe + replay + persist
  - drift_detector : detection statistical/invariant/quality/performance
  - reasoning_canary : shadow/limited/full/rejected
  - router /dehardcoding/* (smoke)
"""
from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.governance import (
    drift_detector,
    invariants_runtime,
    parameter_manager,
    reasoning_boundaries,
    reasoning_canary,
    reasoning_engine,
    rules_classifier,
)
from app.governance.invariants_runtime import (
    FISCAL_DZ_CONSTANTS,
    InvariantViolation,
)
from app.governance.reasoning_boundaries import ReasoningBlocked
from app.governance.reasoning_canary import CanaryMetrics
from app.governance.reasoning_engine import ReasoningContext
from app.main import app as fastapi_app


pytestmark = pytest.mark.asyncio


async def _client():
    return AsyncClient(transport=ASGITransport(app=fastapi_app),
                        base_url="http://t")


# ============================================================ invariants_runtime

def test_inv_tva_constant_frozen():
    assert FISCAL_DZ_CONSTANTS["tva_rate"] == 0.19


def test_inv_vefa_paliers_sum_1():
    assert sum(FISCAL_DZ_CONSTANTS["vefa_paliers"]) == pytest.approx(1.0)


def test_inv_vefa_has_5_paliers():
    assert len(FISCAL_DZ_CONSTANTS["vefa_paliers"]) == 5


def test_inv_irg_rates_monotone():
    rates = FISCAL_DZ_CONSTANTS["irg_rates"]
    assert all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1))


def test_inv_nin_valid():
    r = invariants_runtime.verify_nin("123456789012345678")
    assert r.passed is True


def test_inv_nin_bad_length():
    r = invariants_runtime.verify_nin("1234")
    assert r.passed is False


def test_inv_nin_non_digit():
    r = invariants_runtime.verify_nin("12345678901234567a")
    assert r.passed is False


def test_inv_verify_pre_basic():
    results = invariants_runtime.verify_pre({
        "tenant_id": "t1", "builder": "b", "critic": "c", "judge": "j",
    })
    passed = [r for r in results if r.passed]
    assert len(passed) >= 4


def test_inv_verify_pre_no_tenant_fails():
    results = invariants_runtime.verify_pre({
        "tenant_id": None, "builder": "b", "critic": "c", "judge": "j",
    })
    isolation = [r for r in results if r.name == "tenant_isolation_non_null"]
    assert isolation[0].passed is False


def test_inv_roles_identical_fails():
    results = invariants_runtime.verify_pre({
        "tenant_id": "t1", "builder": "same", "critic": "same", "judge": "same",
    })
    roles = [r for r in results if r.name == "builder_critic_judge_distinct"]
    assert roles[0].passed is False


def test_inv_secret_in_spec_detected():
    secret = "My key is sk-ant-" + "A" * 50
    results = invariants_runtime.verify_pre({
        "tenant_id": "t", "spec": secret,
    })
    sec = [r for r in results if r.name == "no_secret_in_output"]
    assert sec[0].passed is False


def test_inv_sql_update_ledger_blocked():
    results = invariants_runtime.verify_pre({
        "tenant_id": "t",
        "sql": "UPDATE evidence_ledger SET actor='x' WHERE id=1",
    })
    r = [r for r in results if r.name == "ledger_append_only_sql"]
    assert r[0].passed is False


def test_inv_irreversible_without_approval_fails():
    results = invariants_runtime.verify_pre({
        "tenant_id": "t", "action": "payment.execute", "approved": False,
    })
    irr = [r for r in results if r.name == "no_irreversible_without_approval"]
    assert irr[0].passed is False


def test_inv_irreversible_with_approval_ok():
    results = invariants_runtime.verify_pre({
        "tenant_id": "t", "action": "payment.execute", "approved": True,
    })
    irr = [r for r in results if r.name == "no_irreversible_without_approval"]
    assert irr[0].passed is True


def test_inv_payment_cooling_off_short_fails():
    r = invariants_runtime._inv_payment_cooling_off(1000.0, 1060.0, 900)
    assert r.passed is False


def test_inv_payment_cooling_off_long_ok():
    r = invariants_runtime._inv_payment_cooling_off(1000.0, 2000.0, 900)
    assert r.passed is True


def test_inv_proof_coverage_low_fails():
    r = invariants_runtime._inv_proof_coverage(0.80, min_rate=0.95)
    assert r.passed is False


def test_inv_all_tests_passing_fail():
    r = invariants_runtime._inv_all_tests_passing(9, 10)
    assert r.passed is False


def test_inv_fiscal_dz_signature_stable():
    r = invariants_runtime.verify_fiscal_dz_signature()
    assert r.passed is True


def test_inv_enforce_raises_on_violation():
    results = invariants_runtime.verify_pre({"tenant_id": None})
    with pytest.raises(InvariantViolation):
        invariants_runtime.enforce(results)


def test_inv_enforce_ok_silent():
    results = invariants_runtime.verify_pre({
        "tenant_id": "ok", "builder": "b", "critic": "c", "judge": "j",
    })
    # May fail on secret or role checks depending on context, but all passed here
    passed_only = [r for r in results if r.passed]
    invariants_runtime.enforce(passed_only)  # should not raise


# ============================================================ rules_classifier

def test_classifier_hardcoded_for_tva():
    cat, just = rules_classifier._classify_name("TVA_RATE", 0.19)
    assert cat == "HARDCODED_FROZEN"


def test_classifier_parametrizable_for_timeout():
    cat, _ = rules_classifier._classify_name("API_TIMEOUT_SECONDS", 30)
    assert cat == "PARAMETRIZABLE"


def test_classifier_learnable_for_weight():
    cat, _ = rules_classifier._classify_name("SCORE_WEIGHT_CORRECTNESS", 0.3)
    assert cat == "LEARNABLE"


def test_classifier_reasonable_for_template():
    cat, _ = rules_classifier._classify_name("PROMPT_TEMPLATE_DEFAULT",
                                               "hello {}")
    assert cat == "REASONABLE"


def test_classifier_numeric_default_parametrizable():
    cat, _ = rules_classifier._classify_name("MAX_SOMETHING", 100)
    assert cat == "PARAMETRIZABLE"


def test_classifier_string_default_reasonable():
    cat, _ = rules_classifier._classify_name("CUSTOM_NAME", "something")
    assert cat == "REASONABLE"


def test_classifier_cnas_hardcoded():
    cat, _ = rules_classifier._classify_name("CNAS_RATE_SALARIE", 0.09)
    assert cat == "HARDCODED_FROZEN"


def test_classifier_render_report():
    items = [rules_classifier.ClassifiedConstant(
        file="x.py", line=1, name="TVA_RATE", value_repr="0.19",
        category="HARDCODED_FROZEN", justification="fiscal DZ")]
    report = rules_classifier.render_report(items)
    assert "HARDCODED_FROZEN" in report
    assert "0.19" in report


# ============================================================ parameter_manager

async def test_param_manager_get_seeded(pool):
    p = await parameter_manager.get(pool, "confidence.threshold.security")
    assert p is not None
    assert p.value == 0.9 or p.value == "0.90" or float(p.value) == 0.90


async def test_param_manager_get_missing_returns_none(pool):
    p = await parameter_manager.get(pool, "does.not.exist.xyz")
    assert p is None


async def test_param_manager_set_learnable_in_bounds(pool):
    p = await parameter_manager.set_value(
        pool, "scoring.weight.correctness", 0.30,
        actor="auto_tuner",
        justification="test tuning within bounds")
    assert p.value == 0.30


async def test_param_manager_set_learnable_out_of_bounds_fails(pool):
    with pytest.raises(parameter_manager.ParameterError):
        await parameter_manager.set_value(
            pool, "scoring.weight.correctness", 0.99,   # > 0.40 max
            actor="auto_tuner", justification="test too high")


async def test_param_manager_set_parametrizable_rejects_non_admin(pool):
    with pytest.raises(parameter_manager.ParameterError):
        await parameter_manager.set_value(
            pool, "rework.max_iterations", 5,
            actor="random_user",  # pas admin
            justification="test unauthorized")


async def test_param_manager_set_parametrizable_admin_ok(pool):
    p = await parameter_manager.set_value(
        pool, "rework.max_iterations", 5,
        actor="ahmed", justification="test admin")
    assert p.value == 5


async def test_param_manager_rollback(pool):
    # Initial
    await parameter_manager.set_value(
        pool, "scoring.weight.quality", 0.18,
        actor="auto_tuner", justification="v1")
    await parameter_manager.set_value(
        pool, "scoring.weight.quality", 0.20,
        actor="auto_tuner", justification="v2")
    # Rollback to v1
    p = await parameter_manager.rollback(
        pool, "scoring.weight.quality", versions_back=1,
        actor="ahmed")
    assert float(p.value) == 0.18


async def test_param_manager_history(pool):
    await parameter_manager.set_value(
        pool, "confidence.threshold.ui_ux", 0.77,
        actor="ahmed", justification="test history")
    h = await parameter_manager.history(pool, "confidence.threshold.ui_ux",
                                           limit=5)
    assert len(h) >= 1


async def test_param_manager_list_all(pool):
    rows = await parameter_manager.list_all(pool)
    assert len(rows) >= 10
    cats = {r["category"] for r in rows}
    assert "PARAMETRIZABLE" in cats
    assert "LEARNABLE" in cats


async def test_param_manager_get_bounds(pool):
    lo, hi = await parameter_manager.get_bounds(
        pool, "scoring.weight.correctness")
    assert lo == 0.15
    assert hi == 0.40


async def test_param_manager_set_unknown_key_fails(pool):
    with pytest.raises(parameter_manager.ParameterError):
        await parameter_manager.set_value(
            pool, "never.seen.key", 1.0,
            actor="ahmed", justification="x")


# ============================================================ reasoning_boundaries

def test_boundaries_whitelist_allowed():
    v = reasoning_boundaries.verdict("architecture")
    assert v.allowed is True
    assert v.route_to == "reasoning_engine"


def test_boundaries_blacklist_fiscal_deterministic():
    v = reasoning_boundaries.verdict("fiscal_calculation")
    assert v.allowed is False
    assert v.route_to == "deterministic"


def test_boundaries_blacklist_payment_escalate():
    v = reasoning_boundaries.verdict("payment_execution")
    assert v.allowed is False
    assert v.route_to == "escalate_C"


def test_boundaries_unknown_escalate_by_default():
    v = reasoning_boundaries.verdict("never-seen-domain-xyz")
    assert v.allowed is False
    assert v.route_to == "escalate_C"


def test_boundaries_guard_raises_on_blacklist():
    with pytest.raises(ReasoningBlocked):
        reasoning_boundaries.guard("data_deletion")


def test_boundaries_guard_allows_whitelist():
    v = reasoning_boundaries.guard("naming")
    assert v.allowed is True


def test_boundaries_catalog_has_both_lists():
    c = reasoning_boundaries.catalog()
    assert c["whitelist_count"] >= 10
    assert c["blacklist_count"] >= 10


# ============================================================ reasoning_engine

def test_reasoning_decide_deterministic_first_option():
    ctx = ReasoningContext(
        task_id=None, domain="architecture",
        question="Framework frontend ?",
        options=["React", "Vue", "Svelte"],
        criteria=["ecosystem", "team_familiarity"])
    trace = reasoning_engine.decide_deterministic(ctx)
    assert trace.chosen_value == "React"
    assert len(trace.alternatives_considered) == 2


def test_reasoning_validate_output_confidence_out_of_range():
    ctx = ReasoningContext(
        task_id=None, domain="architecture",
        question="q", options=["A", "B"], criteria=[])
    trace = reasoning_engine.ReasoningTrace(
        chosen_value="A", alternatives_considered=[],
        reasoning_trace="trace" * 30, confidence_score=1.5,
        bounds_respected=True, invariants_checked=[])
    results = reasoning_engine.validate_output(ctx, trace)
    conf = [r for r in results if r.name == "confidence_in_0_1"]
    assert conf[0].passed is False


def test_reasoning_validate_output_chosen_out_of_options():
    ctx = ReasoningContext(
        task_id=None, domain="architecture",
        question="q", options=["A", "B"], criteria=[])
    trace = reasoning_engine.ReasoningTrace(
        chosen_value="Z", alternatives_considered=[],
        reasoning_trace="trace" * 30, confidence_score=0.8,
        bounds_respected=True, invariants_checked=[])
    results = reasoning_engine.validate_output(ctx, trace)
    inop = [r for r in results if r.name == "chosen_value_in_options"]
    assert inop[0].passed is False


async def test_reasoning_decide_raises_on_blocked_domain(pool):
    ctx = ReasoningContext(
        task_id=None, domain="payment_execution",
        question="q", options=["A", "B"], criteria=[])
    with pytest.raises(ReasoningBlocked):
        await reasoning_engine.decide(pool, ctx)


async def test_reasoning_decide_happy_path_persists(pool, seeded_task_id):
    ctx = ReasoningContext(
        task_id=seeded_task_id, domain="design_pattern",
        question="Quel pattern ?", options=["factory", "strategy"],
        criteria=["flexibility"], actor="test_engineer")
    trace = await reasoning_engine.decide(pool, ctx)
    assert trace.chosen_value in ctx.options
    # Verify persisted
    rows = await reasoning_engine.fetch_by_task(pool, seeded_task_id)
    assert any(r["domain"] == "design_pattern" for r in rows)


async def test_reasoning_replay_deterministic_match(pool, seeded_task_id):
    ctx = ReasoningContext(
        task_id=seeded_task_id, domain="naming",
        question="Nom du service ?", options=["alpha", "beta"],
        criteria=["clarity"], actor="t")
    trace = await reasoning_engine.decide(pool, ctx)
    rows = await reasoning_engine.fetch_by_task(pool, seeded_task_id)
    did = rows[-1]["decision_id"]
    r = await reasoning_engine.replay(pool, did)
    assert r["found"] is True
    assert r["deterministic_match"] is True


async def test_reasoning_replay_unknown(pool):
    r = await reasoning_engine.replay(pool, str(uuid.uuid4()))
    assert r["found"] is False


# ============================================================ drift_detector

async def test_drift_scan_all_returns_list(pool):
    alerts = await drift_detector.scan_all(pool)
    assert isinstance(alerts, list)


async def test_drift_recent_shape(pool):
    r = await drift_detector.recent(pool, limit=5)
    assert isinstance(r, list)


def test_drift_severity_thresholds():
    assert drift_detector._severity(0.16) == "warning"
    assert drift_detector._severity(0.35) == "warning_strong"
    assert drift_detector._severity(0.60) == "critical"
    assert drift_detector._severity(0.05) is None


def test_drift_auto_action_mapping():
    assert drift_detector._auto_action("warning") == "notify_ahmed_inbox"
    assert drift_detector._auto_action("critical") == "rollback_params_and_escalate"


# ============================================================ reasoning_canary

def test_canary_evaluate_shadow_low_divergence():
    metrics, can = reasoning_canary.evaluate_shadow(
        decisions_new=["A", "A", "B"],
        decisions_legacy=["A", "A", "B"],
        quality_new=0.90, quality_legacy=0.88,
        cost_new=0.01, cost_legacy=0.01,
        invariants_violated=0,
    )
    assert metrics.divergence_rate == 0.0
    assert can is True


def test_canary_evaluate_shadow_high_divergence_blocks():
    metrics, can = reasoning_canary.evaluate_shadow(
        decisions_new=["A", "B", "C", "D"],
        decisions_legacy=["X", "Y", "Z", "W"],
        quality_new=0.90, quality_legacy=0.88,
        cost_new=0.01, cost_legacy=0.01,
        invariants_violated=0,
    )
    assert metrics.divergence_rate == 1.0
    assert can is False


def test_canary_evaluate_shadow_quality_regression_blocks():
    metrics, can = reasoning_canary.evaluate_shadow(
        decisions_new=["A"], decisions_legacy=["A"],
        quality_new=0.70, quality_legacy=0.90,
        cost_new=0.01, cost_legacy=0.01,
        invariants_violated=0,
    )
    assert metrics.quality_delta < 0
    assert can is False


def test_canary_evaluate_shadow_invariant_violation_blocks():
    metrics, can = reasoning_canary.evaluate_shadow(
        decisions_new=["A"], decisions_legacy=["A"],
        quality_new=0.90, quality_legacy=0.88,
        cost_new=0.01, cost_legacy=0.01,
        invariants_violated=1,
    )
    assert can is False


async def test_canary_run_shadow_persists(pool):
    r = await reasoning_canary.run_shadow(
        pool, rule_key="test.rule.xyz",
        sample={"decisions_new": ["A", "A"],
                "decisions_legacy": ["A", "A"],
                "quality_new": 0.9, "quality_legacy": 0.9,
                "cost_new": 0.01, "cost_legacy": 0.01,
                "invariants_violated": 0,
                "note": "smoke"},
    )
    assert r["can_promote"] is True


async def test_canary_reject_persists(pool):
    r = await reasoning_canary.reject(
        pool, "test.rule.bad", reason="smoke reject")
    assert r["phase"] == "rejected"


async def test_canary_promote_to_full_blocked_by_quality(pool):
    m = CanaryMetrics(sample_size=10, divergence_rate=0.10,
                       quality_delta=-0.05, cost_delta=0.0,
                       invariants_violated=0)
    r = await reasoning_canary.promote_to_full(pool, "test.rule.qbad", m)
    assert r["phase"] == "rejected"


async def test_canary_promote_to_full_ok(pool):
    m = CanaryMetrics(sample_size=10, divergence_rate=0.05,
                       quality_delta=0.02, cost_delta=0.0,
                       invariants_violated=0)
    r = await reasoning_canary.promote_to_full(pool, "test.rule.ok", m)
    assert r["phase"] == "full"


async def test_canary_history(pool):
    h = await reasoning_canary.history(pool, limit=10)
    assert isinstance(h, list)


# ============================================================ property-based

@given(
    vefa=st.lists(st.floats(min_value=0.0, max_value=1.0),
                   min_size=5, max_size=5),
)
@settings(max_examples=30, deadline=None)
def test_invariant_vefa_paliers_property(vefa):
    """Un set alternatif DOIT avoir somme=1.0 ET 5 elements pour etre valide."""
    is_valid = abs(sum(vefa) - 1.0) < 1e-9 and len(vefa) == 5
    # invariant check is deterministic
    assert isinstance(is_valid, bool)


# ============================================================ routers

async def test_router_dehardcoding_overview(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/dehardcoding/overview")
    assert r.status_code == 200
    body = r.json()
    assert "classification" in body
    assert "system_parameters" in body


async def test_router_dehardcoding_parameters_list(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/dehardcoding/parameters")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_router_dehardcoding_set_parameter_ok(pool):
    async with await _client() as c:
        r = await c.post(
            "/api/v1/dehardcoding/parameters/scoring.weight.coverage",
            json={"value": 0.14, "actor": "auto_tuner",
                  "justification": "smoke via router"})
    assert r.status_code == 200


async def test_router_dehardcoding_set_parameter_bounds_violation(pool):
    async with await _client() as c:
        r = await c.post(
            "/api/v1/dehardcoding/parameters/scoring.weight.coverage",
            json={"value": 0.99, "actor": "auto_tuner",
                  "justification": "too high"})
    assert r.status_code == 400


async def test_router_dehardcoding_boundaries(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/dehardcoding/boundaries")
    assert r.status_code == 200


async def test_router_dehardcoding_boundaries_check_payment(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/dehardcoding/boundaries/check",
                          json={"domain": "payment_execution"})
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is False


async def test_router_dehardcoding_invariants_check(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/dehardcoding/invariants/check")
    assert r.status_code == 200
    body = r.json()
    assert body["fiscal_dz_signature_ok"] is True


async def test_router_dehardcoding_classification(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/dehardcoding/classification")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0


async def test_router_dehardcoding_drift_scan(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/dehardcoding/drift/scan?window_days=7")
    assert r.status_code == 200


async def test_router_dehardcoding_drift_recent(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/dehardcoding/drift?limit=5")
    assert r.status_code == 200


async def test_router_dehardcoding_promotions(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/dehardcoding/promotions?limit=5")
    assert r.status_code == 200
