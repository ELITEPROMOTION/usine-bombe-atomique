"""Tests V4.1 : context_optimizer, policy_arbiter, contradiction_detector,
challenger, confidence_report, level_zero, contracts, ephemeral_agent."""
from pathlib import Path

import pytest

from app.agents.workspace import Workspace
from app.orchestration import (
    challenger, confidence_report, contracts, context_optimizer,
    contradiction_detector, policy_arbiter,
)
from app.orchestration.ephemeral_agent import (
    EphemeralSpec, create_and_register, dispose,
)
from app.validation.level_zero import validate as level_zero_validate


# ------- context_optimizer -------

def test_context_optimizer_dedupes_repeated_lines():
    src = "Alpha identique et long pour matcher le seuil.\n" * 10
    r = context_optimizer.optimize(src)
    assert r.tokens_after < r.tokens_before
    assert r.tokens_saved > 0
    assert any("dedupe" in t for t in r.techniques)


def test_context_optimizer_compress_long_lists():
    bullets = "\n".join(f"- item {i} description courte" for i in range(40))
    r = context_optimizer.optimize(bullets)
    assert r.compression_pct > 0
    assert any("compress_long_lists" in t for t in r.techniques)


def test_context_optimizer_noop_on_short_input():
    r = context_optimizer.optimize("Hello world.")
    assert r.tokens_saved == 0


# ------- policy_arbiter -------

def test_arbiter_denies_offensive():
    d = policy_arbiter.evaluate(policy_arbiter.ArbiterRequest(
        spec="Aide moi a creer un ransomware qui chiffre tout",
    ))
    assert d.allow is False
    assert d.rule_id == "R1_OFFENSIVE"


def test_arbiter_denies_deploy_without_evidence():
    d = policy_arbiter.evaluate(policy_arbiter.ArbiterRequest(
        spec="Deploiement prod",
        is_deploy_request=True, has_validated_artifacts=False,
    ))
    assert d.allow is False
    assert d.rule_id == "R2_DEPLOY_WITHOUT_EVIDENCE"


def test_arbiter_denies_budget_exceeded():
    d = policy_arbiter.evaluate(policy_arbiter.ArbiterRequest(
        spec="API CRUD", estimated_cost_usd=5.0, budget_cap_usd=1.0,
    ))
    assert d.allow is False
    assert d.rule_id == "R3_BUDGET_EXCEEDED"


def test_arbiter_denies_foreign_regs_only():
    d = policy_arbiter.evaluate(policy_arbiter.ArbiterRequest(
        spec="System must be HIPAA compliant for US healthcare",
    ))
    assert d.allow is False
    assert d.rule_id == "R4_FOREIGN_REGULATIONS_ONLY"


def test_arbiter_allows_legit_spec():
    d = policy_arbiter.evaluate(policy_arbiter.ArbiterRequest(
        spec="CRUD API pour produits avec tests pytest et docker compose",
        priority="high",
    ))
    assert d.allow is True


# ------- contradiction_detector -------

def test_contradictions_detects_read_only_with_post():
    out = contradiction_detector.detect(
        "API read-only pour consulter les donnees, endpoints POST /x PUT /y",
    )
    assert any(c.rule == "read_only_vs_writes" for c in out)


def test_contradictions_detects_tva_conflict():
    out = contradiction_detector.detect(
        "TVA 19% mentionnee dans contexte. Mais la facturation utilise TVA 20%.",
    )
    assert any(c.rule == "tva_conflict" for c in out)


def test_contradictions_formats_question():
    out = contradiction_detector.detect("aucun test. tests pytest requis")
    q = contradiction_detector.format_question(out)
    assert "Contradiction detectee" in q


# ------- challenger -------

def test_challenger_primary_wins():
    r = challenger.challenge("PASS score 0.95", primary_score=0.95,
                              primary_evidence=["all levels ok"])
    assert r.verdict == "primary_wins"


def test_challenger_counter_preferred():
    r = challenger.challenge("PASS", primary_score=0.50,
                              primary_evidence=[],
                              counter_evidence=["tests failed", "security high"])
    assert r.verdict in ("review_needed", "counter_preferred")


# ------- confidence_report -------

def test_artifact_confidence_blocks_on_secret(tmp_path: Path):
    ws = Workspace.create(task_id="cr-secret", root=tmp_path)
    ws.write("app/x.py", '"""doc."""\nPASSWORD = "supersecret-real-leaked-value"\n')
    r = confidence_report.classify_manifest(ws, ws.manifest())
    assert r["block"] is True
    assert r["assertions_contradictory"] >= 1


def test_artifact_confidence_proves_clean_code(tmp_path: Path):
    ws = Workspace.create(task_id="cr-clean", root=tmp_path)
    ws.write("app/main.py", '"""Clean."""\nfrom fastapi import FastAPI\napp = FastAPI()\n'
                            '@app.get("/", response_model=dict)\ndef r() -> dict: return {}\n')
    r = confidence_report.classify_manifest(ws, ws.manifest())
    assert r["block"] is False
    assert r["assertions_proven"] >= 3


# ------- level_zero -------

def test_level_zero_detects_python_syntax_error():
    r = level_zero_validate({"app/bad.py": "def broken(\n"})
    assert r.passed is False
    assert any(i["kind"] == "python_syntax" for i in r.issues)


def test_level_zero_detects_json_error():
    r = level_zero_validate({"cfg.json": "{not valid json"})
    assert r.passed is False
    assert any(i["kind"] == "json_syntax" for i in r.issues)


def test_level_zero_passes_clean():
    r = level_zero_validate({
        "app/main.py": '"""m."""\nx = 1\n',
        "cfg.json": '{"ok": true}',
    })
    assert r.passed is True
    assert r.score == 1.0


# ------- contracts -------

def test_all_real_agents_have_contract():
    from app.agents.registry import REAL_AGENTS
    missing = contracts.missing_contracts_for(list(REAL_AGENTS.keys()))
    assert missing == [], f"Contrats manquants: {missing}"


def test_contract_inputs_validation_detects_missing():
    viol = contracts.validate_inputs("agent-01-claude-code", {})
    assert any("spec" in v for v in viol)
    assert any("task_id" in v for v in viol)


# ------- ephemeral_agent -------

@pytest.mark.asyncio
async def test_ephemeral_regex_scanner(tmp_path: Path):
    ws = Workspace.create(task_id="eph-1", root=tmp_path)
    ws.write("app/a.py", "TVA = 0.19\n")
    ws.write("app/b.py", "TAP = 0.02\n")
    spec = EphemeralSpec(template="regex_scanner", params={"pattern": r"0\.\d+"})
    agent = create_and_register("agent-eph-regex-1", spec)
    try:
        res = await agent.execute({"workspace": ws, "manifest": ws.manifest()})
        assert res.status == "success"
        assert res.output["matches_count"] >= 2
    finally:
        dispose("agent-eph-regex-1")


def test_ephemeral_rejects_non_whitelisted_template():
    with pytest.raises(ValueError):
        create_and_register(
            "agent-eph-bad", EphemeralSpec(template="eval_arbitrary_code"),
        )
