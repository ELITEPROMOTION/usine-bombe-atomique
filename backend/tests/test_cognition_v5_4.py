"""V5.4 - Tests Cognitive Reasoning Core.

Couvre : reasoning_trace_models, meta_cognition, uncertainty, bias,
cot (5 modes), tree_of_thoughts, graph_of_thoughts, react,
reflexion (premortem), debate, mcts, self_discover,
constitutional (7 principes), recursive_refinement (8 niveaux),
circuit_breaker, cache_semantic, adversarial, fingerprint,
dependency_graph, cost_budgeter, health_monitor, human_override,
reproducibility, load_balancer, frontier, benchmarks (5 families),
reasoning_core, router endpoints.

Tous deterministes (seed fixe + solvers stubs).
"""
from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.cognition import (
    adversarial_reasoning_tester,
    bias_detector,
    cognitive_circuit_breaker,
    cognitive_dependency_graph,
    cognitive_health_monitor,
    cognitive_load_balancer,
    constitutional_ai,
    cot_engine,
    debate_engine,
    frontier_knowledge,
    graph_of_thoughts,
    human_reasoning_override,
    mcts_reasoning,
    meta_cognition,
    reasoning_benchmarks,
    reasoning_cache_semantic,
    reasoning_core,
    reasoning_cost_budgeter,
    reasoning_fingerprint,
    reasoning_reproducibility_test,
    recursive_refinement,
    reflexion_engine,
    react_engine,
    self_discover,
    tree_of_thoughts,
    uncertainty_quantifier,
)
from app.cognition.cognitive_circuit_breaker import BreakerState
from app.cognition.reasoning_core import ReasoningRequest
from app.main import app as fastapi_app


pytestmark = pytest.mark.asyncio


async def _client():
    return AsyncClient(transport=ASGITransport(app=fastapi_app),
                        base_url="http://t")


# ============================================================ meta_cognition

def test_meta_classify_simple():
    assert meta_cognition.classify_problem("What is TVA ?") == "simple"


def test_meta_classify_complex():
    assert meta_cognition.classify_problem(
        "Design a multi-step critical architecture") == "complex"


def test_meta_classify_creative():
    assert meta_cognition.classify_problem(
        "Brainstorm creative names for the product") == "creative"


def test_meta_classify_ambiguous():
    assert meta_cognition.classify_problem(
        "Should we use X or Y ? unclear") == "ambiguous"


def test_meta_decide_strategy_returns_techniques():
    d = meta_cognition.decide_strategy(
        "Design a complex system", criticality="medium")
    assert len(d.strategy_techniques) >= 2
    assert d.budget_tokens > 0


def test_meta_decide_critical_doubles_budget():
    d_med = meta_cognition.decide_strategy("simple question", criticality="medium")
    d_crit = meta_cognition.decide_strategy("simple question", criticality="critical")
    assert d_crit.budget_tokens > d_med.budget_tokens


def test_meta_detect_stuck():
    assert meta_cognition.detect_stuck(["a", "a", "a"], "a", 3) is True
    assert meta_cognition.detect_stuck(["a", "b", "c"], "d", 3) is False


def test_meta_detect_loop():
    traj = ["a", "b", "c", "a", "b", "c"]
    assert meta_cognition.detect_loop(traj, window=3) is True


def test_meta_build_report():
    d = meta_cognition.decide_strategy("simple q", criticality="medium")
    r = meta_cognition.build_report(d, stuck_states=2, loops=1,
                                      stop_reason="converged")
    assert r.stuck_states_detected == 2
    assert r.stop_reason == "converged"


# ============================================================ uncertainty

def test_uncertainty_detect_vague():
    assert uncertainty_quantifier.has_vague_rhetoric("il semble que") is True
    assert uncertainty_quantifier.has_vague_rhetoric("exactly 42") is False


def test_uncertainty_aleatory_from_variance():
    assert uncertainty_quantifier.aleatory_from_variance([]) == 0.0
    assert uncertainty_quantifier.aleatory_from_variance([0.5, 0.5, 0.5]) == 0.0
    high = uncertainty_quantifier.aleatory_from_variance([0.0, 1.0, 0.0, 1.0])
    assert high > 0.3


