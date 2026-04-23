"""Tests V4.8 : user_interaction_router, forms_generator, autonomous_executor,
mit_expert_mode, continuous_improvement."""
from __future__ import annotations

import pytest

from app.inbox import forms_generator, mit_expert_mode
from app.inbox.user_interaction_router import (
    AccountAsk, Case, ClarificationAsk, InteractionRequest, PaymentAsk,
    _build_form, _validate,
)


# --- user_interaction_router validate ------------------------------

def test_validate_account_ok():
    req = InteractionRequest(
        case=Case.ACCOUNT, task_id="t", actor="test",
        payload=AccountAsk(service_name="GitHub", why="CI runner"),
    )
    assert _validate(req) is None


def test_validate_account_missing_service():
    req = InteractionRequest(
        case=Case.ACCOUNT, task_id="t", actor="test",
        payload=AccountAsk(service_name="", why="..."),
    )
    assert "service_name" in (_validate(req) or "")


def test_validate_payment_requires_https():
    req = InteractionRequest(
        case=Case.PAYMENT, task_id="t", actor="test",
        payload=PaymentAsk(service_name="X", why="w", cost_amount="10.00",
                            cost_currency="USD", duration_months=1,
                            free_alternative=False, payment_url="ftp://nope"),
    )
    assert "payment_url" in (_validate(req) or "")


def test_validate_payment_ok():
    req = InteractionRequest(
        case=Case.PAYMENT, task_id="t", actor="test",
        payload=PaymentAsk(service_name="X", why="w", cost_amount="10.00",
                            cost_currency="USD", duration_months=1,
                            free_alternative=True,
                            payment_url="https://billing.example.com"),
    )
    assert _validate(req) is None


def test_validate_clarification_requires_suggestion():
    """Principe MIT Senior : jamais une question sans reponse suggeree."""
    req = InteractionRequest(
        case=Case.CLARIFICATION, task_id="t", actor="test",
        payload=ClarificationAsk(question_id="Q-001", question="?", why="w",
                                   suggested_answer=""),
    )
    assert "suggested_answer" in (_validate(req) or "")


def test_validate_clarification_id_format():
    req = InteractionRequest(
        case=Case.CLARIFICATION, task_id="t", actor="test",
        payload=ClarificationAsk(question_id="001", question="?", why="w",
                                   suggested_answer="yes"),
    )
    assert "Q-" in (_validate(req) or "")


def test_validate_payload_mismatch():
    req = InteractionRequest(
        case=Case.ACCOUNT, task_id="t", actor="test",
        payload=PaymentAsk(service_name="X", why="w", cost_amount="5",
                            cost_currency="USD", duration_months=1,
                            free_alternative=False,
                            payment_url="https://x.example.com"),
    )
    assert "case A exige AccountAsk" == _validate(req)


# --- _build_form ------------------------------

def test_build_form_account_has_email_password():
    fields, kind, extras = _build_form(InteractionRequest(
        case=Case.ACCOUNT, task_id="t", actor="a",
        payload=AccountAsk(service_name="Supabase", why="DB"),
    ))
    ids = [f["id"] for f in fields]
    assert ids == ["email", "password"]
    assert kind == "email"
    assert extras["service_name"] == "Supabase"


def test_build_form_payment_has_payment_fields():
    fields, kind, extras = _build_form(InteractionRequest(
        case=Case.PAYMENT, task_id="t", actor="a",
        payload=PaymentAsk(service_name="Datadog", why="APM",
                            cost_amount="15.00", cost_currency="USD",
                            duration_months=1, free_alternative=True,
                            payment_url="https://datadog.com/billing"),
    ))
    assert kind == "payment"
    assert any(f["id"] == "payment_status" for f in fields)
    assert extras["payment_url"].startswith("https://")


def test_build_form_clarification_offers_options():
    fields, kind, extras = _build_form(InteractionRequest(
        case=Case.CLARIFICATION, task_id="t", actor="a",
        payload=ClarificationAsk(
            question_id="Q-002", question="Cloud ?",
            why="Infra", suggested_answer="AWS",
            options=["AWS", "Azure", "GCP"]),
    ))
    assert kind == "custom"
    assert any(f["id"] == "option_choice" for f in fields)
    assert extras["question_id"] == "Q-002"


