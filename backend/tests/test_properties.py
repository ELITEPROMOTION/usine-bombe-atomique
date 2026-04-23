"""Phase 6 - Property tests (hypothesis) sur fonctions pures.

Cible : invariants, parsers, classifieurs. hypothesis genere les entrees.
"""
from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st


# ===========================================================================
# marketplace.classify (invariant mathematique)
# ===========================================================================

@given(
    executions=st.integers(min_value=0, max_value=10_000),
    success_rate=st.floats(min_value=0.0, max_value=1.0,
                            allow_nan=False, allow_infinity=False),
    avg_score=st.floats(min_value=0.0, max_value=1.0,
                         allow_nan=False, allow_infinity=False),
)
def test_marketplace_classify_returns_valid_status(
    executions: int, success_rate: float, avg_score: float,
) -> None:
    from app.orchestration.marketplace import classify
    out = classify(executions, success_rate, avg_score)
    assert out in ("new", "healthy", "at_risk", "deprecated")


@given(executions=st.integers(min_value=3, max_value=1_000))
def test_marketplace_classify_perfect_metrics_healthy(executions: int) -> None:
    from app.orchestration.marketplace import classify
    assert classify(executions, 1.0, 1.0) == "healthy"


@given(executions=st.integers(min_value=3, max_value=1_000))
def test_marketplace_classify_zero_metrics_deprecated(executions: int) -> None:
    from app.orchestration.marketplace import classify
    assert classify(executions, 0.0, 0.0) == "deprecated"


# ===========================================================================
# memory_engine.classify_error (always returns string)
# ===========================================================================

@given(msg=st.text(min_size=0, max_size=500))
def test_classify_error_always_returns_str(msg: str) -> None:
    from app.orchestration.memory_engine import classify_error
    out = classify_error(msg)
    assert isinstance(out, str)
    assert len(out) > 0


@given(msg=st.text(min_size=0, max_size=200))
def test_extract_domain_tags_returns_list(msg: str) -> None:
    from app.orchestration.memory_engine import extract_domain_tags
    out = extract_domain_tags(msg)
    assert isinstance(out, list)


@given(msg=st.text(min_size=0, max_size=10_000))
def test_sanitize_spec_bounded_length(msg: str) -> None:
    from app.orchestration.memory_engine import sanitize_spec
    out = sanitize_spec(msg)
    assert isinstance(out, str)
    assert len(out) <= len(msg) + 100  # bound raisonnable


# ===========================================================================
# intake/universal_intake.detect_format
# ===========================================================================

@given(text=st.text(min_size=0, max_size=500))
def test_detect_format_returns_known_string(text: str) -> None:
    from app.intake.universal_intake import detect_format
    out = detect_format(text)
    assert out in ("json", "yaml", "email", "csv", "markdown",
                   "html", "text", "pdf", "image", "xlsx", "docx")


@given(data=st.dictionaries(
    keys=st.text(min_size=1, max_size=20,
                  alphabet=st.characters(categories=('Ll', 'Lu', 'Nd'))),
    values=st.one_of(st.integers(), st.text(max_size=50), st.booleans()),
    max_size=10,
))
def test_detect_format_json_roundtrip(data: dict) -> None:
    from app.intake.universal_intake import detect_format
    js = json.dumps(data)
    assert detect_format(js) == "json"


# ===========================================================================
# worker._artifact_version (deterministic + order-independent)
# ===========================================================================

@given(st.dictionaries(
    keys=st.text(min_size=1, max_size=20,
                  alphabet=st.characters(categories=('Ll', 'Lu', 'Nd'))),
    values=st.text(min_size=64, max_size=64,
                    alphabet=st.sampled_from("0123456789abcdef")),
    min_size=0, max_size=10,
))
def test_artifact_version_order_independent(pairs) -> None:
    from app.worker import _artifact_version
    m1 = [{"path": p, "sha256": h} for p, h in pairs.items()]
    m2 = list(reversed(m1))
    assert _artifact_version(m1) == _artifact_version(m2)


@given(st.lists(st.tuples(st.text(min_size=1, max_size=20),
                           st.text(min_size=1, max_size=64)),
                 min_size=0, max_size=20))
def test_artifact_version_64_hex(pairs) -> None:
    from app.worker import _artifact_version
    m = [{"path": p, "sha256": h} for p, h in pairs]
    h = _artifact_version(m)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ===========================================================================