def test_uncertainty_epistemic_sources():
    assert uncertainty_quantifier.epistemic_from_sources(0) == 1.0
    assert uncertainty_quantifier.epistemic_from_sources(3) == 0.0


def test_uncertainty_build_report_shape():
    r = uncertainty_quantifier.build_report(
        samples=[0.7, 0.8, 0.9], sources_count=3,
        domain_fit=0.9, budget_used=100, budget_total=1000,
        mean_confidence=0.8)
    assert 0 <= r.credible_low <= r.credible_high <= 1


def test_uncertainty_propagate_envelope():
    a = uncertainty_quantifier.build_report(
        samples=[0.7], sources_count=3, domain_fit=0.9,
        budget_used=100, budget_total=1000, mean_confidence=0.8)
    b = uncertainty_quantifier.build_report(
        samples=[0.2], sources_count=1, domain_fit=0.4,
        budget_used=500, budget_total=1000, mean_confidence=0.5)
    merged = uncertainty_quantifier.propagate(parent=a, increment=b)
    assert merged.epistemic >= a.epistemic


# ============================================================ bias

def test_bias_detect_overconfidence():
    d = bias_detector.detect("This is definitely correct, no doubt")
    assert any(b.name == "overconfidence" for b in d)


def test_bias_detect_groupthink_votes():
    d = bias_detector.detect("simple text", votes_convergence_ratio=0.95)
    assert any(b.name == "groupthink" for b in d)


def test_bias_mitigations_active():
    d = bias_detector.detect("Definitely correct", votes_convergence_ratio=0.0)
    mit = bias_detector.apply_mitigations(d)
    assert any(m["action"] == "strengthen_critic" for m in mit)


def test_bias_build_report():
    r = bias_detector.build_report("obviously definitely correct",
                                     votes_convergence_ratio=0.0)
    assert len(r.biases_detected) >= 1


# ============================================================ fingerprint

def test_fp_normalize():
    assert reasoning_fingerprint.normalize("  Hello  World.  ") == "hello world"


def test_fp_stable():
    a = reasoning_fingerprint.fingerprint("Q1", ["cot"])
    b = reasoning_fingerprint.fingerprint("q1", ["cot"])
    assert a == b


def test_fp_changes_on_path():
    a = reasoning_fingerprint.fingerprint("Q", ["cot"])
    b = reasoning_fingerprint.fingerprint("Q", ["tot"])
    assert a != b


# ============================================================ CoT (5 modes)

def test_cot_zero_shot_produces_steps():
    t = cot_engine.zero_shot_cot("What is 2+2?")
    assert t.mode == "zero_shot"
    assert len(t.steps) >= 1


def test_cot_few_shot_uses_examples():
    examples = [{"question": "1+1", "answer": "2"},
                {"question": "2+2", "answer": "4"}]
    t = cot_engine.few_shot_cot("3+3", examples)
    assert t.mode == "few_shot"


def test_cot_program_aided_math_ok():
    t = cot_engine.program_aided_cot("result = 10 + 5")
    assert t.mode == "program_aided"
    assert t.final_answer == "15"


def test_cot_program_aided_no_numeric():
    t = cot_engine.program_aided_cot("Definis la vie")
    assert t.final_answer == "no_numeric"


def test_cot_self_consistent_votes():
    t = cot_engine.self_consistent_cot("What is A?", n_samples=5)
    assert t.mode == "self_consistent"
    assert 0 <= t.confidence <= 1


def test_cot_structured_has_5_sections():
    t = cot_engine.structured_cot("Question complexe a analyser")
    assert t.mode == "structured"
    assert len(t.steps) == 5  # Given/Assumptions/Reasoning/Verification/Conclusion


# ============================================================ ToT

def test_tot_build_dfs():
    r = tree_of_thoughts.build_tree("root", strategy="dfs",
                                      max_depth=2, branching=2)
    assert r.strategy == "dfs"
    # 1 root + 2 depth1 + 4 depth2 = max 7 nodes
    assert len(r.nodes) >= 3


