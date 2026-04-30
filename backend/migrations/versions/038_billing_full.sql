-- 038 : V9 Phase 9H — Billing + Stripe Checkout (1-shot)
-- 2026-04-30
--
-- 4 tables :
--   payments          : table CANONIQUE des paiements (UUID PK, FK depuis 9G/9F en 9P)
--   invoices          : factures emises (multi-pays, multi-langues)
--   refunds           : refunds partiels/complets
--   webhook_events    : journal Stripe avec idempotency_key UNIQUE

-- ---------------------------------------------------------------------------
-- 1) payments (canonique)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id                          BIGSERIAL PRIMARY KEY,
    payment_id                  UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id                  TEXT NOT NULL,
    stripe_session_id           TEXT,
    stripe_payment_intent_id    TEXT,
    amount_cents                INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency                    CHAR(3) NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','succeeded','failed',
                                                      'refunded','partially_refunded',
                                                      'cancelled')),
    owner_email                 TEXT NOT NULL,
    country                     CHAR(2) NOT NULL,
    locale                      TEXT NOT NULL DEFAULT 'en',
    metadata_json               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at                     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payments_project_recent
    ON payments(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payments_status_recent
    ON payments(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_payments_stripe_session
    ON payments(stripe_session_id)
    WHERE stripe_session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payments_stripe_pi
    ON payments(stripe_payment_intent_id)
    WHERE stripe_payment_intent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payments_pending
    ON payments(created_at DESC)
    WHERE status = 'pending';

-- ---------------------------------------------------------------------------
-- 2) invoices (multi-pays, multi-langues)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id                    BIGSERIAL PRIMARY KEY,
    invoice_id            UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    invoice_number        TEXT NOT NULL UNIQUE,            -- ex. UBA-202604-000001
    payment_id            UUID NOT NULL REFERENCES payments(payment_id),
    project_id            TEXT NOT NULL,
    owner_email           TEXT NOT NULL,
    country               CHAR(2) NOT NULL,
    locale                TEXT NOT NULL DEFAULT 'en',
    description           TEXT NOT NULL DEFAULT '',
    net_amount_cents      INTEGER NOT NULL CHECK (net_amount_cents >= 0),
    vat_pct               NUMERIC(5,2) NOT NULL DEFAULT 0,
    vat_amount_cents      INTEGER NOT NULL DEFAULT 0,
    gross_amount_cents    INTEGER NOT NULL CHECK (gross_amount_cents >= 0),
    currency              CHAR(3) NOT NULL,
    vat_label             TEXT NOT NULL DEFAULT 'VAT',
    pdf_url               TEXT,                            -- rempli par job async
    seq_in_month          INTEGER NOT NULL,
    issued_year           INTEGER NOT NULL,
    issued_month          INTEGER NOT NULL CHECK (issued_month BETWEEN 1 AND 12),
    issued_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (issued_year, issued_month, seq_in_month)
);

CREATE INDEX IF NOT EXISTS idx_invoices_project_recent
    ON invoices(project_id, issued_at DESC);

CREATE INDEX IF NOT EXISTS idx_invoices_owner_recent
    ON invoices(owner_email, issued_at DESC);

CREATE INDEX IF NOT EXISTS idx_invoices_country_month
    ON invoices(country, issued_year, issued_month);

-- ---------------------------------------------------------------------------
-- 3) refunds
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refunds (
    id                  BIGSERIAL PRIMARY KEY,
    refund_id           UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    payment_id          UUID NOT NULL REFERENCES payments(payment_id),
    amount_cents        INTEGER NOT NULL CHECK (amount_cents > 0),
    reason              TEXT NOT NULL CHECK (reason IN
                            ('sla_violation','duplicate_payment',
                             'requested_by_customer','fraudulent',
                             'project_cancelled','other')),
    detail              TEXT NOT NULL DEFAULT '',
    stripe_refund_id    TEXT,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_refunds_payment_recent
    ON refunds(payment_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_refunds_reason_recent
    ON refunds(reason, requested_at DESC);

-- ---------------------------------------------------------------------------
-- 4) webhook_events : Stripe + autres sources (idempotency strict)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_events (
    id                    BIGSERIAL PRIMARY KEY,
    event_db_id           UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    idempotency_key       TEXT NOT NULL UNIQUE,            -- e.g. event.id de Stripe
    source                TEXT NOT NULL DEFAULT 'stripe',
    event_type            TEXT NOT NULL,
    signature_verified    BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json          JSONB NOT NULL,
    payment_id            UUID REFERENCES payments(payment_id),
    received_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_type_recent
    ON webhook_events(event_type, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_webhook_events_unprocessed
    ON webhook_events(received_at DESC)
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_webhook_events_payment
    ON webhook_events(payment_id, received_at DESC)
    WHERE payment_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Vues : revenue 30j + funnel
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_revenue_30d AS
SELECT
    currency,
    COUNT(*) FILTER (WHERE status = 'succeeded') AS paid_count,
    SUM(amount_cents) FILTER (WHERE status = 'succeeded') AS total_paid_cents,
    SUM(amount_cents) FILTER (WHERE status = 'refunded') AS total_refunded_cents,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count
  FROM payments
 WHERE created_at >= NOW() - INTERVAL '30 days'
 GROUP BY currency;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9H
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

    seal_payload := '{"event":"v9_phase9h_billing","version":"9.0.0-phase9h","date":"2026-04-30","tables":["payments","invoices","refunds","webhook_events"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_038_v9_billing',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9H billing sealed (chain_hash=%)', new_chain_hash;
END
$$;
