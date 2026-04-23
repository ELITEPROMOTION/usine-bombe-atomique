"""Tests V4.2 : 24 upgrades (14-37).

Couvre les modules purement deterministes (pas de DB).
Les modules qui exigent asyncpg sont couverts par tests BDD dans test_v42_db.
"""
from __future__ import annotations

import pytest

from app.orchestration import (
    challenger, context_optimizer, defect_taxonomy, delta_validation,
    domain_classifier, edge_hunter, impact_analyzer, parallel_critic,
    patch_types, prompt_cache, reason_code, runtime_network_audit,
    semantic_cache, test_manifests, verification_bundle,
)
from app.orchestration.quorum_judge import decide
from app.orchestration.tri_brain import CriticIssue


# 15 : domain classifier
def test_domain_classifier_detects_paie_dz():
    r = domain_classifier.classify(
        "Module Paie Algerie avec CNAS et IRG, devise DZD")
    assert r.domain == "paie_rh"
    assert r.jurisdiction == "DZ"
    assert r.domain_confidence > 0


def test_domain_classifier_detects_fintech_fr():
    r = domain_classifier.classify(
        "Plateforme de paiement SEPA France avec IBAN et BIC URSSAF")
    assert r.domain == "fintech"
    assert r.jurisdiction == "FR"


# 16 : property-based IRG (simple Hypothesis)
def test_irg_monotone():
    """IRG doit etre monotone croissant : plus on gagne, plus on paie."""
    from decimal import Decimal

    from tests.test_e2e_classe_b_paie import PAIE_FILES
    code = PAIE_FILES["app/business.py"]
    # Execute le code dans un namespace isole
    ns: dict = {}
    exec(compile(code, "<business>", "exec"), ns)
    calc = ns["calculer_irg"]
    results = [calc(Decimal(str(v))) for v in range(30000, 200000, 10000)]
    assert all(a <= b for a, b in zip(results, results[1:], strict=False)), results


# 18 : verification_bundle
def test_bundle_flags_missing_proofs():
    b = verification_bundle.build(
        task_id="t1", spec="spec", agent_results={},
        pipeline_levels=[], confidence={}, structure_result={},
    )
    assert b.ok is False
    assert "test_proofs" in b.missing_proofs


def test_bundle_ok_when_all_proofs_present():
    from app.agents.base_agent import AgentResult
    def _ar(aid, output): return AgentResult(agent_id=aid, agent_name=aid,
                                              status="success", output=output)
    agents = {
        "agent-04-pytest":    _ar("agent-04-pytest", {"score": 1.0, "tests_total": 10}),
        "agent-11-security":  _ar("agent-11-security", {"score": 1.0, "bandit_count": 0}),
        "agent-18-conformite-dz": _ar("agent-18-conformite-dz", {"score": 1.0, "summary": ""}),
        "agent-14-linter":    _ar("agent-14-linter", {"score": 1.0, "issues_count": 0}),
    }
    b = verification_bundle.build(
        task_id="t2", spec="spec",
        agent_results=agents,
        pipeline_levels=[{"level": i, "score": 1.0, "passed": True} for i in range(1, 6)],
        confidence={"composite": 0.95, "dimensions": [{"name": "coverage", "score": 0.8}]},
        structure_result={"passed": True},
    )
    assert b.ok is True


# 20 / 33 / 34 : patch types + revalidation
def test_patch_exceeded_budget_triggers_regen():
    plan = patch_types.classify_patch(
        ["a.py", "b.py", "c.py", "d.py", "e.py"],
        declared_type=patch_types.PatchType.LOCAL_FIX,
    )
    assert plan.type == patch_types.PatchType.REGEN
    assert plan.exceeded_budget


def test_patch_schema_change_triggers_data_layer():
    plan = patch_types.classify_patch(
        ["migrations/010_new.sql"], touches_schema_sql=True,
    )
    assert plan.type == patch_types.PatchType.SCHEMA_FIX
    assert "data" in plan.layers_to_revalidate