def test_tot_build_bfs():
    r = tree_of_thoughts.build_tree("root", strategy="bfs",
                                      max_depth=2, branching=2)
    assert r.strategy == "bfs"


def test_tot_best_first_returns_path():
    r = tree_of_thoughts.build_tree("root", strategy="best_first",
                                      max_depth=3, branching=2)
    assert len(r.best_path) >= 1


def test_tot_unknown_strategy_raises():
    with pytest.raises(ValueError):
        tree_of_thoughts.build_tree("r", strategy="nope")


def test_tot_evaluate_thought_in_range():
    v = tree_of_thoughts.evaluate_thought("donc il faut faire X parce que Y")
    assert 0 <= v <= 1


# ============================================================ GoT

def test_got_build_adds_nodes():
    g = graph_of_thoughts.GraphBuild()
    a = g.add("A", value=0.7)
    b = g.add("B", value=0.5)
    g.link(a, b, "supports")
    trace = graph_of_thoughts.build_trace(g)
    assert len(trace.nodes) == 2
    assert len(trace.edges) == 1


def test_got_detect_contradictions():
    g = graph_of_thoughts.GraphBuild()
    a = g.add("A"); b = g.add("B")
    g.link(a, b, "contradicts")
    trace = graph_of_thoughts.build_trace(g)
    assert len(trace.contradictions) == 1


def test_got_aggregate():
    g = graph_of_thoughts.GraphBuild()
    ids = [g.add(f"T{i}", value=0.5) for i in range(3)]
    merged = graph_of_thoughts.aggregate(g, ids)
    assert merged in g.nodes


def test_got_refine_creates_child():
    g = graph_of_thoughts.GraphBuild()
    a = g.add("A", value=0.5)
    r = graph_of_thoughts.refine(g, a, "A refined")
    assert g.nodes[r].value > g.nodes[a].value


def test_got_convergence_detected():
    g = graph_of_thoughts.GraphBuild()
    a = g.add("A"); b = g.add("B"); c = g.add("C")
    g.link(a, c, "supports")
    g.link(b, c, "supports")
    trace = graph_of_thoughts.build_trace(g)
    assert len(trace.convergences) == 1


# ============================================================ ReAct

async def test_react_runs_and_stops():
    r = await react_engine.run("test problem", max_iterations=5)
    assert len(r.steps) >= 1
    assert r.stop_reason in ("converged", "max_iterations",
                              "repeated_action_escalate",
                              "policy_no_action")


async def test_react_max_iterations():
    r = await react_engine.run("test", max_iterations=2)
    assert len(r.steps) <= 2


async def test_react_tool_dispatch_called():
    hits = []
    def dispatcher(name, args):
        hits.append(name)
        return f"obs_{name}"
    r = await react_engine.run(
        "test", tool_dispatcher=dispatcher, max_iterations=3)
    assert len(hits) >= 1


# ============================================================ Reflexion

def test_reflexion_runs_at_least_1():
    r = reflexion_engine.run("Initial solution draft", max_cycles=3)
    assert len(r.cycles) >= 1


def test_reflexion_premortem_produces_findings():
    findings = reflexion_engine.default_premortem("Solution X")
    assert len(findings) == 5


def test_reflexion_converges_on_marginal():
    r = reflexion_engine.run("Already perfect solution",
                              max_cycles=3, min_delta=0.9)
    # Should converge early with such high min_delta
    assert len(r.cycles) <= 3


def test_reflexion_max_cycles_respected():
    r = reflexion_engine.run("Sol", max_cycles=2, min_delta=0.0)
    assert len(r.cycles) <= 2


# ============================================================ Debate

def test_debate_produces_verdict():
    t = debate_engine.debate("Should we migrate ?")
    assert t.judge_verdict in ("A_wins", "B_wins", "hybrid_synthesis", "escalate")
    assert t.rounds


def test_debate_role_pairs_exist():
    assert len(debate_engine.ROLE_PAIRS) >= 5


def test_debate_max_rounds_respected():
    cfg = debate_engine.DebateConfig(role_a="X", role_b="Y", max_rounds=2)
    t = debate_engine.debate("q", cfg=cfg)
    # 2 rounds * 2 speakers = 4 DebateRounds
    assert len(t.rounds) == 4


