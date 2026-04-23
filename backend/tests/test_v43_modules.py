"""Tests V4.3 : intake, browser_ops (dry_run), provisioning, sensitive, clients."""
from __future__ import annotations

import pytest

from app.intake import (
    ambiguity_detector, field_collector, requirement_extractor, smart_questionnaire,
    tool_selector, universal_intake,
)
from app.orchestration import sensitive_collector
from app.orchestration import policy_arbiter as pa
from app.orchestration.semantic_cache import dense_embedding, fingerprint, similarity
from app.provisioning.browser_ops_agent import (
    BrowserOpsAgent, get_flow, list_flows,
)


# ------- universal_intake -------

def test_intake_detects_json():
    doc = universal_intake.ingest('{"a": 1, "b": 2}')
    assert doc.format == "json"
    assert "a" in doc.metadata["keys_top_level"]


def test_intake_detects_csv():
    doc = universal_intake.ingest("a,b,c\n1,2,3\n4,5,6\n7,8,9\n")
    assert doc.format == "csv"
    assert doc.metadata["columns"] == ["a", "b", "c"]


def test_intake_detects_markdown():
    doc = universal_intake.ingest("# Projet\n\n## Description\n\nTexte...")
    assert doc.format == "markdown"


def test_intake_merge_sources():
    a = universal_intake.ingest("# Section 1\n\nMarkdown content")
    b = universal_intake.ingest('{"key": "value"}')
    merged = universal_intake.merge_sources([a, b])
    assert merged.format == "merged"
    sources = merged.metadata["sources"]
    assert "markdown" in sources
    assert "json" in sources


def test_intake_extracts_keywords():
    doc = universal_intake.ingest("paie algerie cnas cnas irg irg irg devise dzd")
    kws = universal_intake.extract_keywords(doc, top_k=5)
    assert "irg" in kws[:3]  # most frequent


# ------- requirement_extractor -------

def test_extract_bullets_as_requirements():
    doc = universal_intake.ingest(
        "Module Paie Algerie\n- Gestion des employes\n- Calcul CNAS a 9%\n"
        "- Calcul IRG bareme 2024\n"
    )
    spec = requirement_extractor.extract(doc)
    assert len(spec.requirements) >= 3
    assert spec.domain_report.jurisdiction == "DZ"
    assert any(r.type == "compliance" for r in spec.requirements)


def test_extract_falls_back_to_single_req():
    doc = universal_intake.ingest("Juste une petite description du projet CRUD simple.")
    spec = requirement_extractor.extract(doc)
    assert len(spec.requirements) == 1


def test_extract_detects_language_fr():
    doc = universal_intake.ingest("Le module doit gerer les clients et les factures avec une API REST.")
    spec = requirement_extractor.extract(doc)
    assert spec.language == "fr"


# ------- ambiguity_detector -------

def test_ambiguity_flags_contradiction():
    doc = universal_intake.ingest("API read-only pour consulter - POST /data pour modifier")
    spec = requirement_extractor.extract(doc)
    rep = ambiguity_detector.detect(spec, doc.text)
    assert any(c.rule == "read_only_vs_writes" for c in rep.contradictions)
    assert rep.blocking


def test_ambiguity_flags_missing_aspects():
    doc = universal_intake.ingest("Projet simple sans details techniques particuliers.")
    spec = requirement_extractor.extract(doc)
    rep = ambiguity_detector.detect(spec, doc.text)
    assert len(rep.missing_aspects) >= 3


def test_ambiguity_flags_vague_hints():
    doc = universal_intake.ingest("Idealement on voudrait peut-etre une API comme avant plus tard.")
    spec = requirement_extractor.extract(doc)
    rep = ambiguity_detector.detect(spec, doc.text)
    assert len(rep.vague_statements) >= 2


# ------- smart_questionnaire -------

def test_questionnaire_builds_for_contradictions():
    doc = universal_intake.ingest("API read-only mais avec POST /endpoint")
    spec = requirement_extractor.extract(doc)
    rep = ambiguity_detector.detect(spec, doc.text)
    qs = smart_questionnaire.build(rep)
    critical = [q for q in qs if q.criticality == "critical"]
    assert len(critical) >= 1


