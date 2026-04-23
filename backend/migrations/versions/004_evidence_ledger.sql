-- ============================================================
-- 004_evidence_ledger.sql - Journal immuable chaine SHA-256
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_ledger (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    actor VARCHAR(120) NOT NULL,
    kind VARCHAR(40) NOT NULL
        CHECK (kind IN ('decision','artifact','test','override',
                        'arbiter','contradiction','hypothesis',
                        'challenger','repair','contract_violation')),
    payload_hash CHAR(64) NOT NULL,
    prev_hash CHAR(64) NOT NULL,
    chain_hash CHAR(64) NOT NULL UNIQUE,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_task    ON evidence_ledger(task_id);
CREATE INDEX IF NOT EXISTS idx_evidence_kind    ON evidence_ledger(kind);
CREATE INDEX IF NOT EXISTS idx_evidence_created ON evidence_ledger(created_at DESC);

-- Trigger append-only : aucune UPDATE/DELETE autorisee
CREATE OR REPLACE FUNCTION evidence_ledger_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'evidence_ledger is append-only (no % allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evidence_block_update ON evidence_ledger;
CREATE TRIGGER trg_evidence_block_update
    BEFORE UPDATE ON evidence_ledger
    FOR EACH ROW EXECUTE FUNCTION evidence_ledger_block_mutations();

DROP TRIGGER IF EXISTS trg_evidence_block_delete ON evidence_ledger;
CREATE TRIGGER trg_evidence_block_delete
    BEFORE DELETE ON evidence_ledger
    FOR EACH ROW EXECUTE FUNCTION evidence_ledger_block_mutations();

-- Pas de genesis row : la table demarre vide. Le premier event inscrit
-- via `evidence_ledger.record()` utilise GENESIS_HASH (0*64) comme prev_hash,
-- et la chaine grossit. `verify_chain()` rejoue depuis GENESIS_HASH.