# ============================================================ MCTS

def test_mcts_runs_and_picks_action():
    r = mcts_reasoning.run_mcts("root", n_simulations=20, seed=1)
    assert r.tree_size > 1
    assert r.best_action is not None


def test_mcts_ucb1_formula_infinity_for_unvisited():
    from app.cognition.mcts_reasoning import MctsNode, ucb1
    n = MctsNode(id="x", parent=None, action=None, visits=0)
    assert ucb1(n, 10) == float("inf")


def test_mcts_deterministic_with_seed():
    a = mcts_reasoning.run_mcts("s", n_simulations=15, seed=42)
    b = mcts_reasoning.run_mcts("s", n_simulations=15, seed=42)
    assert a.best_action == b.best_action


# ============================================================ Self-Discover

def test_sd_select_returns_modules():
    s = self_discover.select("complex")
    assert len(s) >= 1
    assert all(m in self_discover.MODULES for m in s)


def test_sd_select_respects_budget():
    s = self_discover.select("complex", cost_budget=0.2)
    total = sum(self_discover.MODULE_COST[m] for m in s)
    assert total <= 0.35   # + une marge pour minimum 1 module


def test_sd_plan_complete():
    p = self_discover.plan("design a complex system", "complex")
    assert p.selected_modules
    assert p.adapted_prompts
    assert p.implementation_order


# ============================================================ Constitutional

def test_constitutional_principles_count():
    assert len(constitutional_ai.PRINCIPLES) == 7


def test_constitutional_p1_security_violation():
    ok, reason = constitutional_ai.check_principle(
        "Let's expose secret to external API", "P1")
    assert ok is False
    assert reason and "P1" in reason


def test_constitutional_p6_reversibility_violation():
    ok, _ = constitutional_ai.check_principle(
        "DROP TABLE users;", "P6")
    assert ok is False


def test_constitutional_p3_honesty_violation():
    ok, _ = constitutional_ai.check_principle(
        "I am 100% sure it will work", "P3")
    assert ok is False


def test_constitutional_check_all_builds_report():
    r = constitutional_ai.check_all("normal text nothing bad")
    assert r.final_pass is True
    assert len(r.principle_results) == 7


def test_constitutional_regen_prompt():
    violations = [{"principle": "P3", "reason": "hallucination"}]
    p = constitutional_ai.build_regen_prompt("original", violations)
    assert "CONTRAINTES RENFORCEES" in p
    assert "P3" in p


def test_constitutional_unknown_principle_raises():
    with pytest.raises(KeyError):
        constitutional_ai.check_principle("text", "P99")


# ============================================================ Recursive refinement

def test_refine_produces_8_max_steps():
    r = recursive_refinement.refine("solution", target_level=7)
    assert len(r.steps) >= 1
    assert r.final_level_reached <= 7


def test_refine_stops_on_target():
    r = recursive_refinement.refine("s", target_level=2)
    assert r.final_level_reached <= 2


def test_refine_levels_count():
    assert len(recursive_refinement.LEVELS) == 8


# ============================================================ Circuit breaker

def test_cb_not_triggered_initial():
    s = BreakerState(start_time=__import__("time").perf_counter())
    triggered, reason = cognitive_circuit_breaker.check(s)
    assert not triggered


def test_cb_triggered_on_tokens():
    s = BreakerState(start_time=__import__("time").perf_counter(),
                     tokens_used=200_000)
    triggered, reason = cognitive_circuit_breaker.check(s)
    assert triggered and reason == "tokens_100k"


def test_cb_triggered_on_iterations():
    s = BreakerState(start_time=__import__("time").perf_counter(),
                     iterations=100)
    triggered, reason = cognitive_circuit_breaker.check(s)
    assert triggered and reason == "iterations_50"


async def test_cb_record_kill(pool):
    i = await cognitive_circuit_breaker.record_kill(
        pool, trace_id=None, reason="tokens_100k",
        details={"tokens": 150_000})
    assert i > 0


async def test_cb_record_bad_reason_raises(pool):
    with pytest.raises(ValueError):
        await cognitive_circuit_breaker.record_kill(
            pool, trace_id=None, reason="made_up_reason")


