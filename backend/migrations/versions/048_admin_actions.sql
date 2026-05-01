-- 048 : V9 Phase 9N — Admin actions audit (overrides, FinOps changes, etc.)
-- 2026-04-30
--
-- 1 ligne par action de l'admin (Ahmed) qui mute un etat. Trace immuable
-- (append-only — un trigger sera ajoute en Phase 9J pour bloquer
-- UPDATE/DELETE).

CREATE TABLE IF NOT EXISTS admin_actions (
    id              BIGSERIAL PRIMARY KEY,
    action_id       UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    admin_id        TEXT NOT NULL,
    action_type     TEXT NOT NULL,                    -- e.g. 'cancel_handoff', 'override_router_policy'
    target_type     TEXT NOT NULL,                    -- e.g. 'handoff', 'project', 'direct_link'
    target_id       TEXT,                             -- UUID ou identifiant metier
    payload_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    token_hint      TEXT,                             -- 4 derniers chars du token, jamais le brut
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_actions_admin_recent
    ON admin_actions(admin_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_actions_type_recent
    ON admin_actions(action_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_actions_target
    ON admin_actions(target_type, target_id, created_at DESC)
    WHERE target_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Vue : derniere action par admin et par target
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_admin_actions_recent AS
SELECT action_id, admin_id, action_type, target_type, target_id,
       payload_json, created_at
  FROM admin_actions
 ORDER BY created_at DESC
 LIMIT 500;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9N
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

    seal_payload := '{"event":"v9_phase9n_admin_dashboard","version":"9.0.0-phase9n","date":"2026-04-30","tables":["admin_actions"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_048_v9_admin_dashboard',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9N admin_dashboard sealed (chain_hash=%)', new_chain_hash;
END
$$;
