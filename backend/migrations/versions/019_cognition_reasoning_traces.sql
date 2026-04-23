-- ============================================================
-- 019_cognition_reasoning_traces.sql - V5.4 PARTIE 3
-- 15 tables reasoning_* + cognitive_decisions + benchmarks
-- Numerotee 019 (avant 020 CTC) pour coherence chronologique
-- meme si appliquee apres.
-- ============================================================

CREATE TABLE IF NOT EXISTS reasoning_traces (
    trace_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    session_id UUID,
    agent_id VARCHAR(120),
    problem_statement TEXT NOT NULL,
    problem_type VARCHAR(30) NOT NULL
        CHECK (problem_type IN ('simple','moderate','complex','creative',
                                 'sequential','ambiguous')),
    input_hash CHAR(64) NOT NULL,
    output_hash CHAR(64),
    rules_version VARCHAR(40) NOT NULL DEFAULT 'v5.4',
    model_version VARCHAR(40),
    technique_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_answer JSONB,
    final_confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    reasoning_fingerprint CHAR(64) NOT NULL,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress','completed','failed','killed','cached')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_rtr_task ON reasoning_traces(task_id);
CREATE INDEX IF NOT EXISTS idx_rtr_fingerprint ON reasoning_traces(reasoning_fingerprint);
CREATE INDEX IF NOT EXISTS idx_rtr_status ON reasoning_traces(status, created_at DESC);

CREATE TABLE IF NOT EXISTS reasoning_nodes (
    node_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    kind VARCHAR(20) NOT NULL
        CHECK (kind IN ('thought','action','observation','reflection','critique')),
    depth INTEGER NOT NULL DEFAULT 0,
    value DECIMAL(6,4),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rnodes_trace ON reasoning_nodes(trace_id, depth);

CREATE TABLE IF NOT EXISTS reasoning_edges (
    edge_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    src_node UUID REFERENCES reasoning_nodes(node_id) ON DELETE CASCADE,
    dst_node UUID REFERENCES reasoning_nodes(node_id) ON DELETE CASCADE,
    edge_type VARCHAR(20) NOT NULL
        CHECK (edge_type IN ('supports','derives','contradicts','aggregates','refines')),
    weight DECIMAL(6,4) NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_redges_trace ON reasoning_edges(trace_id);

CREATE TABLE IF NOT EXISTS chain_traces (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    mode VARCHAR(30) NOT NULL
        CHECK (mode IN ('zero_shot','few_shot','program_aided',
                         'self_consistent','structured')),
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    intermediate_conclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    alternatives_rejected JSONB NOT NULL DEFAULT '[]'::jsonb,
    verification_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_answer TEXT,
    confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tree_traces (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    strategy VARCHAR(20) NOT NULL
        CHECK (strategy IN ('dfs','bfs','best_first','mcts')),
    max_depth INTEGER NOT NULL,
    branching_factor INTEGER NOT NULL,
    nodes_generated INTEGER NOT NULL DEFAULT 0,
    nodes_pruned INTEGER NOT NULL DEFAULT 0,
    best_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_score DECIMAL(6,4) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS graph_traces (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    node_count INTEGER NOT NULL DEFAULT 0,
    edge_count INTEGER NOT NULL DEFAULT 0,
    contradictions JSONB NOT NULL DEFAULT '[]'::jsonb,
    convergences JSONB NOT NULL DEFAULT '[]'::jsonb,
    dominant_paths JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS debate_sessions (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    role_a VARCHAR(60) NOT NULL,
    role_b VARCHAR(60) NOT NULL,
    rounds INTEGER NOT NULL DEFAULT 0,
    devils_advocate_activated BOOLEAN NOT NULL DEFAULT FALSE,
    judge_verdict VARCHAR(20)
        CHECK (judge_verdict IS NULL OR judge_verdict IN
               ('A_wins','B_wins','hybrid_synthesis','escalate')),
    judge_rationale TEXT,
    transcript JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS reflections (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    cycle INTEGER NOT NULL,
    premortem_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    improvements JSONB NOT NULL DEFAULT '[]'::jsonb,
    v1_solution TEXT,
    v2_solution TEXT,
    improvement_delta DECIMAL(6,4) NOT NULL DEFAULT 0,
    converged BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mcts_runs (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    simulations INTEGER NOT NULL DEFAULT 0,
    exploration_c DECIMAL(6,4) NOT NULL DEFAULT 1.4142,
    best_action JSONB,
    ucb1_scores JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS constitutional_checks (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    principle VARCHAR(10) NOT NULL
        CHECK (principle IN ('P1','P2','P3','P4','P5','P6','P7')),
    passed BOOLEAN NOT NULL,
    violation_reason TEXT,
    regeneration_constraints JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_const_checks_principle
    ON constitutional_checks(principle, passed);

CREATE TABLE IF NOT EXISTS uncertainty_reports (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    aleatory DECIMAL(6,4) NOT NULL DEFAULT 0,
    epistemic DECIMAL(6,4) NOT NULL DEFAULT 0,
    ontological DECIMAL(6,4) NOT NULL DEFAULT 0,
    computational DECIMAL(6,4) NOT NULL DEFAULT 0,
    credible_low DECIMAL(6,4) NOT NULL DEFAULT 0,
    credible_high DECIMAL(6,4) NOT NULL DEFAULT 1,
    propagation JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS bias_reports (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    biases_detected JSONB NOT NULL DEFAULT '[]'::jsonb,
    mitigations_applied JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS meta_cognitive_reports (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    problem_class VARCHAR(30) NOT NULL,
    strategy_selected VARCHAR(60) NOT NULL,
    resources_allocated JSONB NOT NULL DEFAULT '{}'::jsonb,
    stuck_states_detected INTEGER NOT NULL DEFAULT 0,
    loops_detected INTEGER NOT NULL DEFAULT 0,
    stop_reason VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS cognitive_decisions (
    decision_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE SET NULL,
    chosen JSONB NOT NULL,
    alternatives JSONB NOT NULL DEFAULT '[]'::jsonb,
    justification TEXT,
    confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (risk_level IN ('low','medium','high','critical')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cognitive_benchmarks (
    id BIGSERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    family VARCHAR(30) NOT NULL
        CHECK (family IN ('logic','mathematical','coding',
                           'reasoning_heavy','compliance')),
    score_0_100 DECIMAL(6,2) NOT NULL DEFAULT 0,
    baseline_delta DECIMAL(6,2),
    n_samples INTEGER NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Cache semantique des reasoning (pgvector ready, mais fallback sans)
CREATE TABLE IF NOT EXISTS reasoning_cache (
    cache_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    problem_hash CHAR(64) NOT NULL UNIQUE,
    problem_statement TEXT NOT NULL,
    final_answer JSONB,
    confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    original_trace_id UUID REFERENCES reasoning_traces(trace_id)
        ON DELETE SET NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);

-- Dependency graph : trace parent → traces derivees
CREATE TABLE IF NOT EXISTS reasoning_dependencies (
    id BIGSERIAL PRIMARY KEY,
    parent_trace UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    child_trace UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    dependency_type VARCHAR(30) NOT NULL DEFAULT 'derives',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Circuit breaker kill events
CREATE TABLE IF NOT EXISTS cognitive_kill_events (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE SET NULL,
    reason VARCHAR(40) NOT NULL
        CHECK (reason IN ('timeout_5min','tokens_100k','iterations_50',
                           'memory_2gb','infinite_loop','stuck_state')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Human reasoning overrides
CREATE TABLE IF NOT EXISTS cognitive_human_overrides (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE SET NULL,
    human_id VARCHAR(120) NOT NULL,
    new_decision JSONB NOT NULL,
    justification TEXT NOT NULL CHECK (length(justification) >= 50),
    impact_level VARCHAR(20) NOT NULL DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Adversarial test results
CREATE TABLE IF NOT EXISTS cognitive_adversarial_tests (
    id BIGSERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scenario VARCHAR(120) NOT NULL,
    expected_behavior VARCHAR(60) NOT NULL,   -- "declare_unknown","escalate","conflict_signaled"
    actual_behavior VARCHAR(60) NOT NULL,
    passed BOOLEAN NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Reproducibility test results
CREATE TABLE IF NOT EXISTS cognitive_reproducibility_runs (
    id BIGSERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    traces_replayed INTEGER NOT NULL DEFAULT 0,
    identical INTEGER NOT NULL DEFAULT 0,
    drifted INTEGER NOT NULL DEFAULT 0,
    drift_details JSONB NOT NULL DEFAULT '[]'::jsonb
);
