-- 049 : V9 Phase 9P — Consolidation FK + injection liens directs livrables
-- 2026-04-30
--
-- Ferme ADR-15 (FK retroactives project_id) et partiellement ADR-08
-- (handoff_pending.direct_link_id nullable ; magic_link_token reste pour
-- la fenetre de depreciation).
--
-- Strategie data-aware :
-- 1. Pour chaque table dependante avec project_id TEXT :
--    a. DELETE des lignes orphelines (project_id qui ne match aucune
--       row dans projects.project_id::text)
--    b. ALTER COLUMN project_id TYPE UUID USING project_id::uuid
--    c. ADD CONSTRAINT FK -> projects(project_id)
-- 2. handoff_pending : ADD direct_link_id UUID nullable FK direct_links

-- ---------------------------------------------------------------------------
-- 1. Cleanup orphans + ALTER COLUMN + ADD FK
-- ---------------------------------------------------------------------------

-- intelligence_qualifications (Phase 9C)
DELETE FROM intelligence_qualifications
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE intelligence_qualifications
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE intelligence_qualifications
    ADD CONSTRAINT fk_iq_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- intelligence_pricings (Phase 9C)
DELETE FROM intelligence_pricings
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE intelligence_pricings
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE intelligence_pricings
    ADD CONSTRAINT fk_ip_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- intelligence_assemblies (Phase 9C)
DELETE FROM intelligence_assemblies
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE intelligence_assemblies
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE intelligence_assemblies
    ADD CONSTRAINT fk_ia_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- project_progression (Phase 9C)
DELETE FROM project_progression
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE project_progression
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE project_progression
    ADD CONSTRAINT fk_pp_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- handoff_requests (Phase 9E)
DELETE FROM handoff_requests
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE handoff_requests
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE handoff_requests
    ADD CONSTRAINT fk_hr_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- ai_decisions_log (Phase 9D)
DELETE FROM ai_decisions_log
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE ai_decisions_log
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE ai_decisions_log
    ADD CONSTRAINT fk_aidl_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- hostinger_resources (Phase 9G)
DELETE FROM hostinger_resources
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE hostinger_resources
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE hostinger_resources
    ADD CONSTRAINT fk_hres_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- payments (Phase 9H)
DELETE FROM payments
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE payments
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE payments
    ADD CONSTRAINT fk_payments_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- backups (Phase 9G — project_id est TEXT)
DELETE FROM backups
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE backups
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE backups
    ADD CONSTRAINT fk_backups_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- ssl_certificates (Phase 9G)
DELETE FROM ssl_certificates
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE ssl_certificates
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE ssl_certificates
    ADD CONSTRAINT fk_ssl_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- invoices (Phase 9H)
DELETE FROM invoices
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE invoices
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE invoices
    ADD CONSTRAINT fk_invoices_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);


-- ---------------------------------------------------------------------------
-- 2. handoff_pending : ajout direct_link_id nullable FK
-- ---------------------------------------------------------------------------
-- Migration partielle : la colonne magic_link_token reste (deprecation
-- window). Une migration future supprimera magic_link_token + rendra
-- direct_link_id NOT NULL.
ALTER TABLE handoff_pending
    ADD COLUMN IF NOT EXISTS direct_link_id UUID
        REFERENCES direct_links(link_id);

CREATE INDEX IF NOT EXISTS idx_handoff_pending_direct_link
    ON handoff_pending(direct_link_id)
    WHERE direct_link_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 3. Vue dashboard : projets avec leur etat consolide cross-tables
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_project_consolidated_status AS
SELECT
    p.project_id,
    p.owner_email,
    p.title,
    p.status                                                AS project_status,
    p.pack_id_hint,
    (SELECT COUNT(*) FROM intelligence_qualifications q
        WHERE q.project_id = p.project_id)                  AS qualifications_count,
    (SELECT MAX(created_at) FROM intelligence_pricings ip
        WHERE ip.project_id = p.project_id)                 AS last_pricing_at,
    (SELECT bool_or(paywall_triggered_at IS NOT NULL)
       FROM project_progression pp
        WHERE pp.project_id = p.project_id)                 AS paywall_triggered,
    (SELECT COUNT(*) FROM handoff_requests h
        WHERE h.project_id = p.project_id
          AND h.state IN ('requested','notified','acknowledged','escalated'))
                                                            AS open_handoffs,
    (SELECT SUM(amount_cents) FROM payments pay
        WHERE pay.project_id = p.project_id
          AND pay.status = 'succeeded')                     AS paid_amount_cents,
    (SELECT COUNT(*) FROM hostinger_resources hr
        WHERE hr.project_id = p.project_id
          AND hr.status = 'active')                         AS active_infra_resources,
    (SELECT SUM(cost_usd) FROM ai_decisions_log ad
        WHERE ad.project_id = p.project_id)                 AS total_ai_cost_usd
FROM projects p;


-- ---------------------------------------------------------------------------
-- 4. Seal V9 Phase 9P
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

    seal_payload := '{"event":"v9_phase9p_consolidation","version":"9.0.0-phase9p","date":"2026-04-30","fk_added":["intelligence_qualifications","intelligence_pricings","intelligence_assemblies","project_progression","handoff_requests","ai_decisions_log","hostinger_resources","payments","backups","ssl_certificates","invoices"],"partial":["handoff_pending.direct_link_id"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_049_v9_consolidation',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9P consolidation sealed (chain_hash=%)', new_chain_hash;
END
$$;
