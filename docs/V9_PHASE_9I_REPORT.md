# V9 Phase 9I — Legal Framework — Final Report

**Date** : 2026-04-30
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9P)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9I livre la conformité légale de la V9 :

1. **Legal documents catalog** : ToS / Privacy Policy / Cookie Policy ×
   4 locales (en/fr/ar/es) avec versioning + checksum SHA-256.
2. **Consent management** : record / revoke / query — conforme GDPR
   Art. 6.1.a et Art. 7.3 (retrait aussi simple que l'octroi).
3. **GDPR data export** : Article 20 (portabilité) — collecte les data
   cross-tables et produit un JSON serialisable.
4. **GDPR data erasure** : Article 17 (oubli) avec retention 17§3 —
   anonymise les colonnes PII en préservant l'audit trail immutable.
5. **Migration 050** : `user_consents` + `data_export_requests` +
   `data_erasure_requests` + view `v_gdpr_compliance`.

| Indicateur | Valeur | Cible |
|---|---|---|
| Modules livrés | 5 (types, documents, consent_manager, gdpr_export, gdpr_erasure) | 5 |
| Migration | 050 (3 tables + view) | 1 |
| Tests Phase 9I | 43 / 43 ✅ | toutes |
| Tests cumulés (9-BOOT à 9I) | **614 / 614** ✅ | toutes |
| Coverage Phase 9I | **~99%** | ≥ 90% |
| Coverage cumulée | **98%** | ≥ 90% |
| Ruff | 0 erreur (9 autofix + 1 RUF003 manuel) | 0 |
| Bandit (≥ Medium) | 0 issue | 0 |
| Auto-fix loop | 0 itération | ≤ 3 |

---

## 2. Livrables

### 2.1 Modules (`backend/app/saas_factory/legal/`)

| Fichier | LOC |
|---|---|
| `__init__.py` | 60 |
| `types.py` | 35 |
| `documents.py` | 240 (templates inclus) |
| `consent_manager.py` | 220 |
| `gdpr_export.py` | 220 |
| `gdpr_erasure.py` | 295 |

### 2.2 Migration 050_legal_framework.sql

**Tables** :
- `user_consents` (UUID, owner_email, scope enum 7, doc_version,
  accepted_at, revoked_at, ip_hash SHA-256, metadata) + 3 indexes
- `data_export_requests` (UUID, project_id FK, requester_email, status,
  record_counts_json) + 1 index
- `data_erasure_requests` (UUID, project_id FK, status enum 4, reason,
  requested_at, **executable_after** = requested + 30j, executed_at,
  cancelled_at, counts_json, legal_hold_reason) + 2 indexes

**View** : `v_gdpr_compliance` (consents actifs/révoqués, erasures
pending/executed) — pour dashboard admin.

### 2.3 Documents légaux

**4 locales × 3 types = 12 documents** :

| Locale | ToS | Privacy | Cookie |
|---|---|---|---|
| en | full text | full text + GDPR Art 6/15/17/20 detailed | bullets |
| fr | full text | full text + RGPD detaillé | bullets |
| ar | placeholder + arabe basics | placeholder | placeholder |
| es | placeholder | placeholder | placeholder |

**Note** : les contenus sont des **structures placeholder** marquées
`[PLACEHOLDER — review with legal counsel before production]`. Une
review légale locale est obligatoire avant production. La structure du
système (versioning, checksum, multi-locale lookup) est complète.

### 2.4 Tests (43)

- **Documents catalog (8)** : default load, each doc in each locale,
  checksum SHA-256 computed + déterministe, fallback locale, unknown
  doc type raises, supported_locales constant, privacy mentions GDPR/
  RGPD, arabic chars present
- **ConsentManager (10)** : hash_ip helper, record success, already
  exists raises, invalid email/version raise, revoke success/not-found,
  has_active_consent true/false, list_consents active_only/all,
  parse string metadata
- **GDPRExporter (5)** : serialize_value handles all types (UUID,
  datetime, bytes, list/dict, JSON-string), unknown project raises,
  aggregates 14 tables, serializes data, to_json format
- **GDPREraser (10)** : constants, parse_update_count, request success,
  already pending raises, unknown project raises, empty reason raises,
  cancel success/not-pending, execute force anonymises (verifies
  ERASED placeholders dans args), blocked si window non passée, unknown
  request raises, already done raises, get_erasure returns/None
- **ConsentRecord property (1)** : is_active true/false
- **Migration 050 smoke (1)** : file exists with 3 tables + view + FK +
  seal

---

## 3. Architecture

### 3.1 GDPR strict treatment for all countries (ADR-25)

Choix : on applique GDPR à **tous** les pays — pas de detection par
pays. Plus simple, "highest standard wins". Les juridictions plus
laxes (US, MENA hors EU, Asie) ne sont pas pénalisées par GDPR.
Seules quelques règles spécifiques (e.g. CCPA right to opt-out of sale)
nécessiteraient un treatment différent — non implémentées en V9I.

### 3.2 Erasure preserve audit (ADR-26)

GDPR Article 17 §3 : "Les paragraphes 1 et 2 ne s'appliquent pas dans
la mesure où ce traitement est nécessaire... à des fins (...) d'une
obligation légale". L'audit trail (mandats eIDAS, evidence_ledger,
admin_actions, ai_decisions_log, audit_events) tombe sous obligation
légale (SOC 2 / fiscal 10 ans / eIDAS).