# ============================================================ Cache semantic

async def test_cache_miss_initial(pool):
    r = await reasoning_cache_semantic.lookup(pool, f"unique {uuid.uuid4()}")
    assert r is None


async def test_cache_store_and_hit(pool):
    q = f"cache test {uuid.uuid4().hex[:8]}"
    await reasoning_cache_semantic.store(
        pool, problem_statement=q,
        final_answer={"v": 1}, confidence=0.88)
    r = await reasoning_cache_semantic.lookup(pool, q)
    assert r is not None
    assert r["confidence"] == 0.88


async def test_cache_stats(pool):
    s = await reasoning_cache_semantic.stats(pool)
    assert "total_entries" in s


# ============================================================ Adversarial

def test_adversarial_has_50_scenarios():
    assert len(adversarial_reasoning_tester.ADVERSARIAL_SCENARIOS) == 50


def test_adversarial_detect_unknown():
    assert adversarial_reasoning_tester.detect_behavior(
        "je ne sais pas exactement") == "declare_unknown"


def test_adversarial_detect_escalate():
    assert adversarial_reasoning_tester.detect_behavior(
        "escalade to ahmed needed") == "escalate"


def test_adversarial_detect_conflict():
    assert adversarial_reasoning_tester.detect_behavior(
        "contradiction detected between sources") == "conflict_signaled"


async def test_adversarial_run_all_default_responder(pool):
    r = await adversarial_reasoning_tester.run_all(pool)
    assert r["total"] == 50
    # Default responder = "Je ne sais pas" -> passes scenarios expecting declare_unknown
    assert r["passed"] >= 20


# ============================================================ Dependency graph

async def test_dep_add_and_descendants(pool):
    # Create 3 traces
    async with pool.acquire() as conn:
        import json as _j
        ids = []
        for i in range(3):
            row = await conn.fetchrow(
                """
                INSERT INTO reasoning_traces(
                    problem_statement, problem_type, input_hash,
                    reasoning_fingerprint, status)
                VALUES ($1, 'simple', $2, $3, 'completed')
                RETURNING trace_id
                """, f"dep test {i}", "h" * 64, f"fp{i:064d}"[:64])
            ids.append(str(row["trace_id"]))
    # Chain : 0 -> 1 -> 2
    await cognitive_dependency_graph.add_dependency(
        pool, parent_trace=ids[0], child_trace=ids[1])
    await cognitive_dependency_graph.add_dependency(
        pool, parent_trace=ids[1], child_trace=ids[2])
    desc = await cognitive_dependency_graph.descendants(pool, ids[0])
    assert len(desc) == 2


async def test_dep_ancestors(pool):
    async with pool.acquire() as conn:
        rows = []
        for i in range(2):
            r = await conn.fetchrow(
                """
                INSERT INTO reasoning_traces(problem_statement, problem_type,
                    input_hash, reasoning_fingerprint, status)
                VALUES ($1, 'simple', $2, $3, 'completed')
                RETURNING trace_id
                """, f"anc {i} {uuid.uuid4().hex[:6]}", "a" * 64,
                __import__("secrets").token_hex(32))
            rows.append(str(r["trace_id"]))
    await cognitive_dependency_graph.add_dependency(
        pool, parent_trace=rows[0], child_trace=rows[1])
    anc = await cognitive_dependency_graph.ancestors(pool, rows[1])
    assert any(a["trace_id"] == rows[0] for a in anc)


# ============================================================ Cost budgeter

def test_budget_p0_largest():
    p0 = reasoning_cost_budgeter.allocate("P0")
    p3 = reasoning_cost_budgeter.allocate("P3")
    assert p0.tokens_max > p3.tokens_max


def test_budget_bad_tier_raises():
    with pytest.raises(ValueError):
        reasoning_cost_budgeter.allocate("P99")


def test_budget_consumed_ratio():
    assert reasoning_cost_budgeter.consumed_ratio(1000, "P1") < 1.0
    assert reasoning_cost_budgeter.consumed_ratio(60_000, "P1") == 1.0


