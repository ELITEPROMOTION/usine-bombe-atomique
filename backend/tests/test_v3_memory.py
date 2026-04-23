"""Tests V3 : extract_domain_tags, error_signature, cost_optimizer."""
from app.orchestration.cost_optimizer import (
    PRICING_USD_PER_MTOK, estimate_cost, estimate_tokens, select_model,
)
from app.orchestration.memory_engine import (
    classify_error, error_signature, extract_domain_tags,
)


def test_extract_domain_tags_paie():
    tags = extract_domain_tags("Module Paie Algerie avec CNAS 9% et IRG, devise DZD")
    assert "paie" in tags
    assert "dz" in tags


def test_extract_domain_tags_vefa():
    tags = extract_domain_tags("Gestion clients VEFA residences avec paliers")
    assert "vefa" in tags


def test_extract_domain_tags_empty():
    assert extract_domain_tags("") == []


def test_error_signature_deterministic_and_dedup():
    s1 = error_signature("agent-01", "TypeError", "NoneType has no attribute 'x'\n  File ...")
    s2 = error_signature("agent-01", "TypeError", "NoneType has no attribute 'x'\n  File other")
    assert s1 == s2
    s3 = error_signature("agent-02", "TypeError", "NoneType has no attribute 'x'")
    assert s1 != s3


def test_classify_error_buckets():
    assert classify_error("SyntaxError: invalid syntax") == "SyntaxError"
    assert classify_error("timeout waiting for response") == "Timeout"
    assert classify_error("Connection refused") == "ConnectionError"
    assert classify_error("credit balance too low") == "QuotaError"
    assert classify_error("something else") == "RuntimeError"


def test_select_model_critical_selects_opus():
    sel = select_model("short spec", priority="critical")
    assert sel.tier == "opus"
    assert sel.model_id in PRICING_USD_PER_MTOK


def test_select_model_low_priority_small_selects_haiku():
    sel = select_model("tiny crud api", priority="low")
    assert sel.tier == "haiku"


def test_select_model_default_sonnet():
    sel = select_model("CRUD API pour produits", priority="high")
    assert sel.tier == "sonnet"


def test_select_model_long_spec_escalates_opus():
    sel = select_model("x" * 7000, priority="medium")
    assert sel.tier == "opus"


def test_select_model_refinement_escalates():
    sel = select_model("small spec", priority="medium", refinement_round=1)
    assert sel.tier == "opus"


def test_estimate_cost_sonnet_coherent():
    inp, out = estimate_tokens("x" * 4000)
    cost = estimate_cost("claude-sonnet-4-6", inp, out)
    assert cost > 0
    # Sonnet output to input ratio : 15/3 => output dominates
    assert cost < 1.0  # Un run ne doit jamais couter plus de 1 USD sur cette estimation
