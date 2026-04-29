-- 037 : V9 Phase 9A — direct-link catalog (liens d'action a usage controle)
-- 2026-04-29
--
-- Tables :
--   direct_links        : liens emis (token_hash uniquement, jamais le brut)
--   direct_links_audit  : journal append-only (issued, viewed, consumed, ...)
--
-- Le token brut quitte le serveur dans l'URL et n'est jamais re-stocke.
-- Si la base fuit, les hashs ne permettent pas de retrouver les tokens.
--
-- Numerotation 037 : reservee pour Phase 9A dans le master plan V9.

-- ---------------------------------------------------------------------------
-- 1) direct_links : registre des liens actifs / passes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS direct_links (
    id                 BIGSERIAL PRIMARY KEY,
    link_id            UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    token_hash         TEXT NOT NULL UNIQUE,             -- sha256 du token urlsafe
    action_type        TEXT NOT NULL,                     -- valide via catalog.json (cote app)
    target_id          TEXT NOT NULL,                     -- id metier (handoff, project, deliverable)
    principal_id       TEXT,                              -- utilisateur autorise (optionnel)
    metadata_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    single_use         BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at        TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    revocation_reason  TEXT,
    expires_at         TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_direct_links_action_target
    ON direct_links(action_type, target_id);

CREATE INDEX IF NOT EXISTS idx_direct_links_active_expiry
    ON direct_links(expires_at)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_direct_links_principal_recent
    ON direct_links(principal_id, created_at DESC)
    WHERE principal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_direct_links_action_type_recent
    ON direct_links(action_type, created_at DESC);

-- ---------------------------------------------------------------------------
-- 2) direct_links_audit : journal append-only (1 ligne par evenement)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS direct_links_audit (
    id            BIGSERIAL PRIMARY KEY,
    link_id       UUID,                                  -- nullable pour invalid_token
    event         TEXT NOT NULL CHECK (event IN
                      ('issued','viewed','consumed','expired',
                       'revoked','invalid_token','unknown')),
    user_agent    TEXT,
    ip_hash       TEXT,                                  -- sha256 de l'IP (RGPD)
    detail_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dla_link_recent
    ON direct_links_audit(link_id, occurred_at DESC)
    WHERE link_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dla_event_recent
    ON direct_links_audit(event, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_dla_invalid_recent
    ON direct_links_audit(occurred_at DESC)
    WHERE event = 'invalid_token';

-- ---------------------------------------------------------------------------
-- 3) Seal V9 Phase 9A dans evidence_ledger
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

    seal_payload := '{"event":"v9_phase9a_direct_links","version":"9.0.0-phase9a","date":"2026-04-29","tables":["direct_links","direct_links_audit"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_037_v9_direct_links',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9A direct_links sealed (chain_hash=%)', new_chain_hash;
END
$$;