def test_budget_classify_criticality():
    assert reasoning_cost_budgeter.classify_criticality(
        "simple", "critical") == "P0"
    assert reasoning_cost_budgeter.classify_criticality(
        "complex", "medium") == "P1"
    assert reasoning_cost_budgeter.classify_criticality(
        "simple", "low") == "P3"


# ============================================================ Health monitor

async def test_health_weekly_scores_shape(pool):
    r = await cognitive_health_monitor.weekly_scores(pool)
    assert "current_week_avg" in r
    assert "regression_detected" in r


async def test_health_report_has_families(pool):
    r = await cognitive_health_monitor.health_report(pool)
    assert "by_family" in r
    assert "overall" in r


# ============================================================ Human override

async def test_override_requires_min_justification(pool, seeded_task_id):
    # Create a trace first
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO reasoning_traces(task_id, problem_statement,
                problem_type, input_hash, reasoning_fingerprint, status)
            VALUES ($1, 'override test', 'simple', $2, $3, 'completed')
            RETURNING trace_id
            """, uuid.UUID(seeded_task_id), "z" * 64,
            __import__("secrets").token_hex(32))
    tid = str(row["trace_id"])
    with pytest.raises(ValueError):
        await human_reasoning_override.override_reasoning(
            pool, trace_id=tid, human_id="ahmed",
            new_decision={"x": 1}, justification="too short")


async def test_override_ok_with_justification(pool, seeded_task_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO reasoning_traces(task_id, problem_statement,
                problem_type, input_hash, reasoning_fingerprint, status)
            VALUES ($1, 'override ok', 'simple', $2, $3, 'completed')
            RETURNING trace_id
            """, uuid.UUID(seeded_task_id), "y" * 64,
            __import__("secrets").token_hex(32))
    tid = str(row["trace_id"])
    i = await human_reasoning_override.override_reasoning(
        pool, trace_id=tid, human_id="ahmed",
        new_decision={"verdict": "approve"},
        justification="Executive override based on business priority "
                       "with Ahmed authority validated against Dendani policy.")
    assert i > 0


# ============================================================ Reproducibility

async def test_repro_replay(pool):
    # Create some traces first
    async with pool.acquire() as conn:
        for i in range(5):
            await conn.execute(
                """
                INSERT INTO reasoning_traces(problem_statement, problem_type,
                    input_hash, reasoning_fingerprint, final_answer,
                    final_confidence, status)
                VALUES ($1, 'simple', $2, $3, $4::jsonb, $5, 'completed')
                """, f"repro {i} {uuid.uuid4().hex[:6]}",
                __import__("secrets").token_hex(32),
                __import__("secrets").token_hex(32),
                json.dumps("answer"), 0.80)
    r = await reasoning_reproducibility_test.replay_traces(
        pool, sample_size=3)
    assert "total" in r
    assert "identical" in r


async def test_repro_latest_runs(pool):
    r = await reasoning_reproducibility_test.latest_runs(pool)
    assert isinstance(r, list)


# ============================================================ Load balancer

async def test_load_snapshot_shape(pool):
    s = await cognitive_load_balancer.snapshot(pool)
    assert "by_status" in s
    assert "queue_name" in s


def test_load_pick_worker():
    w = cognitive_load_balancer.pick_worker_for_tier("P1")
    assert w.endswith(":P1")


def test_load_should_throttle():
    assert cognitive_load_balancer.should_throttle(100, "P0") is True
    assert cognitive_load_balancer.should_throttle(2, "P3") is False


# ============================================================ Frontier

def test_frontier_catalog_count():
    c = frontier_knowledge.catalog()
    assert c["total"] >= 5


def test_frontier_relevance_scores():
    s = frontier_knowledge.relevance_score(
        ["reasoning", "chain"], "anthropic_research")
    assert s > 0.5


def test_frontier_by_domain():
    srcs = frontier_knowledge.by_domain("ai_frontier")
    assert len(srcs) >= 3


# ============================================================ Benchmarks

def test_benchmarks_families_count():
    assert len(reasoning_benchmarks.FAMILIES) == 5


