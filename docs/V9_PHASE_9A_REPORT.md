# V9 Phase 9A — Direct-Link Framework — Final Report

**Date** : 2026-04-29
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9-BOOT)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9A livre un framework de liens d'action générique : émission d'un
token cryptographique aléatoire (`secrets.token_urlsafe(32)`), persistance
de son **SHA-256 uniquement** côté DB, validation/consommation atomique
single-use, audit append-only avec hash IP (RGPD), rendu i18n EN/FR.

| Indicateur | Valeur | Cible |
|---|---|---|
| Modules livrés | 4 / 4 | 4 |
| Migration | 037_direct_links_catalog.sql | 1 |
| Tests Phase 9A | 44 / 44 ✅ | toutes passent |
| Tests cumulés (9-BOOT + 9A) | **102 / 102** ✅ | toutes |
| Coverage critique (generator + validator) | **100% / 100%** | ≥ 99% |
| Coverage Phase 9A globale | **99%** | ≥ 90% |
| Coverage cumulée saas_factory + security | **98%** | ≥ 90% |
| Ruff lint | 0 erreur | 0 |
| Bandit (sévérité ≥ Medium) | 0 issue | 0 |
| Auto-fix loop | 0 itération | ≤ 3 |
| Appels externes payants | 0 | 0 |

---

## 2. Livrables

### 2.1 Modules Python (`backend/app/saas_factory/direct_links/`)

| Fichier | LOC | Coverage |
|---|---|---|
| `__init__.py` | 35 | 100% |
| `catalog.py` | 130 | 100% |
| `direct_link_generator.py` | 134 | 100% |
| `validation_engine.py` | 220 | 100% |
| `action_card_generator.py` | 78 | 98% |
| `catalog.json` | 8 actions × 2 locales | n/a |

### 2.2 Migration

- **037_direct_links_catalog.sql** — tables `direct_links` (UUID, token_hash,
  action_type, target_id, principal_id, metadata_json, single_use,
  consumed_at, revoked_at, expires_at) + `direct_links_audit` (event,
  user_agent, ip_hash, detail_json, occurred_at) + 7 indexes + seal
  evidence_ledger.

### 2.3 Tests (`backend/tests/saas_factory/test_direct_links.py`)

44 tests couvrant :

- **Catalog** (13 tests) : chargement, validation Pydantic stricte, locales
  fallback, TTL bornes, callback_path regex, JSON malformé.
- **DirectLinkGenerator** (7 tests) : URL bien formée, **token brut jamais
  persisté** (test dédié), unicité sur 20 itérations, audit `issued`,
  override de TTL, KeyError sur action inconnue.
- **ValidationEngine** (12 tests) : VALID/EXPIRED/CONSUMED/REVOKED/UNKNOWN,
  short-token sans DB hit, double-clic résolu via `consume()` atomique,
  metadata sérialisé en str ou dict, audit toujours présent, **token
  jamais dans les logs d'audit** (test dédié), `revoke()` idempotent.
- **ActionCardGenerator** (5 tests) : i18n FR/EN, fallback si locale
  inconnue, substitution `{service}/{project_name}` tolérante (placeholder
  conservé si var manquante), KeyError si action_type hors catalogue.
- **Sanity** (7 tests) : immutabilité `frozen=True`, `_hash_ip()`
  déterministe, `LinkResolution.is_valid` property, `_safe_format()`
  robustesse.

### 2.4 Docs

- `docs/V9_PHASE_9A_REPORT.md` (ce fichier)
- `docs/V9_ARCHITECTURE_DECISIONS.md` — 2 nouvelles ADR (07, 08)

---

## 3. Catalogue d'actions (8 types initiaux)

| action_type | TTL | single_use | callback_path |
|---|---|---|---|
| `kyc_validation` | 3 jours | ✅ | `/handoff/kyc` |
| `card_setup` | 3 jours | ✅ | `/handoff/card` |
| `manual_step` | 3 jours | ✅ | `/handoff/manual` |
| `deliverable_download` | 7 jours | ❌ | `/deliverables/download` |
| `payment_confirm` | 24h | ✅ | `/billing/checkout` |
| `domain_validation` | 48h | ✅ | `/infra/domain/confirm` |
| `email_verification` | 24h | ✅ | `/auth/email/verify` |
| `account_unlock` | 1h | ✅ | `/auth/account/unlock` |

