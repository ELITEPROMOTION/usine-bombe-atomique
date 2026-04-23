-- ============================================================
-- 014_autonomy_metrics_v51.sql - V5.1 BLOC 13
-- KPIs autonomie : action_rate, ahmed_load, calibration, chaos...
-- ============================================================

CREATE TABLE IF NOT EXISTS autonomy_metrics (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_hours INTEGER NOT NULL DEFAULT 168,
    -- Action metrics
    autonomy_action_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    autonomy_weighted_by_criticity DECIMAL(6,4) NOT NULL DEFAULT 0,
    -- Avoidable escalations
    avoidable_escalation_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    escalation_precision DECIMAL(6,4) NOT NULL DEFAULT 0,
    questions_per_escalation DECIMAL(6,3) NOT NULL DEFAULT 0,
    -- Ahmed load
    ahmed_cognitive_load_minutes_per_project DECIMAL(10,2) NOT NULL DEFAULT 0,
    ahmed_interruptions_per_project DECIMAL(6,2) NOT NULL DEFAULT 0,
    autonomous_continuation_rate_after_block DECIMAL(6,4) NOT NULL DEFAULT 0,
    -- Calibration
    confidence_calibration_score DECIMAL(6,4) NOT NULL DEFAULT 0,
    patch_success_by_type JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Distribution
    c_sub_type_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Chaos / resilience
    chaos_pass_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    mean_time_to_self_heal_seconds INTEGER NOT NULL DEFAULT 0,
    -- Freshness
    artifact_freshness_median_minutes INTEGER NOT NULL DEFAULT 0,
    stale_data_incidents INTEGER NOT NULL DEFAULT 0,
    -- Permission leases
    active_leases INTEGER NOT NULL DEFAULT 0,
    lease_cap_violations INTEGER NOT NULL DEFAULT 0,
    -- Human load budget
    human_load_budget_used_pct DECIMAL(6,4) NOT NULL DEFAULT 0,
    -- Raw details
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_autonomy_metrics_captured
    ON autonomy_metrics(captured_at DESC);

-- Chaos runs journal
CREATE TABLE IF NOT EXISTS autonomy_chaos_runs (
    id BIGSERIAL PRIMARY KEY,
    scenario VARCHAR(120) NOT NULL,
    passed BOOLEAN NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    self_healed BOOLEAN NOT NULL DEFAULT FALSE,
    triggered_escalation BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chaos_runs_created
    ON autonomy_chaos_runs(created_at DESC);

-- Correlation id registry : trace un artefact de bout en bout
CREATE TABLE IF NOT EXISTS correlation_ledger (
    correlation_id VARCHAR(64) PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    origin VARCHAR(60) NOT NULL,      -- ex: "ahmed_inbox", "agent_dag"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    final_verdict VARCHAR(30),
    hop_count INTEGER NOT NULL DEFAULT 0
);

-- Intervention outcomes : apprentissage sur les vraies et fausses escalations
CREATE TABLE IF NOT EXISTS intervention_outcomes (
    id BIGSERIAL PRIMARY KEY,
    pending_request_id UUID,
    form_type CHAR(1) NOT NULL,
    c_sub_type VARCHAR(4),
    was_necessary BOOLEAN,            -- verdict retrospectif
    ahmed_response_ms INTEGER,
    autonomy_alternative TEXT,        -- ce qu'on aurait pu faire sans ahmed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_intervention_necessary
    ON intervention_outcomes(was_necessary, created_at DESC);

-- Negative escalation registry : patterns a ne PAS escalader
CREATE TABLE IF NOT EXISTS negative_escalation_registry (
    id BIGSERIAL PRIMARY KEY,
    signature VARCHAR(120) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    example_request JSONB NOT NULL,
    resolution_hint TEXT NOT NULL,
    learned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    occurrences INTEGER NOT NULL DEFAULT 1
);

-- Human Necessity Proof : preuve structuree avant toute escalation
CREATE TABLE IF NOT EXISTS human_necessity_proofs (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    correlation_id VARCHAR(64),
    form_type CHAR(1) NOT NULL,
    c_sub_type VARCHAR(4),
    levels_tried JSONB NOT NULL DEFAULT '[]'::jsonb,
    counterfactual JSONB NOT NULL DEFAULT '{}'::jsonb,
    proof_hash VARCHAR(64) NOT NULL,
    verdict VARCHAR(20) NOT NULL,     -- proved|rejected
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_necessity_verdict
    ON human_necessity_proofs(verdict, created_at DESC);