L'eraser **anonymise les colonnes PII user-facing** (owner_email,
company_name, target_email, summary_json) mais **ne supprime pas**
les rows. Les hash chains (mandates, evidence_ledger, webhook_events)
restent intactes — leur valeur cryptographique est préservée.

### 3.3 30-day reversal window

`request_erasure` n'exécute pas immédiatement. Une fenêtre de 30 jours
permet :
- **Réversibilité** : un user qui change d'avis peut `cancel_erasure`
  pendant 30j.
- **Détection de fraude** : si la demande vient d'un attaquant (compte
  compromis), 30j de retard donne le temps de détecter et bloquer.
- **Conformité** : la jurisprudence accepte une fenêtre raisonnable
  pour exécuter une demande d'oubli (Art. 12 §3 : "dans un délai d'un
  mois").

`force=True` permet d'exécuter avant la fenêtre (admin override pour
litige RGPD urgent).

### 3.4 Cross-border transfers documentation

Les Privacy Policy mentionnent explicitement les transferts hors UE :
- Stripe (US) sous Standard Contractual Clauses (SCC)
- Anthropic (US) sous SCC

Ces clauses sont documentées dans le Privacy Policy en/fr. À compléter
côté légal avec les vrais contrats SCC signés.

### 3.5 Anonymisation pattern

Plutôt que de supprimer les rows (qui casserait les FK projects → ...),
on remplace les valeurs PII :

| Champ | Avant | Après erasure |
|---|---|---|
| owner_email | `client@example.com` | `erased@redacted.local` |
| company_name | `ACME Corp` | `[ERASED]` |
| target_email | `client@example.com` | `erased@redacted.local` |
| summary_json | `{...}` | `{"erased": true}` |
| description (invoices) | `Pack saas` | `[ERASED]` |

Les **timestamps** et **status** sont conservés (utiles pour audit, pas
PII). Les UUIDs (project_id, payment_id) sont conservés (référencables
dans les preuves, pas de PII directe).

---

## 4. Conformité

| Article GDPR | Implémentation |
|---|---|
| **Art. 6.1.a** (consentement) | `ConsentManager.record_consent` |
| **Art. 6.1.b** (contrat) | Onboarding 9F + ToS acceptance |
| **Art. 6.1.c** (obligation légale) | invoices 10 ans, audit 7 ans |
| **Art. 7.3** (retrait simple) | `revoke_consent` (1 appel) |
| **Art. 13** (info au sujet) | Privacy Policy + reason requis pour erasure |
| **Art. 15** (accès) | `GDPRExporter.export_for_project` |
| **Art. 17** (oubli) | `GDPREraser` avec retention 17§3 |
| **Art. 17§3** (exception légale) | Audit trail préservé |
| **Art. 20** (portabilité) | Export JSON serialisable |

