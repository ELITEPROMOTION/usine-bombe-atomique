-- 045 : V9 Phase 9B — Setup Wizard Ahmed (admin bootstrap, 4 etapes)
-- 2026-04-30
--
-- Tables :
--   setup_wizard_state  : 1 ligne par session de wizard (historique)
--   platform_config     : singleton (id=1) — config commitee active
--
-- Numero 045 et non 038 : 037 deja pose (Phase 9A direct_links), 038-042
-- reserves au master plan (billing 9H, hostinger 9G, ai 9D, pricing 9C,
-- audit 9J), 043-044 deja poses (Phase 9-BOOT). 045 = prochain libre.
-- ADR-10 documente ce choix.

-- ---------------------------------------------------------------------------
-- 1) setup_wizard_state : sessions de wizard (multi-tentative tolere)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS setup_wizard_state (
    id                    BIGSERIAL PRIMARY KEY,
    wizard_id             UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    current_step          TEXT NOT NULL CHECK (current_step IN
                              ('brand_identity','pricing_baseline',
                               'service_catalog','operations_defaults')),
    completed_steps       TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    partial_config_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                TEXT NOT NULL DEFAULT 'in_progress'
                              CHECK (status IN
                                  ('in_progress','committed','abandoned')),
    started_by            TEXT NOT NULL DEFAULT 'ahmed',
    started_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    committed_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_setup_wizard_state_status
    ON setup_wizard_state(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_setup_wizard_state_in_progress
    ON setup_wizard_state(updated_at DESC)
    WHERE status = 'in_progress';

-- ---------------------------------------------------------------------------
-- 2) platform_config : singleton (1 seule ligne, id=1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_config (
    id                BIGINT PRIMARY KEY CHECK (id = 1),
    version           INTEGER NOT NULL DEFAULT 1,
    identity_json     JSONB NOT NULL,
    pricing_json      JSONB NOT NULL,
    services_json     JSONB NOT NULL,
    operations_json   JSONB NOT NULL,
    committed_by      TEXT NOT NULL,
    committed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vue d'historique : on garde aussi `setup_wizard_state` qui contient
-- toutes les tentatives anterieures (incluant abandonees).

-- ---------------------------------------------------------------------------
-- 3) Seal V9 Phase 9B dans evidence_ledger
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

    seal_payload := '{"event":"v9_phase9b_setup_wizard","version":"9.0.0-phase9b","date":"2026-04-30","tables":["setup_wizard_state","platform_config"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_045_v9_setup_wizard',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9B setup_wizard sealed (chain_hash=%)', new_chain_hash;
END
$$;