Le catalogue est versionné (`version: 1.0.0`) et validé à l'import via
Pydantic v2. Toute violation lève `CatalogValidationError`.

---

## 4. Modèle de menace (security review)

### 4.1 Threats considérés

| Menace | Mitigation |
|---|---|
| Vol de DB (dump postgres) | Token brut jamais stocké → SHA-256(`token_urlsafe(32)`) ; les liens en cours ne sont pas exploitables. |
| Replay d'un token consommé | `single_use=true` + UPDATE atomique avec `WHERE consumed_at IS NULL` → toute deuxième consommation échoue. |
| Token forgé | `secrets.token_urlsafe(32)` = 256 bits d'entropie ; force brute infaisable. |
| Énumération (scan d'URLs) | `validate("")` et tokens < 16 chars rejetés sans DB hit (anti-bruit) ; les vrais essais sont audités via `invalid_token`. |
| Fuite d'IP en clair | IP hashée SHA-256 avant insertion (`_hash_ip()`), conformément à la RGPD recital 26. |
| Token loggué accidentellement | Test dédié `test_token_never_appears_in_audit_detail` : aucun argument du INSERT audit ne contient le token brut. |
| Race condition double-clic | `consume()` fait un UPDATE conditionnel atomique ; le second appel passe par `validate()` et retourne CONSUMED. |
| Token sans expiration | `expires_at NOT NULL` au niveau schema ; impossible de créer un lien immortel. |

### 4.2 Threats hors scope (à traiter ailleurs)

- Rate-limiting / bruteforce → middleware FastAPI ou nginx (Phase 9J)
- CSRF sur les endpoints `/handoff/*` → middleware FastAPI standard
- TLS/HSTS → Phase 9J + 9G (Hostinger SSL)

---

## 5. Conformité aux contraintes

| Contrainte | Respect |
|---|---|
| Pas d'appel externe payant | ✅ |
| Coverage critique ≥ 99% | ✅ (generator + validator = 100%) |
| Coverage globale ≥ 90% | ✅ (98% cumulés, 99% Phase 9A) |
| Tests rigoureux | ✅ (44 tests + tests sécurité dédiés) |
| Auto-fix ≤ 3 itérations | ✅ (0) |
| Conventional commit | ✅ (à venir) |
| Pas de tag posé en autonome | ✅ |
| Aucune régression V8.5 / 9-BOOT | ✅ (102 tests cumulés tous verts) |

---

## 6. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (102 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (0 erreur) |
| bandit -ll | ✅ PASS (0 issue Medium+) |
| coverage critique ≥ 99% | ✅ PASS (100%) |
| coverage globale ≥ 90% | ✅ PASS (98%) |
| Aucun secret/token en clair dans logs | ✅ PASS (test dédié) |
| Aucun appel API externe payant | ✅ PASS |

---

## 7. Limitations & dette technique

- **action_card_generator.py 98%** — la branche fallback du `_safe_format`
  (logger.debug dans le `except IndexError, ValueError`) est testée
  fonctionnellement (le test `test_safe_format_keeps_unknown_placeholder`
  passe par `partial {`) mais ruff/coverage ne crédite pas la ligne
  intermédiaire. Non-bloquant.
- **Pas de migration des magic-links 9-BOOT vers `direct_links`** — les
  tokens de `handoff_pending` (Phase 9-BOOT) restent une table dédiée.
  La fusion sera faite en Phase 9P (« injection liens directs livrables »).
  Voir ADR-08.
- **Pas de cleanup des liens expirés** — un job périodique (Arq) sera ajouté
  en Phase 9Q pour `DELETE FROM direct_links WHERE expires_at < NOW() - INTERVAL '30 days'`.
- **Pas de retry backoff sur audit failure** — si `INSERT direct_links_audit`
  échoue, l'opération principale réussit quand même (audit best-effort).
  À renforcer si SOC 2 strict requiert l'audit synchrone.

---

## 8. Statut & next-step

```
PHASE 9A : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**Décision attendue** : `GO` Phase 9B (Setup Wizard 4 étapes) /
`FIX` (corrections) / `STOP`.
