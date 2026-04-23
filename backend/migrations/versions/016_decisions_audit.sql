-- ============================================================
-- 016_decisions_audit.sql - V5.2 BLOC 6
-- Table decisions_audit : trace immuable de chaque decision reasoning
-- ============================================================

CREATE TABLE IF NOT EXISTS decisions_audit (
    id BIGSERIAL PRIMARY KEY,
    decision_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    context_hash CHAR(64) NOT NULL,
    domain VARCHAR(80) NOT NULL,
    category VARCHAR(20) NOT NULL
        CHECK (category IN ('HARDCODED_FROZEN','PARAMETRIZABLE',
                             'LEARNABLE','REASONABLE')),
    chosen_value JSONB NOT NULL,
    alternatives_considered JSONB NOT NULL DEFAULT '[]'::jsonb,
    reasoning_trace TEXT NOT NULL,
    confidence_score DECIMAL(6,4) NOT NULL DEFAULT 0,
    bounds_respected BOOLEAN NOT NULL DEFAULT TRUE,
    invariants_checked JSONB NOT NULL DEFAULT '[]'::jsonb,
    quality_kernel_validation JSONB,
    actor VARCHAR(120) NOT NULL,
    correlation_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rollback_state JSONB,
    retention_until TIMESTAMPTZ NOT NULL
        DEFAULT (NOW() + INTERVAL '7 years')
);

CREATE INDEX IF NOT EXISTS idx_decisions_task
    ON decisions_audit(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_domain
    ON decisions_audit(domain, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_category
    ON decisions_audit(category, created_at DESC);

-- Trigger append-only (identique a audit_events)
CREATE OR REPLACE FUNCTION decisions_audit_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'decisions_audit is append-only (retention 7 ans, no UPDATE/DELETE)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decisions_block_update ON decisions_audit;
CREATE TRIGGER trg_decisions_block_update
    BEFORE UPDATE ON decisions_audit
    FOR EACH ROW EXECUTE FUNCTION decisions_audit_block_mutations();

DROP TRIGGER IF EXISTS trg_decisions_block_delete ON decisions_audit;
CREATE TRIGGER trg_decisions_block_delete
    BEFORE DELETE ON decisions_audit
    FOR EACH ROW EXECUTE FUNCTION decisions_audit_block_mutations();
