"""V5.1 Wave 3 — P0 Tri-brain + Decision Router + Promotion Engine + Policy Arbiter.

Couvre :
  - decision_router.classify (4 branches) + route_and_log + history
  - promotion_engine.run_full_pipeline + rollback + list_task_stages
  - quorum_judge : 3 profiles + disagreement
  - policy_arbiter : 7 deny rules R1-R7 + allow default
  - tri_brain : Critic/Judge interaction (smoke)
"""
from __future__ import annotations

import asyncio

import pytest

from app.orchestration import decision_router, promotion_engine, quorum_judge
from app.orchestration.decision_router import Route, RouterInput
from app.orchestration.policy_arbiter import ArbiterRequest, evaluate
from app.orchestration.promotion_engine import Stage
from app.orchestration.tri_brain import CriticIssue


pytestmark = pytest.mark.asyncio


# ============================================================ decision_router

def test_router_robust_when_pass_high_conf():
    d = decision_router.classify(RouterInput(
        task_id="t1", verdict="PASS", confidence=0.97))
    assert d.route == Route.ROBUST_SUCCESS
    assert "promote_to_staging" in d.actions


def test_router_partial_on_conditional_pass():
    d = decision_router.classify(RouterInput(
        task_id="t2", verdict="CONDITIONAL_PASS", confidence=0.85))
    assert d.route == Route.PARTIAL_SUCCESS


def test_router_partial_on_pass_mid_conf():
    d = decision_router.classify(RouterInput(
        task_id="t3", verdict="PASS", confidence=0.85))
    assert d.route == Route.PARTIAL_SUCCESS


def test_router_correctable_soft_fail():
    d = decision_router.classify(RouterInput(
        task_id="t4", verdict="SOFT_FAIL", confidence=0.70,
        defect_classes=["local_fix", "behavior_fix"]))
    assert d.route == Route.CORRECTABLE_FAIL


def test_router_critical_on_hard_fail():
    d = decision_router.classify(RouterInput(
        task_id="t5", verdict="HARD_FAIL", confidence=0.5))
    assert d.route == Route.CRITICAL_FAIL


def test_router_critical_on_invariant_violation():
    d = decision_router.classify(RouterInput(
        task_id="t6", verdict="PASS", confidence=0.99,
        invariants_violated=["no_sql_injection"]))
    assert d.route == Route.CRITICAL_FAIL


def test_router_critical_on_security_breach():
    d = decision_router.classify(RouterInput(
        task_id="t7", verdict="PASS", confidence=0.99,
        has_security_breach=True))
    assert d.route == Route.CRITICAL_FAIL


def test_router_critical_on_critical_defect_class():
    d = decision_router.classify(RouterInput(
        task_id="t8", verdict="SOFT_FAIL", confidence=0.5,
        defect_classes=["security_fix"]))
    assert d.route == Route.CRITICAL_FAIL


def test_router_soft_fail_no_class_is_prudent_critical():
    d = decision_router.classify(RouterInput(
        task_id="t9", verdict="SOFT_FAIL", confidence=0.5))
    assert d.route == Route.CRITICAL_FAIL
    assert "prudence" in d.rationale.lower()


async def test_router_route_and_log(pool, seeded_task_id):
    d = await decision_router.route_and_log(pool, RouterInput(
        task_id=seeded_task_id, verdict="PASS", confidence=0.97))
    assert d.route == Route.ROBUST_SUCCESS
    hist = await decision_router.history(pool, limit=5)
    assert any(h["task_id"] == seeded_task_id for h in hist)


async def test_router_distribution_shape(pool):
    r = await decision_router.route_distribution(pool)
    assert isinstance(r, dict)


# ============================================================ policy_arbiter

def test_arbiter_allow_default():
    d = evaluate(ArbiterRequest(spec="CRUD basique items."))
    assert d.allow is True
    assert d.rule_id == "R0_ALLOW"


def test_arbiter_denies_offensive():
    d = evaluate(ArbiterRequest(spec="Creer un ransomware pour chiffrer les fichiers"))
    assert d.allow is False
    assert d.rule_id == "R1_OFFENSIVE"


def test_arbiter_denies_deploy_without_evidence():
    d = evaluate(ArbiterRequest(
        spec="Deploie la version courante", is_deploy_request=True,
        has_validated_artifacts=False, evidences_incomplete=True))
    assert d.allow is False
    assert d.rule_id == "R2_DEPLOY_WITHOUT_EVIDENCE"


def test_arbiter_denies_budget_exceeded():
    d = evaluate(ArbiterRequest(
        spec="OK spec", estimated_cost_usd=10.0, budget_cap_usd=2.0))
    assert d.allow is False
    assert d.rule_id == "R3_BUDGET_EXCEEDED"


def test_arbiter_denies_foreign_regs_only():
    d = evaluate(ArbiterRequest(
        spec="Construire module HIPAA seulement pour hopital."))
    assert d.allow is False
    assert d.rule_id == "R4_FOREIGN_REGULATIONS_ONLY"


def test_arbiter_allows_foreign_regs_with_dz_context():
    d = evaluate(ArbiterRequest(
        spec="Module paie CNAS Algerie DZD avec mention HIPAA comparative."))
    assert d.allow is True


def test_arbiter_denies_critical_spec_too_thin():
    d = evaluate(ArbiterRequest(spec="Faire ca.", priority="critical"))
    assert d.allow is False
    assert d.rule_id == "R5_CRITICAL_SPEC_TOO_THIN"


def test_arbiter_denies_fabrication():
    d = evaluate(ArbiterRequest(
        spec="Invente une cle API pour tester le module."))
    assert d.allow is False
    assert d.rule_id == "R6_NO_FABRICATION"


