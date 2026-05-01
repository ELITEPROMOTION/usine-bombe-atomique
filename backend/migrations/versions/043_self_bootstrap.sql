-- 043 : V9 Phase 9-BOOT — self-bootstrap state
-- 2026-04-29
--
-- Tables :
--   self_bootstrap_state  : phase d'amorcage (init, validators, plans, complete)
--   service_activations   : 1 ligne par service tiers (Cloudflare, Stripe, ...)
--   handoff_pending       : handoffs KYC / carte / etape manuelle
--
-- Numerotation 043 : reservee dans le master plan V9 (037-042 = autres phases).

-- ---------------------------------------------------------------------------
-- 1) self_bootstrap_state : phases successives de l'amorcage
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS self_bootstrap_state (
    id              BIGSERIAL PRIMARY KEY,
    bootstrap_id    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    phase           TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pending','in_progress','blocked','done','failed')),
    detail_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sbs_phase_status
    ON self_bootstrap_state(phase, status, started_at DESC);

-- ---------------------------------------------------------------------------
-- 2) service_activations : etat operationnel de chaque integration tierce
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_activations (
    id                BIGSERIAL PRIMARY KEY,
    service_name      TEXT NOT NULL UNIQUE,
    tier              INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 3),
    activation_status TEXT NOT NULL CHECK (activation_status IN
                          ('queued','planning','awaiting_handoff','active','failed')),
    plan_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    vault_path        TEXT,
    last_attempt_at   TIMESTAMPTZ,
    activated_at      TIMESTAMPTZ,
    failure_reason    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_activations_status
    ON service_activations(activation_status, tier);

CREATE INDEX IF NOT EXISTS idx_service_activations_active_recent
    ON service_activations(activated_at DESC) WHERE activation_status = 'active';

-- ---------------------------------------------------------------------------
-- 3) handoff_pending : magic-link en attente de validation humaine
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS handoff_pending (
    id                  BIGSERIAL PRIMARY KEY,
    handoff_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    handoff_type        TEXT NOT NULL CHECK (handoff_type IN ('kyc','card','manual_step')),
    target_email        TEXT NOT NULL,
    magic_link_token    TEXT NOT NULL UNIQUE,
    instructions_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    locale              TEXT NOT NULL DEFAULT 'en',
    status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
                            ('pending','reminded_1h','reminded_12h','reminded_24h',
                             'escalated','resolved','expired')),
    expires_at          TIMESTAMPTZ NOT NULL,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_handoff_pending_status
    ON handoff_pending(status, expires_at);

CREATE INDEX IF NOT EXISTS idx_handoff_pending_open
    ON handoff_pending(created_at DESC)
    WHERE status NOT IN ('resolved','expired');

-- ---------------------------------------------------------------------------
-- 4) Seal V9 Phase 9-BOOT dans evidence_ledger
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

    seal_payload := '{"event":"v9_phase9boot_self_bootstrap","version":"9.0.0-bootstrap","date":"2026-04-29","tables":["self_bootstrap_state","service_activations","handoff_pending"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_043_v9_bootstrap',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9-BOOT self_bootstrap sealed (chain_hash=%)', new_chain_hash;
END
$$;
