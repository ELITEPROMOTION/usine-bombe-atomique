-- ============================================================
-- 031_knowledge_graph.sql - V5.8 Knowledge Graph (entites + relations)
-- ============================================================

CREATE TABLE IF NOT EXISTS kg_nodes (
    id VARCHAR(120) PRIMARY KEY,
    node_type VARCHAR(40) NOT NULL
        CHECK (node_type IN ('entity','rule','decision','evidence',
                              'domain','agent','feature_flag','task')),
    label TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_type
    ON kg_nodes(node_type);

CREATE TABLE IF NOT EXISTS kg_edges (
    id BIGSERIAL PRIMARY KEY,
    source_id VARCHAR(120) NOT NULL REFERENCES kg_nodes(id)
        ON DELETE CASCADE,
    target_id VARCHAR(120) NOT NULL REFERENCES kg_nodes(id)
        ON DELETE CASCADE,
    relation_type VARCHAR(40) NOT NULL
        CHECK (relation_type IN ('depends_on','contradicts','supports',
                                   'learned_from','derived_from','applies_to',
                                   'triggers','impacts')),
    weight DECIMAL(5,3) NOT NULL DEFAULT 1.0,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, target_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_kg_edges_source
    ON kg_edges(source_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_kg_edges_target
    ON kg_edges(target_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_kg_edges_contradicts
    ON kg_edges(relation_type)
    WHERE relation_type = 'contradicts';