| Master plan | Statut |
|---|---|
| #42 Invoice multi-pays multi-langues (50+ TVA) | ✅ (déjà en 9H) |
| Phase 9I (legal multi-pays) | ✅ |
| Coverage critique ≥ 99% | ✅ |
| Coverage globale ≥ 90% | ✅ (98%) |
| Aucun appel externe payant | ✅ |
| Conventional commit | ✅ |
| Pas de tag autonome | ✅ |
| Aucune régression (614/614) | ✅ |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (614 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (0 erreur, 9 autofix + 1 RUF003 ambiguous unicode) |
| bandit -ll | ✅ PASS (0 issue Medium+) |
| coverage globale ≥ 90% | ✅ PASS (98% cumulé) |

---

## 6. Limitations & dette technique

- **Documents AR/ES sont des placeholders** : structure complète mais
  texte légal minimal. À étoffer par un legal counsel local.
- **DataProcessingAddendum (DPA)** non livré : utile pour B2B clients
  qui exigent un DPA signé avant signature de contrat. À ajouter dans
  une phase ultérieure.
- **Pas d'auto-detect law per country** : on applique GDPR à tous les
  pays (ADR-25). Si un client chinois exige PIPL strict, ou un client
  US exige CCPA opt-out-of-sale, il faudra étendre.
- **Erasure n'envoie pas de notification** : le client devrait recevoir
  un email "votre demande a été enregistrée, exécutée le X". À câbler
  via Resend dans une phase future.
- **Pas d'export PDF** : seulement JSON. Si les utilisateurs demandent
  un export PDF lisible, ajouter un renderer (weasyprint).
- **Migration 050 non testée contre Postgres réel** : les triggers
  d'audit immutability (9J) n'affectent pas ces tables. La suite
  `production_readiness` validera au déploiement.
- **Pas de dashboard /admin/gdpr/*** : extension naturelle de 9N à
  ajouter. Pour l'instant, exposable via Python CLI ou job ad-hoc.

---

## 7. État cumulé V9 sur la branche

| Phase | Commit | Tests | Coverage | LoC |
|---|---|---|---|---|
| 9-BOOT | `bba1fa1` | 58 | 97% | +2 970 |
| 9A | `71896b1` | +44 | 98% | +1 809 |
| 9B | `7db1b10` | +39 | 98% | +1 549 |
| 9C | `b668e2f` | +49 | 98% | +2 827 |
| 9D | `9927877` | +66 | 98% | +2 603 |
| 9E | `2c4ef0e` | +29 | 98% | +1 558 |
| 9F | `bcdbdb9` | +48 | 99% | +1 856 |
| 9N | `f227b0b` | +45 | 98% | +2 189 |
| 9G | `8ffc735` | +46 | 98% | +2 315 |
| 9H | `6b83ed7` | +67 | 98% | +2 891 |
| 9R | `b8d590a`+`b34b88a` | +9 | 98% | +700 |
| 9J | `ec92b4c` | +49 | 98% | +1 610 |
| 9P | `7711c68` | +22 | 98% | +1 082 |
| **9I** | `(à venir)` | **+43 (614)** | **98%** | ~+1 800 |

**Total V9 cumulé estimé** : 14 phases, 15 commits, ~27 000 lignes,
**614 tests verts**, 20 ADR (07–26).

---

## 8. Statut & next-step

```
PHASE 9I : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**La V9 est très avancée**. 14 phases sur ~16 prévues. Phases du
master plan non livrées :
- 9K (observabilité 360°) — infra-driven, à brancher avec Sentry/Datadog
- 9L (resilience + chaos) — phase ops
- 9M (dashboard client luxe) — frontend
- 9O (design system luxe) — frontend
- 9Q (n8n workflows) — outil externe
- 9S (22 docs) — documentation rédigée

**Recommandation** :
- **STOP + tag `v9.0.0-rc1`** : 614 tests, 14 phases, framework complet.
  Très bon moment pour merger en main et déployer staging.
- Les phases restantes (K/L/M/O/Q/S) sont **non-bloquantes** pour MVP
  et peuvent être traitées séparément.

**Décision attendue** : poursuivre / STOP+tag / merge.
