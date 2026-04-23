"""Tests V4 : auto_tuner, marketplace, self_improver, escalator."""
from app.orchestration.auto_tuner import (
    DEFAULT_CPASS_MIN, DEFAULT_PASS_MIN, compute_thresholds,
)
from app.orchestration.escalator import detect_question
from app.orchestration.marketplace import classify
from app.orchestration.self_improver import Proposal


def test_auto_tuner_defaults_when_sparse():
    t = compute_thresholds([0.9, 0.95], [0.9, 0.95], scope="global")
    assert t.pass_min == DEFAULT_PASS_MIN
    assert t.cpass_min == DEFAULT_CPASS_MIN


def test_auto_tuner_recalibrates_with_history():
    scores = [0.88, 0.92, 0.95, 0.97, 0.85, 0.90, 0.93, 0.96, 0.89]
    t = compute_thresholds(scores, scores, scope="global")
    assert t.sample_count == 9
    assert 0.80 <= t.pass_min <= 0.92
    # Ordre strict maintenu
    assert t.cpass_min < t.pass_min
    assert t.soft_fail_min < t.cpass_min


def test_marketplace_classify_new_healthy_atrisk_deprecated():
    assert classify(executions=1, success_rate=1.0, avg_score=1.0) == "new"
    assert classify(executions=10, success_rate=0.95, avg_score=0.90) == "healthy"
    assert classify(executions=10, success_rate=0.80, avg_score=0.85) == "at_risk"
    assert classify(executions=10, success_rate=0.60, avg_score=0.90) == "deprecated"
    assert classify(executions=10, success_rate=0.95, avg_score=0.40) == "deprecated"


def test_proposal_signature_stable():
    p1 = Proposal("error_pattern", "high", "X", "r", {"k": 1})
    p2 = Proposal("error_pattern", "medium", "X", "other", {"k": 2})
    p3 = Proposal("cost", "low", "X", "r", {"k": 1})
    assert p1.signature() == p2.signature()
    assert p1.signature() != p3.signature()


def test_escalator_short_spec_asks_domain():
    q = detect_question("CRUD api")
    assert q is not None
    assert q.category == "spec_too_short"


def test_escalator_detects_dz_without_constants():
    q = detect_question(
        "Module pour la gestion en Algerie avec processus de reporting avances et tableaux " * 2,
        priority="high",
    )
    assert q is not None and q.category == "dz_constants_missing"


def test_escalator_passes_complete_spec():
    q = detect_question(
        "Module Paie Algerie avec TVA 19%, TAP 2%, CNAS 9% et IRG bareme. Entites Employe,"
        " RubriquePaie, FichePaie. Endpoints CRUD + /paie/generer + /g50.", priority="high")
    assert q is None


def test_escalator_critical_missing_sla():
    spec = "CRUD API pour produits avec tests pytest et docker compose complet " * 3
    q = detect_question(spec, priority="critical")
    assert q is not None and q.category == "critical_missing_sla"