# --- forms_generator --------------------------

def test_form_account_contains_instructions():
    f = forms_generator.form_account(AccountAsk("X", "Y"))
    assert f["type"] == "A"
    assert "automatiquement" in f["instruction"]
    assert any(fd["id"] == "email" for fd in f["fields"])


def test_form_payment_exposes_alternative_flag():
    f = forms_generator.form_payment(PaymentAsk(
        "X", "Y", "10", "USD", 1, True, "https://x.com"))
    assert f["type"] == "B"
    assert f["free_alternative"] is True


def test_form_clarification_title_and_fields():
    f = forms_generator.form_clarification(ClarificationAsk(
        "Q-001", "q?", "w", "yes", ["yes", "no"], "high"))
    assert f["type"] == "C"
    assert f["title"] == "Clarification necessaire"
    assert any(fd["id"] == "free_answer" for fd in f["fields"])


def test_render_dispatch_mismatch_raises():
    with pytest.raises(ValueError):
        forms_generator.render(InteractionRequest(
            case=Case.ACCOUNT, task_id="t", actor="a",
            payload=PaymentAsk("X", "Y", "1", "USD", 1, True,
                                 "https://x.example.com"),
        ))


# --- mit_expert_mode -----------------------

def test_mit_choose_returns_winner():
    d = mit_expert_mode.pick_http_server()
    assert d.winner.name == "uvicorn+fastapi"
    assert len(d.losers) == 2


def test_mit_pick_db_prefers_pgvector():
    d = mit_expert_mode.pick_db()
    assert "pgvector" in d.winner.name


def test_mit_pick_queue_prefers_arq_for_python():
    d = mit_expert_mode.pick_queue()
    assert d.winner.name == "redis+arq"


def test_mit_pick_llm_critical_goes_opus():
    d = mit_expert_mode.pick_llm_tier(100, "critical", "low")
    assert d.winner.name == "opus-4-7"


def test_mit_pick_llm_low_spec_goes_haiku():
    d = mit_expert_mode.pick_llm_tier(500, "low", "low")
    assert d.winner.name == "haiku-4-5"


def test_mit_pick_llm_default_goes_sonnet():
    d = mit_expert_mode.pick_llm_tier(2000, "high", "medium")
    assert d.winner.name == "sonnet-4-6"


def test_mit_requires_two_candidates():
    from app.inbox.mit_expert_mode import Candidate, choose
    with pytest.raises(ValueError):
        choose([Candidate("solo", 1, 1, 1, 1, 1)])


def test_mit_recommend_patterns_fintech():
    p = mit_expert_mode.recommend_patterns("fintech")
    assert "event-sourcing" in p["architecture"]
    assert "blue/green" in p["deploy"]


# --- continuous_improvement risk_score ---------

def test_cci_risk_score_safe_for_calibration():
    from app.inbox.continuous_improvement import _risk_score
    r = _risk_score({"category": "calibration", "priority": "medium"})
    assert r < 0.20   # auto-apply eligible


def test_cci_risk_score_high_for_architecture():
    from app.inbox.continuous_improvement import _risk_score
    r = _risk_score({"category": "architecture", "priority": "critical"})
    assert r >= 0.80


# --- meta_optimizer seuils ------------

def test_meta_degradation_flags_30pct_duration():
    from app.inbox.meta_optimizer import _detect_degradation
    prev = {"avg_duration_ms": 10_000, "rework_rate": 0.10, "avg_cost_usd": 0.10}
    curr = {"avg_duration_ms": 14_000, "rework_rate": 0.10, "avg_cost_usd": 0.10}
    d = _detect_degradation(curr, prev)
    assert any("avg_duration_ms" in s for s in d)


def test_meta_no_degradation_without_previous():
    from app.inbox.meta_optimizer import _detect_degradation
    assert _detect_degradation({"avg_duration_ms": 1}, None) == []


def test_meta_no_degradation_when_stable():
    from app.inbox.meta_optimizer import _detect_degradation
    prev = {"avg_duration_ms": 10_000, "rework_rate": 0.10, "avg_cost_usd": 0.10}
    curr = {"avg_duration_ms": 10_500, "rework_rate": 0.10, "avg_cost_usd": 0.10}
    assert _detect_degradation(curr, prev) == []
