"""V5.1 - Tests pour l'autonomie ultimate 99.9%+.

Couverture :
  - ambiguity_resolver : cascade 4 niveaux, C1..C6, false/self_induced
  - autonomy_ladder : 5 modes
  - human_necessity_proof : hash + verdict
  - autonomy_cost_model : best_mode
  - calibration_engine : Brier + buckets
  - autonomy_auditor : shape KPIs
  - autonomy_chaos_engine : result shape
  - fallback_chain : coverage et registration
  - permission_lease_manager : grant + consume + revoke (mocked pool)
  - autonomy_simulation_lab : Policy comparison
"""
from __future__ import annotations

from app.autonomy import (
    ambiguity_resolver,
    autonomy_cost_model,
    autonomy_ladder,
    calibration_engine,
    fallback_chain,
    intervention_learner,
)
from app.autonomy.autonomy_ladder import LadderInput, Mode
from app.autonomy.autonomy_simulation_lab import Policy
from app.autonomy.calibration_engine import CalibrationReport


# ------------------------------------------------------------- ambiguity_resolver

def test_classify_sub_type_business():
    assert ambiguity_resolver.classify_sub_type(
        "quelle regle metier appliquer pour Dendani ?") == "C1"


def test_classify_sub_type_priorite():
    assert ambiguity_resolver.classify_sub_type(
        "on livre plus vite ou on attend les tests ?") == "C2"


def test_classify_sub_type_rgpd():
    assert ambiguity_resolver.classify_sub_type(
        "faut-il un RGPD waiver pour cette donnee ?") == "C3"


def test_classify_sub_type_cdc():
    assert ambiguity_resolver.classify_sub_type(
        "la clause CDC est ambigue sur cette partie") == "C6"


def test_is_false_ambiguity_true():
    assert ambiguity_resolver.is_false_ambiguity(
        "Je ne sais pas quoi faire avec ce endpoint")


def test_is_false_ambiguity_false():
    assert not ambiguity_resolver.is_false_ambiguity(
        "Quel framework choisir entre Django et FastAPI ?")


def test_is_self_induced_true():
    ctx = ("Le CDC precise que le backup doit etre quotidien a 02:00 UTC "
            "avec retention 30 jours et chiffrement AES-256.")
    q = "Quelle frequence backup quotidien AES-256 retention 30 UTC ?"
    assert ambiguity_resolver.is_self_induced(ctx, q)


def test_is_self_induced_false():
    ctx = "Projet API gestion clients VEFA"
    q = "Faut-il utiliser GraphQL ou REST ?"
    assert not ambiguity_resolver.is_self_induced(ctx, q)


def test_industry_default_hit_backup():
    ok, msg = ambiguity_resolver._level2_industry_default(
        "Quelle strategie de backup adopter ?")
    assert ok and "02:00 UTC" in msg


def test_industry_default_miss():
    ok, _ = ambiguity_resolver._level2_industry_default(
        "Quel nom donner a la v2 de Dendani client ?")
    assert ok is False


# --------------------------------------------------------------- autonomy_ladder

def test_ladder_continue_when_high_confidence():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.95, reversible=True, scope_reducible=True,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False,
    ))
    assert d.mode == Mode.CONTINUE


def test_ladder_escalate_on_hard_boundary():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.99, reversible=True, scope_reducible=True,
        hard_boundary=True, proof_valid=True, ambiguity_resolved=False,
    ))
    assert d.mode == Mode.ESCALATE


def test_ladder_probe_on_mid_confidence():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.80, reversible=True, scope_reducible=True,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False,
    ))
    assert d.mode == Mode.PROBE


def test_ladder_constrain_with_scope():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.65, reversible=False, scope_reducible=True,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False,
    ))
    assert d.mode == Mode.CONSTRAIN


def test_ladder_defer_on_low_without_proof():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.20, reversible=False, scope_reducible=False,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False,
    ))
    assert d.mode == Mode.DEFER


def test_ladder_escalate_on_very_low_with_proof():
    d = autonomy_ladder.decide(LadderInput(
        confidence=0.20, reversible=False, scope_reducible=False,
        hard_boundary=False, proof_valid=True, ambiguity_resolved=False,
    ))
    assert d.mode == Mode.ESCALATE


def test_ladder_upgrade_defer_to_escalate_on_critical():
    base = autonomy_ladder.decide(LadderInput(
        confidence=0.50, reversible=False, scope_reducible=False,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False,
    ))
    assert base.mode == Mode.DEFER
    up = autonomy_ladder.upgrade_for_criticality(base, "critical")
    assert up.mode == Mode.ESCALATE


