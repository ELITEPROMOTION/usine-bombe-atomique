-- ============================================================
-- 023_ctc_evidence_chain.sql - V5.3 BLOC 9
-- Chaine preuve cryptographique immuable HMAC-SHA256
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_chain_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    phase_id UUID,
    actor_type VARCHAR(20) NOT NULL
        CHECK (actor_type IN ('agent','validator','human','system')),
    actor_id VARCHAR(120) NOT NULL,
    ts_us BIGINT NOT NULL,           -- epoch microseconds
    input_hash CHAR(64) NOT NULL,
    output_hash CHAR(64) NOT NULL,
    artifact_hash CHAR(64),
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    parent_event_hash CHAR(64) NOT NULL,
    chain_hash CHAR(64) NOT NULL UNIQUE,
    signature CHAR(64) NOT NULL,      -- HMAC-SHA256
    signing_key_id VARCHAR(40) NOT NULL,
    verdict VARCHAR(20) NOT NULL
        CHECK (verdict IN ('PASS','CONDITIONAL_PASS','SOFT_FAIL','HARD_FAIL',
                           'GENESIS','CHAIN_CHECK')),
    justification TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evchain_task
    ON evidence_chain_events(task_id, ts_us);
CREATE INDEX IF NOT EXISTS idx_evchain_created
    ON evidence_chain_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evchain_actor
    ON evidence_chain_events(actor_type, actor_id);

-- Trigger append-only strict
CREATE OR REPLACE FUNCTION evidence_chain_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'evidence_chain_events is IMMUTABLE (no UPDATE/DELETE)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evchain_block_update ON evidence_chain_events;
CREATE TRIGGER trg_evchain_block_update
    BEFORE UPDATE ON evidence_chain_events
    FOR EACH ROW EXECUTE FUNCTION evidence_chain_block_mutations();

DROP TRIGGER IF EXISTS trg_evchain_block_delete ON evidence_chain_events;
CREATE TRIGGER trg_evchain_block_delete
    BEFORE DELETE ON evidence_chain_events
    FOR EACH ROW EXECUTE FUNCTION evidence_chain_block_mutations();

-- Integrity checks log
CREATE TABLE IF NOT EXISTS evidence_chain_integrity_log (
    id BIGSERIAL PRIMARY KEY,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    events_checked INTEGER NOT NULL DEFAULT 0,
    broken_links INTEGER NOT NULL DEFAULT 0,
    bad_signatures INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('preserved','broken','quarantined')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- HMAC keys registry (metadata only ; cles reelles dans Vault)
CREATE TABLE IF NOT EXISTS evidence_signing_keys (
    key_id VARCHAR(40) PRIMARY KEY,
    vault_path VARCHAR(200) NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at TIMESTAMPTZ,
    algorithm VARCHAR(20) NOT NULL DEFAULT 'HMAC-SHA256'
);
INSERT INTO evidence_signing_keys(key_id, vault_path, activated_at)
VALUES ('ctc-key-2026Q2', 'secret/uba/ctc/hmac_key_2026Q2', NOW())
ON CONFLICT (key_id) DO NOTHING;
