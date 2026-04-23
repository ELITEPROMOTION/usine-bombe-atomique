"""Tests V4.4 : decision_router, promotion_engine, runtime_mesh (core).

Les tests qui touchent la BDD sont marques avec asyncio + pool mock inutile :
on exerce ici uniquement la logique pure deterministe.
"""
from __future__ import annotations

import pytest

from app.orchestration.decision_router import (
    CORRECTABLE_CLASSES, CRITICAL_CLASSES, Route, RouterInput, classify,
)
from app.orchestration.promotion_engine import (
    STAGE_ORDER, Stage, _gate_canary, _gate_staging_smoke,
)
from app.orchestration.runtime_mesh import DriftAlert, _percentile, detect_drift


# -------- decision_router -----------

def test_router_robust_success():
    d = classify(RouterInput(task_id="t", verdict="PASS", confidence=0.96))
    assert d.route == Route.ROBUST_SUCCESS
    assert "promote_to_staging" in d.actions


def test_router_partial_success_conditional_pass():
    d = classify(RouterInput(task_id="t", verdict="CONDITIONAL_PASS", confidence=0.88))
    assert d.route == Route.PARTIAL_SUCCESS
    assert "notify_ceo" in d.actions


def test_router_partial_success_low_confidence():
    d = classify(RouterInput(task_id="t", verdict="PASS", confidence=0.85))
    assert d.route == Route.PARTIAL_SUCCESS


def test_router_correctable_local_fix():
    d = classify(RouterInput(
        task_id="t", verdict="SOFT_FAIL", confidence=0.70,
        defect_classes=["local_fix"],
    ))
    assert d.route == Route.CORRECTABLE_FAIL
    assert "tri_brain_remediation" in d.actions


def test_router_correctable_contract_fix():
    d = classify(RouterInput(
        task_id="t", verdict="SOFT_FAIL", confidence=0.72,
        defect_classes=["contract_fix", "behavior_fix"],
    ))
    assert d.route == Route.CORRECTABLE_FAIL


def test_router_critical_hard_fail():
    d = classify(RouterInput(task_id="t", verdict="HARD_FAIL", confidence=0.50))
    assert d.route == Route.CRITICAL_FAIL
    assert "rollback_immediate" in d.actions
    assert "escalate_human" in d.actions


def test_router_critical_invariant_violated():
    d = classify(RouterInput(
        task_id="t", verdict="PASS", confidence=0.98,
        invariants_violated=["no_hardcoded_secret"],
    ))
    assert d.route == Route.CRITICAL_FAIL


def test_router_critical_security_breach():
    d = classify(RouterInput(
        task_id="t", verdict="PASS", confidence=0.99,
        has_security_breach=True,
    ))
    assert d.route == Route.CRITICAL_FAIL


def test_router_security_fix_defect_is_critical():
    d = classify(RouterInput(
        task_id="t", verdict="SOFT_FAIL", confidence=0.75,
        defect_classes=["security_fix"],
    ))
    assert d.route == Route.CRITICAL_FAIL


def test_router_soft_fail_without_class_is_critical():
    """Principe de prudence : SOFT_FAIL sans defaut classifie = critical."""
    d = classify(RouterInput(task_id="t", verdict="SOFT_FAIL", confidence=0.70))
    assert d.route == Route.CRITICAL_FAIL


def test_router_boundary_confidence_094_is_partial():
    d = classify(RouterInput(task_id="t", verdict="PASS", confidence=0.94))
    assert d.route == Route.PARTIAL_SUCCESS


def test_router_boundary_confidence_095_exact_is_robust():
    d = classify(RouterInput(task_id="t", verdict="PASS", confidence=0.95))
    assert d.route == Route.ROBUST_SUCCESS


def test_correctable_classes_defined():
    assert CORRECTABLE_CLASSES == {"local_fix", "contract_fix", "behavior_fix"}


def test_critical_classes_defined():
    assert "security_fix" in CRITICAL_CLASSES
    assert "schema_fix" in CRITICAL_CLASSES


# -------- promotion_engine (stage ordering) -----------

def test_stage_order_strict():
    assert STAGE_ORDER == (Stage.BUILD, Stage.STAGING, Stage.CANARY, Stage.PRODUCTION)


def test_stage_enum_values():
    assert Stage.BUILD.value == "build"
    assert Stage.ROLLED_BACK.value == "rolled_back"


@pytest.mark.asyncio
async def test_canary_rejects_error_rate_over_5pct():
    """Test pur sans BDD : on passe un pool stub."""

    class StubTx:
        async def __aenter__(self): return None
        async def __aexit__(self, *args): return None

    class StubConn:
        async def execute(self, *args, **kwargs): return None
        async def fetchrow(self, *args, **kwargs):
            # event_id attendu par evidence_ledger.record
            return {"chain_hash": "0" * 64,
                    "event_id": "00000000-0000-0000-0000-000000000000"}
        def transaction(self): return StubTx()

    class StubAcquire:
        async def __aenter__(self): return StubConn()
        async def __aexit__(self, *args): return None

    class StubPool:
        def acquire(self): return StubAcquire()

    # canary_metrics avec error_rate 10% -> doit fail
    outcome = await _gate_canary(
        StubPool(), task_id="00000000-0000-0000-0000-000000000000",
        artifact_version="abc", canary_metrics={
            "latency_p95_ms": 250.0, "error_rate": 0.10, "cpu_pct": 30.0,
        },
    )
    assert outcome.status == "failed"
    assert "error_rate" in outcome.reason