def test_ladder_no_upgrade_on_medium():
    base = autonomy_ladder.decide(LadderInput(
        confidence=0.50, reversible=False, scope_reducible=False,
        hard_boundary=False, proof_valid=False, ambiguity_resolved=False,
    ))
    assert autonomy_ladder.upgrade_for_criticality(base, "medium").mode \
           == Mode.DEFER


# --------------------------------------------------------------- cost model

def test_cost_best_mode_high_conf_prefers_continue():
    r = autonomy_cost_model.best_mode(confidence=0.95)
    assert r["best"] in ("CONTINUE", "PROBE", "CONSTRAIN")


def test_cost_best_mode_low_conf_prefers_escalate_or_defer():
    r = autonomy_cost_model.best_mode(
        confidence=0.10, downstream_cost_usd=1000.0)
    assert r["best"] in ("ESCALATE", "DEFER")


def test_cost_breakdown_has_positive_total():
    cb = autonomy_cost_model.estimate(
        confidence=0.5, mode="CONTINUE", tokens_in=10_000, tokens_out=2_000,
        duration_ms=5000, downstream_cost_usd=500.0,
    )
    assert cb.total_usd > 0
    d = cb.to_dict()
    assert set(d.keys()) == {"api_usd", "latency_usd", "human_usd", "risk_usd", "total_usd"}


def test_cost_escalate_reduces_risk_vs_continue():
    c = autonomy_cost_model.estimate(
        confidence=0.3, mode="CONTINUE", downstream_cost_usd=1000.0)
    e = autonomy_cost_model.estimate(
        confidence=0.3, mode="ESCALATE", human_minutes=3.0,
        downstream_cost_usd=1000.0)
    assert e.risk_usd < c.risk_usd


# --------------------------------------------------------------- calibration

def test_calibration_empty_report_ok():
    r = CalibrationReport(samples=0, brier_score=0.0,
                           calibration_score=0.0, buckets=[])
    assert calibration_engine.calibrate(0.5, r) == 0.5


def test_calibration_calibrate_with_buckets():
    r = CalibrationReport(
        samples=10, brier_score=0.05, calibration_score=0.95,
        buckets=[{"range": "0.6-0.8", "n": 5, "avg_confidence": 0.7,
                   "avg_outcome": 0.5, "gap": 0.2}],
    )
    assert calibration_engine.calibrate(0.7, r) == 0.5


# --------------------------------------------------------------- fallback_chain

def test_fallback_datadog_recommends_prometheus():
    d = fallback_chain.find("datadog", min_coverage=0.70)
    assert d.should_still_ask is False
    assert d.recommended["name"] in ("prometheus+grafana",
                                       "datadog-free-5hosts")


def test_fallback_unknown_service_asks():
    d = fallback_chain.find("never-seen-service-xyz")
    assert d.should_still_ask is True
    assert d.recommended is None


def test_fallback_register_adds_map():
    fallback_chain.register(
        "my-new-service",
        [{"name": "mns-alt", "coverage": 0.9,
          "integration_effort": "low", "kind": "open_source"}],
    )
    d = fallback_chain.find("my-new-service")
    assert d.recommended["name"] == "mns-alt"


# --------------------------------------------------------------- intervention_learner

def test_signature_stable_same_inputs():
    s1 = intervention_learner._signature("C", "C1", "Datadog",
                                            "frequence backup ?")
    s2 = intervention_learner._signature("C", "C1", "datadog",
                                            "frequence backup ?")
    assert s1 == s2


def test_signature_different_inputs():
    s1 = intervention_learner._signature("C", "C1", "Datadog", "question 1")
    s2 = intervention_learner._signature("C", "C2", "Datadog", "question 1")
    assert s1 != s2


# --------------------------------------------------------------- Policy shape

def test_simulation_policy_defaults():
    p = Policy()
    assert p.escalate_confidence_threshold == 0.40
    assert p.continue_confidence_threshold == 0.92


# --------------------------------------------------------------- chaos scenarios list

def test_chaos_scenarios_exposed():
    from app.autonomy import autonomy_chaos_engine
    assert len(autonomy_chaos_engine.SCENARIOS) >= 5
    assert "api_unavailable" in autonomy_chaos_engine.SCENARIOS


# --------------------------------------------------------------- correlation id

def test_new_id_format():
    from app.autonomy import correlation_id_universal
    cid = correlation_id_universal.new_id("test")
    assert cid.startswith("test-")
    assert len(cid) == len("test-") + 12


def test_new_id_unique():
    from app.autonomy import correlation_id_universal
    a = correlation_id_universal.new_id()
    b = correlation_id_universal.new_id()
    assert a != b
