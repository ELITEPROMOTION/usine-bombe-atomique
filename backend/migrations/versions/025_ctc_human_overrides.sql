-- ============================================================
-- 025_ctc_human_overrides.sql - V5.3 BLOC 17
-- Human overrides traceables + snapshots + backward compatibility
-- ============================================================

CREATE TABLE IF NOT EXISTS human_overrides (
    override_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    original_verdict_id UUID,
    new_verdict VARCHAR(30) NOT NULL,
    justification TEXT NOT NULL,
    human_id VARCHAR(120) NOT NULL,
    evidence_chain_event_id UUID REFERENCES evidence_chain_events(event_id),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','re_evaluated','expired','revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    re_evaluated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_overrides_status
    ON human_overrides(status, created_at DESC);

-- State snapshots (metadata - binary dump offline)
CREATE TABLE IF NOT EXISTS truth_engine_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tables_included JSONB NOT NULL,
    storage_path VARCHAR(500),
    compressed_bytes BIGINT,
    chain_integrity_ok BOOLEAN NOT NULL DEFAULT TRUE,
    retention_until TIMESTAMPTZ NOT NULL
        DEFAULT (NOW() + INTERVAL '90 days'),
    checksum CHAR(64)
);

-- Backward compatibility replay runs
CREATE TABLE IF NOT EXISTS truth_backward_replay (
    id BIGSERIAL PRIMARY KEY,
    version_old VARCHAR(40) NOT NULL,
    version_new VARCHAR(40) NOT NULL,
    verdicts_replayed INTEGER NOT NULL DEFAULT 0,
    identical INTEGER NOT NULL DEFAULT 0,
    improved INTEGER NOT NULL DEFAULT 0,
    regressed INTEGER NOT NULL DEFAULT 0,
    regression_details JSONB NOT NULL DEFAULT '[]'::jsonb,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verdict_pass BOOLEAN NOT NULL DEFAULT FALSE
);

-- Meta Truth Audit weekly results
CREATE TABLE IF NOT EXISTS meta_truth_audits (
    id BIGSERIAL PRIMARY KEY,
    audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    truth_tests_pass BOOLEAN NOT NULL DEFAULT FALSE,
    chain_integrity_ok BOOLEAN NOT NULL DEFAULT FALSE,
    sources_consulted INTEGER NOT NULL DEFAULT 0,
    rework_convergence_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    false_positive_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    false_negative_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    verdict VARCHAR(20) NOT NULL
        CHECK (verdict IN ('OK','REGRESSION','CRITICAL')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Budget + latency tracking
CREATE TABLE IF NOT EXISTS truth_budget_usage (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    layer VARCHAR(40) NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    degraded_mode BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Chaos test results for CTC
CREATE TABLE IF NOT EXISTS truth_chaos_runs (
    id BIGSERIAL PRIMARY KEY,
    scenario VARCHAR(80) NOT NULL,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    ctc_continued_validation BOOLEAN NOT NULL DEFAULT FALSE,
    fallback_executed BOOLEAN NOT NULL DEFAULT FALSE,
    chain_integrity_preserved BOOLEAN NOT NULL DEFAULT FALSE,
    alerts_triggered INTEGER NOT NULL DEFAULT 0,
    recovery_time_seconds INTEGER NOT NULL DEFAULT 0,
    verdict VARCHAR(20) NOT NULL
        CHECK (verdict IN ('PASS','FAIL','DEGRADED'))
);
