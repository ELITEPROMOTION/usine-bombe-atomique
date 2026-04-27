-- 036 : V8.5 — validation score v2 (breakdown + attempts)
-- 2026-04-27
--
-- Ajoute aux tables `tasks` les colonnes pour persister le breakdown reel
-- du nouveau validation_score (echelle 0..100, 6 composantes), le nombre
-- de tentatives de re-generation, et l'historique des quality gates.

-- ---------------------------------------------------------------------------
-- 1) tasks : nouvelles colonnes
-- ---------------------------------------------------------------------------
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS validation_breakdown_json JSONB,
    ADD COLUMN IF NOT EXISTS validation_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS quality_gates_history_json JSONB,
    ADD COLUMN IF NOT EXISTS validation_decision TEXT
        CHECK (validation_decision IN ('ACCEPTED','PARTIAL','REJECTED'));

-- Index pour requetes dashboard "tasks par decision"
CREATE INDEX IF NOT EXISTS idx_tasks_validation_decision
    ON tasks(validation_decision)
    WHERE validation_decision IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_validation_attempts_high
    ON tasks(validation_attempts DESC)
    WHERE validation_attempts >= 2;

-- ---------------------------------------------------------------------------
-- 2) Vue dashboard : score breakdown agrege
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_validation_breakdown_summary AS
SELECT
    validation_decision,
    COUNT(*) AS task_count,
    AVG((validation_breakdown_json->>'total')::int) AS avg_total,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (validation_breakdown_json->>'total')::int) AS p50_total,
    AVG(validation_attempts) AS avg_attempts,
    SUM(CASE WHEN validation_attempts >= 3 THEN 1 ELSE 0 END) AS exhausted_count
FROM tasks
WHERE validation_breakdown_json IS NOT NULL
GROUP BY validation_decision;

-- ---------------------------------------------------------------------------
-- 3) Seal V8.5D dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v8_5d_validation_score_v2","version":"6.3.0","date":"2026-04-27","fix":"100-pt breakdown ; tasks.validation_breakdown_json + validation_attempts + validation_decision"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_036_v8_5d',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8.5D validation score v2 sealed (chain_hash=%)', new_chain_hash;
END
$$;