def test_revalidation_causale_from_diff():
    layers = patch_types.required_layers_from_diff([
        "app/main.py", "tests/test_x.py", "migrations/999.sql",
    ])
    assert "behavior" in layers
    assert "data" in layers
    assert "structure" in layers


# 26 : delta_validation
def test_delta_diff_detects_changes():
    before = {"a.py": "x = 1\n", "b.py": "y = 2\n"}
    after = {"a.py": "x = 1\n", "b.py": "y = 22\n", "c.py": "z = 3\n"}
    d = delta_validation.diff(before, after)
    assert d.added == ["c.py"]
    assert d.modified == ["b.py"]
    assert d.removed == []
    assert d.unchanged == 1


def test_delta_time_saved():
    d = delta_validation.DeltaResult(modified=["a"], unchanged=9)
    pct = delta_validation.estimated_time_saved_pct(d, total_files=10)
    assert 85 <= pct <= 95


# 27 : edge_hunter
def test_edge_hunter_flags_datetime_now():
    cases = edge_hunter.hunt({"app/x.py": "from datetime import datetime\nt = datetime.now()\n"})
    assert any(c.kind == "datetime_no_tz" for c in cases)


def test_edge_hunter_flags_float_money():
    cases = edge_hunter.hunt({"app/x.py": "class P:\n    prix: float = 0.0\n"})
    assert any(c.kind == "float_money" for c in cases)


def test_edge_hunter_summary():
    cases = edge_hunter.hunt({"app/x.py": "from datetime import datetime\nt = datetime.now()\n"})
    s = edge_hunter.summarize(cases)
    assert s["total"] >= 1


# 21 : reason_code
def test_reason_code_blind_raises():
    with pytest.raises(ValueError):
        reason_code.ensure_non_blind(
            reason_code=reason_code.ReasonCode.PYTEST_FAIL,
            file_path=None, line=None, proof_missing="",
        )


def test_reason_code_valid_passes():
    req = reason_code.ensure_non_blind(
        reason_code=reason_code.ReasonCode.PYTEST_FAIL,
        file_path="tests/test_x.py", line=12,
        proof_missing="test_foo failed assertion",
    )
    assert req.file_path == "tests/test_x.py"


# 22 : test_manifests
def test_manifests_loads_api():
    m = test_manifests.load_manifest("api")
    assert m is not None
    assert "required_suites" in m


def test_manifest_enforce_detects_missing_suite():
    files = {"app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n"}
    r = test_manifests.enforce("api", files)
    assert r.ok is False
    assert any("crud_cycle" in s for s in r.missing_suites)


def test_project_type_detection():
    assert test_manifests.detect_project_type(
        {"app/main.py": "from fastapi import FastAPI\n",
         "tests/test_x.py": "def test_ok(): pass"},
    ) == "api"


# 23 : runtime_network_audit
def test_network_audit_flags_requests():
    files = {"app/x.py": "import requests\nrequests.get('https://evil.com')\n"}
    r = runtime_network_audit.static_scan(files)
    assert r.outbound_attempts >= 1


def test_network_audit_whitelists_tests():
    files = {"tests/test_x.py": "import httpx\nhttpx.get('http://localhost:8000')\n"}
    r = runtime_network_audit.static_scan(files)
    assert r.verdict == "clean"


# 24 : semantic_cache
def test_semantic_cache_similar_prompts():
    a = "Module Paie Algerie CNAS IRG TVA 19 TAP 2 DZD"
    b = "Module Paie Algerie avec CNAS IRG TVA 19 TAP 2 DZD"
    fa = semantic_cache.fingerprint(a)
    fb = semantic_cache.fingerprint(b)
    assert semantic_cache.similarity(fa, fb) > 0.8


def test_semantic_cache_unrelated_prompts():
    fa = semantic_cache.fingerprint("API CRUD pour tickets de support")
    fb = semantic_cache.fingerprint("Module Paie Algerie CNAS IRG TVA DZD")
    assert semantic_cache.similarity(fa, fb) < 0.6