@pytest.mark.asyncio
async def test_staging_smoke_passes_on_health_ok():
    class StubTx:
        async def __aenter__(self): return None
        async def __aexit__(self, *args): return None

    class StubConn:
        async def execute(self, *args, **kwargs): return None
        async def fetchrow(self, *args, **kwargs):
            # event_id attendu par evidence_ledger.record
            return {"chain_hash": "0" * 64,
                    "event_id": "00000000-0000-0000-0000-000000000000"}
        def transaction(self): return StubTx()

    class StubAcquire:
        async def __aenter__(self): return StubConn()
        async def __aexit__(self, *args): return None

    class StubPool:
        def acquire(self): return StubAcquire()

    outcome = await _gate_staging_smoke(
        StubPool(), "00000000-0000-0000-0000-000000000000", "av",
        {"health_ok": True, "http_2xx_ratio": 1.0, "basic_tests": 3},
    )
    assert outcome.status == "passed"
    assert outcome.next_stage == Stage.CANARY


@pytest.mark.asyncio
async def test_staging_smoke_fails_on_ratio_below_95():
    class StubTx:
        async def __aenter__(self): return None
        async def __aexit__(self, *args): return None

    class StubConn:
        async def execute(self, *args, **kwargs): return None
        async def fetchrow(self, *args, **kwargs):
            # event_id attendu par evidence_ledger.record
            return {"chain_hash": "0" * 64,
                    "event_id": "00000000-0000-0000-0000-000000000000"}
        def transaction(self): return StubTx()

    class StubAcquire:
        async def __aenter__(self): return StubConn()
        async def __aexit__(self, *args): return None

    class StubPool:
        def acquire(self): return StubAcquire()

    outcome = await _gate_staging_smoke(
        StubPool(), "00000000-0000-0000-0000-000000000000", "av",
        {"health_ok": True, "http_2xx_ratio": 0.85, "basic_tests": 3},
    )
    assert outcome.status == "failed"


# -------- runtime_mesh -----------

def test_percentile_simple():
    assert _percentile([10, 20, 30, 40, 50], 0.95) == 50
    assert _percentile([], 0.95) == 0.0


def test_percentile_ignores_zero():
    """Les probes avec latence=0 sont ignorees (echec)."""
    assert _percentile([0, 0, 100], 0.95) == 100


def test_drift_alert_serialization():
    a = DriftAlert(target="backend", metric="latency_p95_ms",
                    value=400.0, baseline=200.0, drift_pct=1.0)
    d = a.to_dict()
    assert d["target"] == "backend"
    assert d["drift_pct"] == 100.0  # +100%


@pytest.mark.asyncio
async def test_detect_drift_returns_empty_when_no_baseline():
    """Sans baseline stockee, aucun drift possible."""

    class StubConn:
        async def fetch(self, *args, **kwargs): return []
        async def execute(self, *args, **kwargs): return None

    class StubAcquire:
        async def __aenter__(self): return StubConn()
        async def __aexit__(self, *args): return None

    class StubPool:
        def acquire(self): return StubAcquire()

    alerts = await detect_drift(StubPool(), "backend",
                                  {"latency_p95_ms": 1000.0})
    assert alerts == []


# -------- integration defect class derivation ---------

def test_worker_derive_defect_classes_security_high():
    from app.agents.base_agent import AgentResult
    from app.worker import _derive_defect_classes, _has_security_breach

    results = {
        "agent-02-sonarqube": AgentResult(
            agent_id="agent-02-sonarqube", agent_name="SonarQube",
            status="success", output={"severity_counts": {"HIGH": 2}},
        ),
        "agent-04-pytest": AgentResult(
            agent_id="agent-04-pytest", agent_name="Pytest",
            status="success", output={"tests_failed": 3},
        ),
    }
    classes = _derive_defect_classes(results)
    assert "security_fix" in classes
    assert "behavior_fix" in classes


def test_worker_detects_security_breach():
    from app.agents.base_agent import AgentResult
    from app.worker import _has_security_breach

    results = {
        "agent-11-security": AgentResult(
            agent_id="agent-11-security", agent_name="Security",
            status="success", output={"secrets_count": 1},
        ),
    }
    assert _has_security_breach(results) is True


def test_worker_no_breach_on_zero_secrets():
    from app.agents.base_agent import AgentResult
    from app.worker import _has_security_breach

    results = {
        "agent-11-security": AgentResult(
            agent_id="agent-11-security", agent_name="Security",
            status="success", output={"secrets_count": 0},
        ),
    }
    assert _has_security_breach(results) is False