def test_benchmarks_run_family_logic():
    r = reasoning_benchmarks.run_family("logic")
    assert r.score_0_100 >= 0
    assert r.n_samples > 0


def test_benchmarks_run_family_unknown_raises():
    with pytest.raises(ValueError):
        reasoning_benchmarks.run_family("nope")


async def test_benchmarks_run_all(pool):
    r = await reasoning_benchmarks.run_all(pool)
    assert "overall_score" in r
    assert "by_family" in r


async def test_benchmarks_latest(pool):
    await reasoning_benchmarks.run_all(pool)
    r = await reasoning_benchmarks.latest(pool)
    assert len(r) >= 1


# ============================================================ Reasoning Core

async def test_reasoning_core_end_to_end(pool, seeded_task_id):
    req = ReasoningRequest(
        problem_statement="What strategy for complex migration?",
        task_id=seeded_task_id, criticality="medium")
    trace = await reasoning_core.reason(pool, req)
    assert trace.trace_id is not None
    assert trace.status == "completed"
    assert trace.final_confidence > 0


async def test_reasoning_core_get_trace(pool, seeded_task_id):
    req = ReasoningRequest(
        problem_statement="simple q?", task_id=seeded_task_id)
    trace = await reasoning_core.reason(pool, req)
    fetched = await reasoning_core.get_trace(pool, trace.trace_id)
    assert fetched is not None
    assert fetched["trace_id"] == trace.trace_id


async def test_reasoning_core_list_traces(pool):
    r = await reasoning_core.list_traces(pool, limit=5)
    assert isinstance(r, list)


# ============================================================ Router smoke

async def test_router_cog_health(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/health")
    assert r.status_code == 200


async def test_router_cog_live(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/live")
    assert r.status_code == 200


async def test_router_reason(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/reason",
                          json={"problem_statement": "test"})
    assert r.status_code == 200


async def test_router_reason_no_statement(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/reason", json={})
    assert r.status_code in (400, 429)


async def test_router_cot_zero_shot(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/cot/zero_shot",
                          json={"problem": "What is AI?"})
    assert r.status_code == 200


async def test_router_cot_structured(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/cot/structured",
                          json={"problem": "analyze"})
    assert r.status_code == 200


async def test_router_tot(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/tot",
                          json={"root_thought": "root"})
    assert r.status_code == 200


async def test_router_got(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/got",
                          json={"thoughts": ["A", "B", "C"]})
    assert r.status_code == 200


async def test_router_react(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/react",
                          json={"problem": "solve this"})
    assert r.status_code == 200


async def test_router_reflexion(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/reflexion",
                          json={"solution": "draft"})
    assert r.status_code == 200


async def test_router_debate(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/debate",
                          json={"question": "x or y ?"})
    assert r.status_code == 200


async def test_router_mcts(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/mcts",
                          json={"state": "root", "n_simulations": 10,
                                 "seed": 7})
    assert r.status_code == 200


async def test_router_self_discover(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/self_discover",
                          json={"problem": "design", "problem_type": "complex"})
    assert r.status_code == 200


async def test_router_constitutional_check(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/constitutional/check",
                          json={"text": "normal text"})
    assert r.status_code == 200


async def test_router_recursive_refine(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/reasoning/recursive_refinement",
                          json={"solution": "sol"})
    assert r.status_code == 200


async def test_router_benchmarks_run(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/cognition/benchmarks/run")
    assert r.status_code == 200


async def test_router_benchmarks_latest(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/benchmarks/latest")
    assert r.status_code == 200


async def test_router_circuit_recent(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/circuit/recent")
    assert r.status_code == 200


async def test_router_cache_stats(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/cache/stats")
    assert r.status_code == 200


async def test_router_adversarial_run(pool):
    async with await _client() as c:
        r = await c.post("/api/v1/cognition/adversarial/run")
    assert r.status_code == 200


async def test_router_load_snapshot(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/load/snapshot")
    assert r.status_code == 200


async def test_router_frontier(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/frontier/catalog")
    assert r.status_code == 200


async def test_router_repro_latest(pool):
    async with await _client() as c:
        r = await c.get("/api/v1/cognition/reproducibility/latest")
    assert r.status_code == 200
