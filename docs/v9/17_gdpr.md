# 17 — GDPR compliance

Référence : Phase 9I (`docs/V9_PHASE_9I_REPORT.md`), ADR-25/26.

## Articles couverts

| Article | Module | Endpoint client |
|---|---|---|
| Art 6.1.a (consentement) | `ConsentManager.record_consent` | PATCH `/client/profile/consents` |
| Art 6.1.b (contrat) | Onboarding 9F + ToS | (implicite) |
| Art 6.1.c (obligation légale) | invoices 10 ans, audit 7 ans | n/a |
| Art 7.3 (retrait simple) | `revoke_consent` (1 appel) | PATCH consents (toggle off) |
| Art 13 (info au sujet) | Privacy Policy + reason requis erasure | UI `/client/profile` |
| Art 15 (accès) | `GDPRExporter.export_for_project` | (job async) |
| Art 17 (oubli) | `GDPREraser` avec retention 17§3 | POST `/client/profile/gdpr/erasure` |
| Art 17§3 (exception légale) | Audit trail préservé | (automatique) |
| Art 20 (portabilité) | Export JSON serialisable | POST `/client/profile/gdpr/export` |

## Modèle de consentement

7 scopes définis (`ConsentScope` enum) :
- `tos_acceptance`, `privacy_policy`
- `cookie_functional`, `cookie_analytics`, `cookie_marketing`
- `data_processing`, `marketing_opt_in`

Storage : table `user_consents` avec `owner_email`, `scope`,
`doc_version`, `accepted_at`, `revoked_at`, `ip_hash` SHA-256.

Sur l'UI client (Phase 9M, page Profile), 2 toggles exposés :
- `consent_marketing` ↔ scope `marketing_opt_in`
- `consent_analytics` ↔ scope `cookie_analytics`

## Erasure (Art 17 + 17§3)

### Modèle

1. Client soumet : POST `/client/profile/gdpr/erasure` avec `reason`.
2. Backend insère row dans `data_erasure_requests` status `pending`,
   `executable_after = now + 30 days`.
3. **Fenêtre 30j** : peut être annulée si erreur ou fraude.
4. Après 30j : admin déclenche `execute_erasure(request_id)`.
5. Anonymisation des colonnes PII des **tables non-audit** :
   - `projects.owner_email` → `erased@redacted.local`
   - `projects.company_name` → `[ERASED]`
   - `projects.summary_json` → `{"erased": true}`
   - `payments.owner_email` → idem
   - `invoices.owner_email` + `description` → idem
   - `handoff_requests.target_email` → idem
   - `client_onboarding_sessions.owner_email` + `partial_data_json` → idem

### Préservation audit (Art 17§3)

Tables **non touchées** (obligation légale) :
- `mandates` (eIDAS, durée vie + 7 ans)
- `evidence_ledger` (chain hash, SOC 2)
- `admin_actions` (SOC 2)
- `ai_decisions_log` (FinOps audit, 3 ans)
- `audit_events` (SOC 2, 7 ans)

Justification : ces tables contiennent des **hashes** ou **pseudonymes**,
pas de PII brute. Les triggers append-only (ADR-23) bloqueraient
toute tentative de modification de toute façon.

### Force erasure

`execute_erasure(request_id, force=True)` permet d'exécuter avant
les 30j (admin override pour litige RGPD urgent). **Tracé** dans
`admin_actions`.

## Cross-border transfers

Privacy Policy mentionne explicitement :
- Stripe (US) sous Standard Contractual Clauses (SCC)
- Anthropic (US) sous SCC

Documenté côté légal avec contrats SCC signés.

## Contact DPO

- Email DPO : configuré via env var `DPO_EMAIL` (workflow n8n 03).
- Workflow 03 (Phase 9Q) notifie le DPO + Slack #compliance dès
  qu'une demande GDPR est soumise.

## Vue admin

```sql
SELECT * FROM v_gdpr_compliance;
-- consents_active, consents_revoked, exports_pending,
-- exports_completed, erasures_pending, erasures_executed
```

## Limitations V9

- **Documents AR/ES placeholders** — review légale locale requise
  avant production.
- **DPA (Data Processing Addendum)** non livré — utile pour B2B
  clients qui exigent un DPA signé.
- **Pas d'auto-detect law per country** : on applique GDPR à tous
  (ADR-25). Si client chinois exige PIPL strict ou US exige CCPA
  opt-out-of-sale, étendre.
- **Erasure n'envoie pas de notification** : à câbler via Resend
  ultérieurement.

## Voir aussi

- [16 — Security](./16_security.md)
- [12 — Admin runbook](./12_admin_runbook.md)
- `docs/V9_PHASE_9I_REPORT.md`
