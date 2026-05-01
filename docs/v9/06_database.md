# 06 — Database & migrations

## Stack

PostgreSQL 15+ avec extensions `pgcrypto` (gen_random_uuid) et
`uuid-ossp` (selon migrations historiques).

## Migrations

50+ fichiers SQL dans `migrations/versions/`. Convention :

```
NNN_<topic>.sql
```

Exécution séquentielle, idempotent (CREATE TABLE IF NOT EXISTS).

| # | Topic | Phase |
|---|---|---|
| 001–006 | initial, RLS, audit, evidence | early |
| 007 | audit_events (append-only) | V8 |
| 037 | direct_links_catalog | 9C |
| 038 | billing_full (payments, invoices, refunds, webhook_events) | 9H |
| 039 | hostinger_provisioning (domains, vps, ssl, backups) | 9G |
| 040 | ai_decisions_log | 9D |
| 041 | intelligence_engine (qualification, pricing, assembly) | 9E |
| 042 | audit_trail_immutable (BEFORE UPDATE/DELETE triggers) | 9J |
| 043 | self_bootstrap | 9-BOOT |
| 044 | mandates_eidas | 9P |
| 045 | setup_wizard | 9B |
| 046 | handoff_orchestrator | 9A |
| 047 | client_onboarding + projects (canonique) | 9F |
| 048 | admin_actions | 9J |
| 049 | consolidation (FK rétroactives) | 9P |
| 050 | legal_framework (user_consents + GDPR requests) | 9I |

## Tables canoniques

- `projects` (047) : owner_email, company_name, pack_id_hint, status
  enum 8, summary_json, created_at/updated_at.
- `payments` (038) : payment_id UUID, project_id TEXT (FK rétroactive
  9P), amount_cents, currency, status enum 6.
- `invoices` (038) : invoice_id UUID, payment_id FK, gross_amount_cents,
  pdf_url.
- `handoff_requests` (046) : handoff_id UUID, action_type, state enum 7.
- `audit_events` (007) : append-only, retention 7 ans.
- `evidence_ledger` (004) : chain hash, append-only.
- `user_consents` (050) : owner_email, scope enum 7, doc_version.
- `data_export_requests` (050) / `data_erasure_requests` (050) : GDPR.

## FK rétroactives (ADR-15 + ADR-24)

Plusieurs FK étaient en TEXT en 9C/9D/9E (avant 9F qui a livré la
table `projects` canonique). 9P (migration 049) les a converties en
UUID FK avec cleanup orphans préalable. Pattern :

```sql
-- 1. Cleanup orphans
DELETE FROM child WHERE project_id NOT IN (SELECT project_id FROM projects);
-- 2. ALTER COLUMN
ALTER TABLE child ALTER COLUMN project_id TYPE UUID USING project_id::UUID;
-- 3. ADD CONSTRAINT
ALTER TABLE child ADD CONSTRAINT fk_child_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);
```

## Audit immutability (ADR-23)

Tables `audit_events`, `evidence_ledger`, `mandates`,
`admin_actions`, `ai_decisions_log` ont des **BEFORE UPDATE/DELETE
triggers** qui RAISE EXCEPTION. Toute tentative de modification se
fail.

```sql
CREATE TRIGGER trg_table_block_update
  BEFORE UPDATE ON <table>
  FOR EACH ROW EXECUTE FUNCTION table_block_mutations();
```

GDPR erasure (Art 17§3) anonymise des **autres** tables (projects,
payments, invoices, handoff_requests, client_onboarding_sessions)
mais **préserve** ces 5 tables d'audit.

## Index policies

- Index sur `(status, created_at DESC)` pour les listes admin.
- Index partiel `WHERE status NOT IN ('cancelled', 'archived')` pour
  les vues "actifs".
- Index `WHERE owner_email IS NOT NULL` sur les sessions.

## Voir aussi

- [04 — Backend dev](./04_backend_dev.md)
- [17 — GDPR](./17_gdpr.md)
- `docs/V9_PHASE_9P_REPORT.md` (FK rétroactives)
