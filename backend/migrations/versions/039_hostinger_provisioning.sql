-- 039 : V9 Phase 9G — Hostinger Provisioning
-- 2026-04-30
--
-- 5 tables :
--   hostinger_resources   : registre des ressources (domain, vps, ssl, backup)
--   hostinger_audit       : journal append-only des operations API
--   domain_searches       : historique des recherches (lecture libre)
--   ssl_certificates      : certificats Let's Encrypt
--   backups               : sauvegardes quotidiennes
--
-- Numero 039 : reserve dans le master plan V9 a Phase 9G.

-- ---------------------------------------------------------------------------
-- 1) hostinger_resources : etat de chaque ressource externe
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hostinger_resources (
    id              BIGSERIAL PRIMARY KEY,
    resource_id     UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    resource_type   TEXT NOT NULL CHECK (resource_type IN ('domain','vps','ssl','backup')),
    project_id      TEXT NOT NULL,
    hostinger_id    TEXT,                                  -- id chez Hostinger
    status          TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','provisioning','active',
                                          'failed','destroyed')),
    payment_id      TEXT,                                  -- ref vers billing (FK en 9P)
    metadata_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hostres_project_recent
    ON hostinger_resources(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hostres_type_status
    ON hostinger_resources(resource_type, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_hostres_hostinger_id
    ON hostinger_resources(hostinger_id)
    WHERE hostinger_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_hostres_active_recent
    ON hostinger_resources(updated_at DESC)
    WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 2) hostinger_audit : journal append-only des operations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hostinger_audit (
    id              BIGSERIAL PRIMARY KEY,
    audit_id        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    resource_id     UUID,                                  -- nullable (audit pre-creation)
    event           TEXT NOT NULL,                         -- e.g. 'purchase_requested'
    payload_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hostaudit_resource_recent
    ON hostinger_audit(resource_id, occurred_at DESC)
    WHERE resource_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_hostaudit_event_recent
    ON hostinger_audit(event, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- 3) domain_searches : historique des recherches (utile pour analytics)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS domain_searches (
    id            BIGSERIAL PRIMARY KEY,
    search_id     UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    query         TEXT NOT NULL,
    available     BOOLEAN NOT NULL,
    raw_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    searched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_domsearch_query_recent
    ON domain_searches(query, searched_at DESC);

-- ---------------------------------------------------------------------------
-- 4) ssl_certificates : Let's Encrypt
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ssl_certificates (
    id                       BIGSERIAL PRIMARY KEY,
    cert_id                  UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id               TEXT NOT NULL,
    domain                   TEXT NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','issued','renewing',
                                                   'expired','failed')),
    issued_at                TIMESTAMPTZ,
    expires_at               TIMESTAMPTZ,
    last_renewed_at          TIMESTAMPTZ,
    hostinger_metadata_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_ssl_project_recent
    ON ssl_certificates(project_id, issued_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_ssl_expires_soon
    ON ssl_certificates(expires_at)
    WHERE status = 'issued' AND expires_at IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5) backups : sauvegardes quotidiennes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backups (
    id                    BIGSERIAL PRIMARY KEY,
    backup_id             UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id            TEXT NOT NULL,
    vps_resource_id       UUID NOT NULL REFERENCES hostinger_resources(resource_id),
    status                TEXT NOT NULL DEFAULT 'scheduled'
                             CHECK (status IN ('scheduled','running','completed',
                                                'failed','restoring','restored')),
    size_bytes            BIGINT,
    hostinger_backup_id   TEXT,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at          TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backups_project_recent
    ON backups(project_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_backups_vps
    ON backups(vps_resource_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_backups_status_recent
    ON backups(status, started_at DESC);

-- ---------------------------------------------------------------------------
-- Vues pratiques
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_ssl_expires_30d AS
SELECT cert_id, project_id, domain, expires_at,
       (expires_at - NOW()) AS time_remaining
  FROM ssl_certificates
 WHERE status = 'issued'
   AND expires_at IS NOT NULL
   AND expires_at <= NOW() + INTERVAL '30 days'
 ORDER BY expires_at ASC;

CREATE OR REPLACE VIEW v_active_resources_per_project AS
SELECT project_id, resource_type, COUNT(*) AS count_active
  FROM hostinger_resources
 WHERE status = 'active'
 GROUP BY project_id, resource_type;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9G
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

    seal_payload := '{"event":"v9_phase9g_hostinger_provisioning","version":"9.0.0-phase9g","date":"2026-04-30","tables":["hostinger_resources","hostinger_audit","domain_searches","ssl_certificates","backups"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_039_v9_hostinger',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9G hostinger_provisioning sealed (chain_hash=%)', new_chain_hash;
END
$$;
