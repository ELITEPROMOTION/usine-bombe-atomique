-- 044 : V9 Phase 9-BOOT — mandats numeriques eIDAS Article 26
-- 2026-04-29
--
-- Chaque mandat est un maillon d'une chaine SHA-256 :
--   chain_hash = sha256(prev_hash || payload_hash)
-- La revocation est append-only via le champ audit_log (jamais de DELETE).

CREATE TABLE IF NOT EXISTS mandates (
    id                 BIGSERIAL PRIMARY KEY,
    mandate_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    mandate_type       TEXT NOT NULL CHECK (mandate_type IN
                          ('account_creation','sub_authorization',
                           'data_processing','payment_authorization')),
    principal_id       TEXT NOT NULL,
    agent_identity     TEXT NOT NULL,
    scope_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash       TEXT NOT NULL,
    prev_hash          TEXT NOT NULL,
    chain_hash         TEXT NOT NULL UNIQUE,
    signed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    revocation_reason  TEXT,
    audit_log          JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_mandates_chain_hash    ON mandates(chain_hash);
CREATE INDEX IF NOT EXISTS idx_mandates_signed_at     ON mandates(signed_at DESC);
CREATE INDEX IF NOT EXISTS idx_mandates_principal     ON mandates(principal_id, signed_at DESC);
CREATE INDEX IF NOT EXISTS idx_mandates_active
    ON mandates(principal_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_mandates_type_recent
    ON mandates(mandate_type, signed_at DESC);

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9-BOOT (mandates) dans evidence_ledger
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

    seal_payload := '{"event":"v9_phase9boot_mandates_eidas","version":"9.0.0-bootstrap","date":"2026-04-29","standard":"eIDAS Article 26","table":"mandates"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_044_v9_mandates',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9-BOOT mandates sealed (chain_hash=%)', new_chain_hash;
END
$$;
