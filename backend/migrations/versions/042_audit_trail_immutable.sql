-- 042 : V9 Phase 9J — Audit trail immutability triggers (append-only)
-- 2026-04-30
--
-- Bloque UPDATE/DELETE sur les tables append-only :
--   - admin_actions       (Phase 9N)
--   - ai_decisions_log    (Phase 9D)
--   - hostinger_audit     (Phase 9G)
--   - direct_links_audit  (Phase 9A)
--   - webhook_events      (Phase 9H — payload_json/signature_verified
--                          immuables ; processed_at/payment_id peuvent
--                          etre completes 1 fois)
--
-- Pour `mandates` (Phase 9-BOOT) : trigger column-level — chain_hash,
-- prev_hash, payload_hash, signed_at sont immuables ; revoked_at,
-- revocation_reason et audit_log peuvent etre mis a jour (revocation
-- legitime). signature integrite preservee.

-- ---------------------------------------------------------------------------
-- 1) Helper : RAISE EXCEPTION trigger function pour append-only strict
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_block_mutations() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'append-only: % on % bloque par audit trail',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- 2) Triggers stricts sur tables 100% append-only
-- ---------------------------------------------------------------------------
-- admin_actions : aucune mutation
DROP TRIGGER IF EXISTS trg_admin_actions_no_update ON admin_actions;
CREATE TRIGGER trg_admin_actions_no_update
    BEFORE UPDATE OR DELETE ON admin_actions
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();

-- ai_decisions_log : aucune mutation
DROP TRIGGER IF EXISTS trg_ai_decisions_log_no_update ON ai_decisions_log;
CREATE TRIGGER trg_ai_decisions_log_no_update
    BEFORE UPDATE OR DELETE ON ai_decisions_log
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();

-- hostinger_audit : aucune mutation
DROP TRIGGER IF EXISTS trg_hostinger_audit_no_update ON hostinger_audit;
CREATE TRIGGER trg_hostinger_audit_no_update
    BEFORE UPDATE OR DELETE ON hostinger_audit
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();

-- direct_links_audit : aucune mutation
DROP TRIGGER IF EXISTS trg_direct_links_audit_no_update ON direct_links_audit;
CREATE TRIGGER trg_direct_links_audit_no_update
    BEFORE UPDATE OR DELETE ON direct_links_audit
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();


-- ---------------------------------------------------------------------------
-- 3) webhook_events : payload_json/signature_verified/event_type immuables ;
--    processed_at + payment_id peuvent etre completes 1 fois
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_webhook_events_protect() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'webhook_events: DELETE bloque (immuable)'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- UPDATE : on protege les champs immuables
    IF NEW.idempotency_key  IS DISTINCT FROM OLD.idempotency_key
       OR NEW.payload_json    IS DISTINCT FROM OLD.payload_json
       OR NEW.signature_verified IS DISTINCT FROM OLD.signature_verified
       OR NEW.event_type      IS DISTINCT FROM OLD.event_type
       OR NEW.source          IS DISTINCT FROM OLD.source
       OR NEW.received_at     IS DISTINCT FROM OLD.received_at
    THEN
        RAISE EXCEPTION 'webhook_events: champs immuables modifies'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- processed_at peut etre rempli mais pas reverte
    IF OLD.processed_at IS NOT NULL
       AND NEW.processed_at IS DISTINCT FROM OLD.processed_at
    THEN
        RAISE EXCEPTION 'webhook_events: processed_at deja fixe, modification interdite'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_webhook_events_protect ON webhook_events;
CREATE TRIGGER trg_webhook_events_protect
    BEFORE UPDATE OR DELETE ON webhook_events
    FOR EACH ROW EXECUTE FUNCTION fn_webhook_events_protect();


-- ---------------------------------------------------------------------------
-- 4) mandates : chain_hash/prev_hash/payload_hash/signed_at immuables ;
--    revoked_at, revocation_reason, audit_log peuvent etre mis a jour
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_mandates_protect() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'mandates: DELETE bloque (chaine immuable)'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- UPDATE : champs critiques de la chaine
    IF NEW.chain_hash       IS DISTINCT FROM OLD.chain_hash
       OR NEW.prev_hash       IS DISTINCT FROM OLD.prev_hash
       OR NEW.payload_hash    IS DISTINCT FROM OLD.payload_hash
       OR NEW.signed_at       IS DISTINCT FROM OLD.signed_at
       OR NEW.mandate_id      IS DISTINCT FROM OLD.mandate_id
       OR NEW.mandate_type    IS DISTINCT FROM OLD.mandate_type
       OR NEW.principal_id    IS DISTINCT FROM OLD.principal_id
       OR NEW.agent_identity  IS DISTINCT FROM OLD.agent_identity
       OR NEW.scope_json      IS DISTINCT FROM OLD.scope_json
    THEN
        RAISE EXCEPTION 'mandates: chaine immuable, champ critique modifie'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- revoked_at une fois fixe ne peut pas etre revert
    IF OLD.revoked_at IS NOT NULL
       AND (NEW.revoked_at IS NULL
            OR NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
    THEN
        RAISE EXCEPTION 'mandates: revocation immuable une fois enregistree'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_mandates_protect ON mandates;
CREATE TRIGGER trg_mandates_protect
    BEFORE UPDATE OR DELETE ON mandates
    FOR EACH ROW EXECUTE FUNCTION fn_mandates_protect();


-- ---------------------------------------------------------------------------
-- 5) Verification helper : recense les triggers actifs
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_audit_immutability_status AS
SELECT
    event_object_table AS table_name,
    trigger_name,
    array_agg(event_manipulation ORDER BY event_manipulation) AS events,
    action_timing
FROM information_schema.triggers
WHERE trigger_name LIKE 'trg_%_protect'
   OR trigger_name LIKE 'trg_%_no_update'
GROUP BY event_object_table, trigger_name, action_timing;


-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9J
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

    seal_payload := '{"event":"v9_phase9j_audit_immutability","version":"9.0.0-phase9j","date":"2026-04-30","triggers":["admin_actions","ai_decisions_log","hostinger_audit","direct_links_audit","webhook_events","mandates"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_042_v9_audit_immutability',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9J audit immutability sealed (chain_hash=%)', new_chain_hash;
END
$$;
