-- ============================================================
-- 010_tool_registry_pgvector.sql - V4.3 registry SaaS + pgvector
-- ============================================================

-- 1. pgvector (image pgvector/pgvector:pg16 requise)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Registre des outils externes connectes
CREATE TABLE IF NOT EXISTS tool_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tool_id VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    tool_type VARCHAR(30) NOT NULL
        CHECK (tool_type IN ('saas','self_hosted','mcp','api','cli')),
    url VARCHAR(500),
    api_key_vault_path VARCHAR(200),
    status VARCHAR(30) NOT NULL DEFAULT 'pending_setup'
        CHECK (status IN ('connected','disconnected','pending_setup',
                          'needs_user_input','broken','deprecated')),
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_health_at TIMESTAMPTZ,
    last_health_status VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    connected_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tool_status ON tool_registry(status);

-- 3. Demandes d'input utilisateur (lies aux outils pendant provisioning)
CREATE TABLE IF NOT EXISTS pending_user_inputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    tool_id VARCHAR(60),
    request_kind VARCHAR(40) NOT NULL
        CHECK (request_kind IN ('email','password','otp','captcha','payment',
                                'api_key','custom','two_factor')),
    fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    context TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'awaiting'
        CHECK (status IN ('awaiting','submitted','expired','cancelled')),
    submission_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '1 hour'
);

CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_user_inputs(status);
CREATE INDEX IF NOT EXISTS idx_pending_task ON pending_user_inputs(task_id);

-- 4. Enrichir semantic_cache avec une vraie colonne vector (V4.2 JSONB fallback reste)
ALTER TABLE semantic_cache
    ADD COLUMN IF NOT EXISTS embedding vector(128);
CREATE INDEX IF NOT EXISTS idx_semcache_embedding
    ON semantic_cache USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);
