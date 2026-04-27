-- 035 : V8.5 — delivery quality gates persistence
-- 2026-04-27
--
-- Persiste l'historique des 6 quality gates executees avant chaque livraison
-- d'un projet, pour audit + dashboard + auto-retry.
--
-- Tables :
--   delivery_quality_gates  : ligne par execution d'un gate
--   quality_gate_failures   : detail par echec (pour feedback aux agents)

-- ---------------------------------------------------------------------------
-- 1) delivery_quality_gates : historique brut des executions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_quality_gates (
    id              BIGSERIAL PRIMARY KEY,
    project_id      UUID NOT NULL,
    attempt_number  INTEGER NOT NULL DEFAULT 1,
    gate_name       TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PASS','FAIL','SKIP','ERROR')),
    score           NUMERIC(5,3),
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    details_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dqg_project_attempt
    ON delivery_quality_gates(project_id, attempt_number, gate_name);

CREATE INDEX IF NOT EXISTS idx_dqg_status_recent
    ON delivery_quality_gates(status, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_dqg_gate_name_recent
    ON delivery_quality_gates(gate_name, checked_at DESC);

-- ---------------------------------------------------------------------------
-- 2) quality_gate_failures : detail des echecs (pour feedback aux agents)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_gate_failures (
    id                BIGSERIAL PRIMARY KEY,
    project_id        UUID NOT NULL,
    gate_name         TEXT NOT NULL,
    attempt_number    INTEGER NOT NULL,
    error_msg         TEXT NOT NULL,
    fixed_in_attempt  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qgf_project_open
    ON quality_gate_failures(project_id, fixed_in_attempt) WHERE fixed_in_attempt IS NULL;

CREATE INDEX IF NOT EXISTS idx_qgf_gate_recent
    ON quality_gate_failures(gate_name, created_at DESC);

-- ---------------------------------------------------------------------------
-- 3) Seal V8.5 dans evidence_ledger
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

    seal_payload := '{"event":"v8_5_quality_gates_strict","version":"6.3.0","date":"2026-04-27","fix":"6 strict gates blocking delivery; pytest_agent fallback parser; templates include pytest-json-report"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_035_v8_5',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8.5 quality gates strict sealed (chain_hash=%)', new_chain_hash;
END
$$;
