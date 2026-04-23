-- ============================================================
-- 022_ctc_truth_graph.sql - V5.3 BLOC 4
-- truth_assertion_links : graphe assertions ↔ artefacts ↔ decisions
-- WORM logique : append-only via triggers
-- ============================================================

CREATE TABLE IF NOT EXISTS truth_assertion_links (
    link_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assertion_id UUID REFERENCES truth_assertions(assertion_id)
        ON DELETE CASCADE,
    linked_entity_type VARCHAR(30) NOT NULL
        CHECK (linked_entity_type IN
               ('task','artifact','validation','decision',
                'version','incident','hypothesis','risk')),
    linked_entity_id UUID NOT NULL,
    link_type VARCHAR(20) NOT NULL
        CHECK (link_type IN ('supports','contradicts','depends_on','invalidates')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tal_assertion
    ON truth_assertion_links(assertion_id);
CREATE INDEX IF NOT EXISTS idx_tal_entity
    ON truth_assertion_links(linked_entity_type, linked_entity_id);

-- Trigger append-only (WORM)
CREATE OR REPLACE FUNCTION truth_graph_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'truth_assertion_links is append-only (WORM)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tal_block_update ON truth_assertion_links;
CREATE TRIGGER trg_tal_block_update
    BEFORE UPDATE ON truth_assertion_links
    FOR EACH ROW EXECUTE FUNCTION truth_graph_block_mutations();

DROP TRIGGER IF EXISTS trg_tal_block_delete ON truth_assertion_links;
CREATE TRIGGER trg_tal_block_delete
    BEFORE DELETE ON truth_assertion_links
    FOR EACH ROW EXECUTE FUNCTION truth_graph_block_mutations();
