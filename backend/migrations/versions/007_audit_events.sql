-- ============================================================
-- 007_audit_events.sql - Event sourcing append-only, retention 7 ans
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    tenant_id UUID REFERENCES tenants(id),
    actor VARCHAR(200) NOT NULL,
    action VARCHAR(80) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retention_until TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 years')
);

CREATE INDEX IF NOT EXISTS idx_audit_events_task     ON audit_events(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant   ON audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor    ON audit_events(actor);
CREATE INDEX IF NOT EXISTS idx_audit_events_action   ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_created  ON audit_events(created_at DESC);

-- Append-only : pas de UPDATE / DELETE (retention 7 ans legale)
CREATE OR REPLACE FUNCTION audit_events_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (retention 7 ans - no % allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_events_block_update ON audit_events;
CREATE TRIGGER trg_audit_events_block_update
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutations();

DROP TRIGGER IF EXISTS trg_audit_events_block_delete ON audit_events;
CREATE TRIGGER trg_audit_events_block_delete
    BEFORE DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutations();