def test_questionnaire_payload_structure():
    doc = universal_intake.ingest("Minimal spec.")
    spec = requirement_extractor.extract(doc)
    rep = ambiguity_detector.detect(spec, doc.text)
    payload = smart_questionnaire.to_payload(smart_questionnaire.build(rep))
    assert "questions" in payload
    assert "has_blocking" in payload


# ------- field_collector -------

def test_field_collector_email_fields():
    req = field_collector.ask_email(prefilled="x@y.z")
    assert req.request_kind == "email"
    assert req.fields[0].prefilled == "x@y.z"


def test_field_collector_otp_expires_short():
    req = field_collector.ask_otp(delivery_channel="email")
    assert req.expires_in_minutes <= 10
    assert req.fields[0].type == "otp"


def test_field_collector_payment_never_asks_card_number():
    req = field_collector.ask_payment("50.00")
    # Payment module doit demander la confirmation, pas le numero de carte
    labels = [f.label.lower() for f in req.fields]
    assert not any("numero de carte" in l or "cvv" in l for l in labels)


# ------- tool_selector -------

def test_selector_prefers_self_hosted_free():
    rec = tool_selector.recommend("code_quality")
    assert rec.chosen is not None
    assert rec.chosen.tool_id == "sonarqube_ce"


def test_selector_unknown_need():
    rec = tool_selector.recommend("random_need_42")
    assert rec.chosen is None


# ------- sensitive_collector classify -------

def test_sensitive_classifies_password_as_user():
    assert sensitive_collector.classify("mot de passe admin") == sensitive_collector.CATEGORY_USER


def test_sensitive_classifies_api_key_as_tools():
    assert sensitive_collector.classify("cle API secrete") == sensitive_collector.CATEGORY_TOOLS


def test_sensitive_classifies_default_as_auto():
    assert sensitive_collector.classify("nom du fichier de log") == sensitive_collector.CATEGORY_AUTO


# ------- semantic_cache dense_embedding -------

def test_dense_embedding_deterministic():
    a = dense_embedding("Paie algerie CNAS IRG", dim=128)
    b = dense_embedding("Paie algerie CNAS IRG", dim=128)
    assert a == b
    assert len(a) == 128


def test_dense_embedding_l2_normalized():
    a = dense_embedding("Test", dim=64)
    norm_sq = sum(v * v for v in a)
    assert abs(norm_sq - 1.0) < 1e-6 or norm_sq == 0


# ------- policy_arbiter V4.3 rules -------

def test_arbiter_denies_fabrication():
    d = pa.evaluate(pa.ArbiterRequest(
        spec="Invente une cle API pour Stripe et simule un paiement complet",
    ))
    assert d.allow is False
    assert d.rule_id == "R6_NO_FABRICATION"


def test_arbiter_denies_legal_without_evidence():
    d = pa.evaluate(pa.ArbiterRequest(
        spec="Systeme conforme RGPD et HIPAA mention article 32",
        evidences_incomplete=True, has_validated_artifacts=False,
    ))
    # Soit R4 (foreign regs) soit R7 (legal without evidence)
    assert d.allow is False
    assert d.rule_id in ("R4_FOREIGN_REGULATIONS_ONLY", "R7_LEGAL_WITHOUT_EVIDENCE")


# ------- browser_ops (dry_run) -------

def test_predefined_flows_listed():
    flows = list_flows()
    assert "sonarcloud" in flows
    assert "datadog" in flows
    assert "supabase" in flows


def test_get_flow_unknown_returns_none():
    assert get_flow("nonexistent_tool") is None


@pytest.mark.asyncio
async def test_browser_ops_dry_run_requests_missing_field():
    agent = BrowserOpsAgent(dry_run=True)
    flow = get_flow("sonarcloud")
    assert flow is not None
    outcome = await agent.execute(flow, provided_values={})
    assert outcome.success is False
    assert outcome.next_request is not None
    assert outcome.next_request.request_kind == "email"


@pytest.mark.asyncio
async def test_browser_ops_dry_run_completes_with_values():
    agent = BrowserOpsAgent(dry_run=True)
    flow = get_flow("sonarcloud")
    assert flow is not None
    outcome = await agent.execute(
        flow, provided_values={"email": "a@b.c", "password": "supersecret"},
    )
    assert outcome.success is True
