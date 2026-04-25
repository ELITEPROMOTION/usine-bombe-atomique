-- 033 : V8 OSINT Legal Framework
-- Tables : osint_consents, osint_audit_trail, osint_scope_whitelist
-- Triggers append-only sur audit_trail (pas d'UPDATE/DELETE).
-- 2026-04-26

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 1) osint_consents : contrats consentement explicite (pentest etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS osint_consents (
    consent_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    target               VARCHAR(255) NOT NULL,
    actions              JSONB        NOT NULL,
    contractor           VARCHAR(255) NOT NULL,
    contract_pdf_sha256  CHAR(64)     NOT NULL,
    signed_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at           TIMESTAMPTZ  NOT NULL,
    revoked_at           TIMESTAMPTZ,
    revoked_reason       TEXT,
    tenant_id            UUID,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_osint_consents_target_active
  ON osint_consents (target)
  WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_osint_consents_expires
  ON osint_consents (expires_at);

-- ---------------------------------------------------------------------------
-- 2) osint_audit_trail : append-only, hash-chained
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS osint_audit_trail (
    id            BIGSERIAL    PRIMARY KEY,
    event_id      UUID         NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    actor         VARCHAR(120) NOT NULL,
    module        VARCHAR(120) NOT NULL,
    action        VARCHAR(120) NOT NULL,
    target        VARCHAR(255) NOT NULL,
    risk_level    VARCHAR(20)  NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
    decision      VARCHAR(20)  NOT NULL CHECK (decision IN ('allowed','denied','error')),
    consent_id    UUID         REFERENCES osint_consents(consent_id) ON DELETE SET NULL,
    payload_hash  CHAR(64)     NOT NULL,
    prev_hash     CHAR(64)     NOT NULL,
    chain_hash    CHAR(64)     NOT NULL UNIQUE,
    payload_json  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    tenant_id     UUID
);

CREATE INDEX IF NOT EXISTS idx_osint_audit_target ON osint_audit_trail (target);
CREATE INDEX IF NOT EXISTS idx_osint_audit_module_decision ON osint_audit_trail (module, decision);
CREATE INDEX IF NOT EXISTS idx_osint_audit_created_desc ON osint_audit_trail (created_at DESC);

-- Triggers : append-only stricte (refus UPDATE et DELETE)
CREATE OR REPLACE FUNCTION osint_audit_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'osint_audit_trail is append-only (V8 immuabilite RGPD-DZ)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_osint_audit_block_update ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_block_update
  BEFORE UPDATE ON osint_audit_trail
  FOR EACH ROW EXECUTE FUNCTION osint_audit_block_mutations();

DROP TRIGGER IF EXISTS trg_osint_audit_block_delete ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_block_delete
  BEFORE DELETE ON osint_audit_trail
  FOR EACH ROW EXECUTE FUNCTION osint_audit_block_mutations();

-- ---------------------------------------------------------------------------
-- 3) osint_scope_whitelist : entrees stricte d'extension whitelist
--    (rarement utilise — Dendani hardcoded dans le code Python pour empecher
--     un override SQL accidentel ; cette table garde un audit trail)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS osint_scope_whitelist (
    id            BIGSERIAL   PRIMARY KEY,
    scope_pattern VARCHAR(255) NOT NULL,
    reason        TEXT         NOT NULL,
    added_by      VARCHAR(120) NOT NULL,
    added_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    revoked_at    TIMESTAMPTZ,
    revoked_reason TEXT,
    tenant_id     UUID
);

CREATE INDEX IF NOT EXISTS idx_osint_whitelist_active
  ON osint_scope_whitelist (scope_pattern)
  WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------------------
-- 4) Seal V8 : event marker dans evidence_ledger
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

    seal_payload := '{"event":"v8_osint_legal_framework_init","version":"5.5.8","date":"2026-04-26","tables_created":["osint_consents","osint_audit_trail","osint_scope_whitelist"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_033_v8',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8 OSINT seal event inserted (chain_hash=%)', new_chain_hash;
END
$$;