# 25 : parallel_critic
@pytest.mark.asyncio
async def test_parallel_critic_finds_same_issues():
    files = {"app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef r(): return {}\n",
             "requirements.txt": "fastapi\n", "tests/test_x.py": "def test_ok(): pass\n"}
    r = await parallel_critic.analyze_parallel(files)
    assert r.analyses_run == 6
    assert any(i.message.startswith("Endpoint") for i in r.issues)


# 29 : quorum judge
def test_quorum_unanimous_approve():
    r = decide([])
    assert r.final_verdict == "approve"
    assert not r.has_disagreement


def test_quorum_lenient_vs_severe_disagreement():
    issues = [CriticIssue("major", "quality", f"m{i}", None) for i in range(2)]
    r = decide(issues)
    # severe voit 2 majors > 1 -> refine ; lenient voit 2 majors < 5 -> approve
    assert r.has_disagreement


def test_quorum_critical_unanimous_reject():
    issues = [CriticIssue("critical", "security", "secret", None)]
    r = decide(issues)
    assert r.final_verdict == "reject"


# 32 : impact analyzer
def test_impact_analyzer_large_blast_on_schema_change():
    r = impact_analyzer.analyze(
        ["migrations/010_new.sql", "app/schemas.py", "app/routers/x.py"],
        spec="Module DZ avec TVA",
        diff_loc=150,
    )
    assert "data" in r.recommended_revalidation
    assert r.blast_radius in ("medium", "large", "critical")


def test_impact_analyzer_small_blast_on_tiny_change():
    r = impact_analyzer.analyze(["app/util.py"], diff_loc=5)
    assert r.blast_radius == "small"


# 35 : defect_taxonomy
def test_defect_classify_security():
    nature, gravite = defect_taxonomy.classify(
        "hardcoded secret detected", "bandit scan")
    assert nature == "securite"
    assert gravite in ("bloquante", "vitale")


def test_defect_classify_conformite():
    nature, gravite = defect_taxonomy.classify("TVA 20% au lieu de 19%")
    assert nature == "conformite"


def test_defect_signature_deterministic():
    d1 = defect_taxonomy.Defect("title", "securite", "bloquante")
    d2 = defect_taxonomy.Defect("title", "securite", "vitale")
    assert defect_taxonomy.signature(d1) == defect_taxonomy.signature(d2)


# 14 : context_optimizer recap (deja couvert V4.1, on ajoute une assertion)
def test_context_optimizer_ratio_better_than_target():
    src = ("Ligne identique." * 5 + "\n") * 20
    r = context_optimizer.optimize(src)
    assert r.compression_pct >= 30


# 37 : innovation_scout transitions
def test_innovation_transitions_valid():
    from app.orchestration.innovation_scout import TRANSITIONS, STAGES
    # Chaque stage source doit figurer dans STAGES
    for src in TRANSITIONS:
        assert src in STAGES
    # Pas de transition depuis rejected ni rollback (terminaux)
    assert TRANSITIONS["rejected"] == ()
    assert TRANSITIONS["rollback"] == ()


# 17 : prompt_cache
def test_prompt_cache_builds_blocks():
    blocks = prompt_cache.build_cached_system("system rules here")
    assert blocks[0]["cache_control"]["type"] == "ephemeral"
    assert blocks[0]["text"] == "system rules here"


def test_prompt_cache_estimates_savings():
    assert prompt_cache.estimate_savings(1000, 800) == 80.0
    assert prompt_cache.estimate_savings(0, 0) == 0.0


# 19 : no-missing-checks (verifie que timed ne renvoie pas None silencieusement)
def test_timed_decorator_catches_exception():
    from scripts.verify_uba import CheckResult, timed
    @timed
    def broken() -> CheckResult:
        raise RuntimeError("boom")
    r = broken()
    assert r.status == "FAIL"
    assert "boom" in r.summary


def test_timed_decorator_catches_none_return():
    from scripts.verify_uba import CheckResult, timed
    @timed
    def returns_none() -> CheckResult:
        return None  # type: ignore[return-value]
    r = returns_none()
    assert r.status == "FAIL"
