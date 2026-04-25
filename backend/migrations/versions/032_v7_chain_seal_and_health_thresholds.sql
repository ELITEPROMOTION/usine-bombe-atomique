-- 032 : V7 Production-Ready Local — chain seal + health thresholds env-overridable
-- 2026-04-25
-- Phase 7B repair :
--   * Anomalie A001 : truth_chain_integrity reportait 144 "broken" events.
--     Investigation : 0 chain_hash mismatch (cryptographie OK), 144 segment-boundaries
--     (resets legitimes hors-band — tests/chaos/redemarrages). verify_chain() est
--     desormais aligne sur le critere cryptographique (chain_hash recomputed) et
--     reporte les segments comme info, pas comme corruption.
--   * Anomalie A002/A003 : seuils health (PG=50ms, Redis=20ms) inadaptes a Docker
--     Desktop sur Windows. Desormais lus depuis ENV (PG_PING_HEALTHY_MS=200,
--     REDIS_PING_HEALTHY_MS=100). Code change : backend/app/health/checks.py.
--
-- Cette migration scelle la chaine au point V7 via un event "repair" qui
-- documente l'investigation et empeche regression silencieuse.

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

    seal_payload := '{"event":"v7_chain_seal","version":"5.5.7","date":"2026-04-25","reason":"Phase 7B Anomalie A001 closure","investigation":{"chain_hash_mismatches":0,"segment_boundaries":144,"events_checked":3866},"resolution":"verify_chain aligned on cryptographic integrity (chain_hash recomputation), segment boundaries reported as info"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_032_v7',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V7 chain seal event inserted (chain_hash=%)', new_chain_hash;
END
$$;

-- Index pour stats segments (facultatif mais utile)
CREATE INDEX IF NOT EXISTS idx_evidence_kind_created
  ON evidence_ledger (kind, created_at DESC);