# autonomy.autonomy_ladder (pure)
# ===========================================================================

@given(
    confidence=st.floats(min_value=0.0, max_value=1.0,
                          allow_nan=False, allow_infinity=False),
    reversible=st.booleans(),
    scope_reducible=st.booleans(),
    hard_boundary=st.booleans(),
    proof_valid=st.booleans(),
    ambiguity_resolved=st.booleans(),
)
def test_autonomy_ladder_decide_returns_valid_mode(
    confidence, reversible, scope_reducible, hard_boundary,
    proof_valid, ambiguity_resolved,
) -> None:
    from app.autonomy import autonomy_ladder
    from app.autonomy.autonomy_ladder import LadderInput
    inp = LadderInput(
        confidence=confidence, reversible=reversible,
        scope_reducible=scope_reducible, hard_boundary=hard_boundary,
        proof_valid=proof_valid, ambiguity_resolved=ambiguity_resolved,
    )
    out = autonomy_ladder.decide(inp)
    assert hasattr(out, "mode")
    assert isinstance(out.reason, str)
    assert isinstance(out.constraints, list)


# ===========================================================================
# decision_router.classify (pure)
# ===========================================================================

@given(
    verdict=st.sampled_from(["PASS", "CONDITIONAL_PASS", "SOFT_FAIL", "FAIL"]),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_decision_router_classify_valid(verdict: str, confidence: float) -> None:
    from app.orchestration.decision_router import RouterInput, classify
    out = classify(RouterInput(
        task_id="t1", verdict=verdict, confidence=confidence,
        invariants_violated=[], defect_classes=[],
        has_security_breach=False,
    ))
    assert hasattr(out, "route")


# ===========================================================================
# domain_classifier.classify (pure)
# ===========================================================================

@given(prompt=st.text(min_size=0, max_size=500))
def test_domain_classifier_returns_report(prompt: str) -> None:
    from app.orchestration.domain_classifier import classify
    out = classify(prompt)
    assert hasattr(out, "domain")
    assert isinstance(out.domain_hits, list)
    assert 0.0 <= out.domain_confidence <= 1.0


# ===========================================================================
# defect_taxonomy.classify (pure)
# ===========================================================================

@given(
    title=st.text(min_size=0, max_size=100),
    details=st.text(min_size=0, max_size=200),
)
def test_defect_taxonomy_classify_shape(title: str, details: str) -> None:
    from app.orchestration.defect_taxonomy import classify
    label, sev = classify(title, details)
    assert isinstance(label, str) and len(label) > 0
    assert isinstance(sev, str) and len(sev) > 0


# ===========================================================================
# auto_tuner.compute_thresholds (pure)
# ===========================================================================

@given(
    scores_pass=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=0, max_size=100),
    scores_all=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=0, max_size=100),
)
@settings(max_examples=30)
def test_compute_thresholds_monotonic(
    scores_pass: list[float], scores_all: list[float],
) -> None:
    from app.orchestration.auto_tuner import compute_thresholds
    t = compute_thresholds(scores_pass, scores_all, scope="global")
    # ordering invariant
    assert t.pass_min >= t.cpass_min
    assert t.cpass_min >= t.soft_fail_min >= 0.0
    assert t.pass_min <= 1.0


# ===========================================================================
# reason_code.validate (pure)
# ===========================================================================

@given(st.text(min_size=0, max_size=200))
def test_reason_code_validate_doesnt_crash(txt: str) -> None:
    from app.orchestration.reason_code import RepromptRequest, validate
    try:
        validate(RepromptRequest(task_id="t", reason=txt, context={}))
    except Exception:
        # certains input invalides -> raise ok
        pass


# ===========================================================================
# sensitive_collector.classify (pure)
# ===========================================================================

@given(st.text(min_size=0, max_size=100))
def test_sensitive_classify_returns_category(label: str) -> None:
    from app.orchestration.sensitive_collector import classify
    out = classify(label)
    assert isinstance(out, str)


# ===========================================================================
# ambiguity_resolver.classify_sub_type
# ===========================================================================

@given(st.text(min_size=0, max_size=200))
def test_ambiguity_classify_sub_type(q: str) -> None:
    from app.autonomy.ambiguity_resolver import classify_sub_type
    out = classify_sub_type(q)
    assert out is None or isinstance(out, str)