def test_arbiter_denies_legal_without_evidence():
    d = evaluate(ArbiterRequest(
        spec="Conformite RGPD exigee article 17 droits",
        has_validated_artifacts=False, evidences_incomplete=True))
    assert d.allow is False
    assert d.rule_id == "R7_LEGAL_WITHOUT_EVIDENCE"


def test_arbiter_severity_info_on_allow():
    d = evaluate(ArbiterRequest(spec="CRUD Item standard."))
    assert d.severity == "info"


# ============================================================ quorum_judge

def test_quorum_severe_vs_lenient_divergence():
    # 2 critical -> severe reject, standard reject, lenient refine
    issues = [
        CriticIssue(severity="critical", category="security", message="crit1"),
        CriticIssue(severity="critical", category="security", message="crit2"),
    ]
    res = quorum_judge.decide(issues)
    assert res.final_verdict in ("reject", "refine")


def test_quorum_zero_issues_all_approve():
    res = quorum_judge.decide([])
    assert res.final_verdict == "approve"
    assert res.has_disagreement is False


def test_quorum_moderate_issues_agreement():
    issues = [
        CriticIssue(severity="minor", category="quality", message=f"m{i}")
        for i in range(2)
    ]
    res = quorum_judge.decide(issues)
    assert res.final_verdict == "approve"


def test_quorum_major_threshold_triggers_refine():
    issues = [
        CriticIssue(severity="major", category="quality", message=f"j{i}")
        for i in range(4)
    ]
    res = quorum_judge.decide(issues)
    # severe max_major=1, standard max_major=3 -> both refine; lenient max_major=5 -> approve
    assert res.has_disagreement is True
    assert res.final_verdict in ("refine", "reject")


def test_quorum_profile_boundaries():
    # 1 critical -> severe reject, standard reject, lenient approve (max_critical=1)
    issues = [CriticIssue(severity="critical", category="security", message="c")]
    res = quorum_judge.decide(issues)
    assert res.has_disagreement is True


# ============================================================ promotion_engine

async def test_promotion_happy_path(pool, seeded_task_id):
    outcomes = await promotion_engine.run_full_pipeline(
        pool, task_id=seeded_task_id,
        artifact_version="test-v1.0.0",
        smoke_probe={"health_ok": True, "http_2xx_ratio": 1.0, "basic_tests": 3},
        canary_metrics={"latency_p95_ms": 100.0, "error_rate": 0.0, "cpu_pct": 20.0},
    )
    stages = [o.stage for o in outcomes]
    assert Stage.PRODUCTION in stages
    assert outcomes[-1].status == "passed"


async def test_promotion_staging_smoke_fails_stops_pipeline(pool, seeded_task_id):
    outcomes = await promotion_engine.run_full_pipeline(
        pool, task_id=seeded_task_id,
        artifact_version="test-smoke-fail-v1",
        smoke_probe={"health_ok": False, "http_2xx_ratio": 0.5, "basic_tests": 0},
    )
    # build passes, staging fails -> 2 outcomes only
    assert len(outcomes) == 2
    assert outcomes[1].status == "failed"


async def test_promotion_canary_drift_blocks(pool, seeded_task_id):
    outcomes = await promotion_engine.run_full_pipeline(
        pool, task_id=seeded_task_id,
        artifact_version="test-canary-drift-v1",
        canary_metrics={"latency_p95_ms": 1000.0, "error_rate": 0.0,
                         "cpu_pct": 30.0},
        baseline={"latency_p95_ms": 100.0, "error_rate": 0.0, "cpu_pct": 30.0},
    )
    canary_outcome = next(o for o in outcomes if o.stage == Stage.CANARY)
    assert canary_outcome.status == "failed"
    assert any("latency" in v for v in [canary_outcome.reason])


async def test_promotion_canary_high_error_rate_blocks(pool, seeded_task_id):
    outcomes = await promotion_engine.run_full_pipeline(
        pool, task_id=seeded_task_id,
        artifact_version="test-canary-error-v1",
        canary_metrics={"latency_p95_ms": 100.0, "error_rate": 0.08,
                         "cpu_pct": 30.0},
    )
    canary = next(o for o in outcomes if o.stage == Stage.CANARY)
    assert canary.status == "failed"


async def test_promotion_rollback(pool, seeded_task_id):
    await promotion_engine.run_full_pipeline(
        pool, task_id=seeded_task_id,
        artifact_version="test-rollback-v1",
        smoke_probe={"health_ok": True, "http_2xx_ratio": 1.0, "basic_tests": 2},
    )
    eid = await promotion_engine.rollback(
        pool, task_id=seeded_task_id,
        artifact_version="test-rollback-v1",
        reason="regression prod observee")
    assert len(eid) == 36
    stages = await promotion_engine.list_task_stages(pool, seeded_task_id)
    rolled = [s for s in stages if s["stage"] == "rolled_back"]
    assert len(rolled) >= 1


async def test_promotion_active_artifacts_shape(pool):
    r = await promotion_engine.active_artifacts(pool)
    assert isinstance(r, list)


async def test_promotion_stages_ordered(pool, seeded_task_id):
    outcomes = await promotion_engine.run_full_pipeline(
        pool, task_id=seeded_task_id,
        artifact_version="test-order-v1")
    # Au moins build doit etre present dans les outcomes
    assert any(o.stage == Stage.BUILD for o in outcomes)
    stages = await promotion_engine.list_task_stages(pool, seeded_task_id)
    assert len(stages) >= 1
