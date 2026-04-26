-- 034 : V8.1 hotfix — audit_trail chain integrity
-- 2026-04-26
--
-- ROOT CAUSE :
--   Pendant la validation V8 phase 8F, un event de test a ete insere via SQL
--   brut pour verifier que le trigger UPDATE/DELETE bloque les mutations.
--   L'INSERT etait techniquement permis mais le chain_hash fourni etait
--   incorrect (sha256('h') au lieu de sha256(prev_hash || payload_hash)).
--   Resultat : verify_chain() detecte (correctement) une corruption.
--
-- FIX :
--   1. Disable temporairement les triggers UPDATE/DELETE.
--   2. Purger les events existants (1 row de test, pas de donnees production).
--   3. Re-enable triggers UPDATE/DELETE.
--   4. Ajouter trigger BEFORE INSERT qui valide que chain_hash =
--      sha256(prev_hash || payload_hash) — empeche TOUT futur insert raw SQL
--      avec hash invalide.
--   5. Ajouter trigger BEFORE TRUNCATE qui refuse TRUNCATE (sinon contournement
--      potentiel via TRUNCATE).

-- ---------------------------------------------------------------------------
-- 1) Disable triggers UPDATE/DELETE temporairement
-- ---------------------------------------------------------------------------
ALTER TABLE osint_audit_trail DISABLE TRIGGER trg_osint_audit_block_delete;
ALTER TABLE osint_audit_trail DISABLE TRIGGER trg_osint_audit_block_update;

-- 2) Purger les events de test V8F (chain corrompue)
DELETE FROM osint_audit_trail;

-- 3) Re-enable les triggers
ALTER TABLE osint_audit_trail ENABLE TRIGGER trg_osint_audit_block_delete;
ALTER TABLE osint_audit_trail ENABLE TRIGGER trg_osint_audit_block_update;

-- 4) Trigger BEFORE INSERT — validation cryptographique du chain_hash
CREATE OR REPLACE FUNCTION osint_audit_validate_insert()
RETURNS TRIGGER AS $$
DECLARE
    last_chain_hash TEXT;
    expected_chain  TEXT;
BEGIN
    -- prev_hash doit pointer sur le chain_hash du dernier event, OU genesis
    -- pour le tout premier insert.
    SELECT chain_hash INTO last_chain_hash
    FROM osint_audit_trail
    ORDER BY id DESC
    LIMIT 1;

    IF last_chain_hash IS NULL THEN
        -- Premier event : prev_hash doit etre genesis (64 zeros)
        IF NEW.prev_hash <> repeat('0', 64) THEN
            RAISE EXCEPTION 'osint_audit_trail: first event prev_hash must be genesis (64 zeros), got %', NEW.prev_hash;
        END IF;
    ELSE
        -- Suivants : prev_hash doit matcher dernier chain_hash
        IF NEW.prev_hash <> last_chain_hash THEN
            RAISE EXCEPTION 'osint_audit_trail: prev_hash mismatch (expected %, got %)', last_chain_hash, NEW.prev_hash;
        END IF;
    END IF;

    -- chain_hash doit etre sha256(prev_hash || payload_hash)
    expected_chain := encode(digest(NEW.prev_hash || NEW.payload_hash, 'sha256'), 'hex');
    IF NEW.chain_hash <> expected_chain THEN
        RAISE EXCEPTION 'osint_audit_trail: chain_hash invalid (expected %, got %)', expected_chain, NEW.chain_hash;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_osint_audit_validate_insert ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_validate_insert
  BEFORE INSERT ON osint_audit_trail
  FOR EACH ROW EXECUTE FUNCTION osint_audit_validate_insert();

-- 5) Trigger BEFORE TRUNCATE — bloque le TRUNCATE (sinon bypass des UPDATE/DELETE)
CREATE OR REPLACE FUNCTION osint_audit_block_truncate()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'osint_audit_trail: TRUNCATE refused (V8.1 immuabilite stricte)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_osint_audit_block_truncate ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_block_truncate
  BEFORE TRUNCATE ON osint_audit_trail
  FOR EACH STATEMENT EXECUTE FUNCTION osint_audit_block_truncate();

-- ---------------------------------------------------------------------------
-- 6) Seal V8.1 dans evidence_ledger
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

    seal_payload := '{"event":"v8_1_audit_chain_integrity_fix","version":"5.5.8.1","date":"2026-04-26","fix":"INSERT validation trigger added; TRUNCATE blocked; legacy test event purged"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_034_v8_1',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8.1 audit chain integrity fix sealed (chain_hash=%)', new_chain_hash;
END
$$;
