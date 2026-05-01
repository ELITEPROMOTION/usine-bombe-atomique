# V9 Security Audit Report — Phase 4 production readiness

**Date** : 2026-05-01
**Branche** : `main`
**Auditeur** : automatisé (Bandit + ruff + grep manuel + revue OWASP)
**Statut** : PASS pour V9 modules, dette legacy documentée

---

## 1. Résumé exécutif

Audit statique complet de la V9 :
- ✅ 0 issue Bandit High global (HIBP SHA-1 corrigée Phase 2)
- ✅ 0 issue Bandit Medium+ sur modules V9 (saas_factory/, security/, routers/)
- ✅ 0 secret en clair dans le code (grep + Bandit)
- ✅ 779 tests verts, dont 13 tests sécurité-spécifiques
- ⚠ 13 issues Bandit Medium dans modules legacy V5-V8 (non-bloquantes)

**Pentest dynamique non exécuté** : nécessite environnement déployé +
outils (nmap/nuclei/burp). Recommandé en Phase 7 staging avant
promotion prod.

---

## 2. OWASP Top 10 (2021) — couverture V9

| ID | Catégorie | Couverture V9 |
|---|---|---|
| A01:2021 | Broken Access Control | ✅ JWT admin (RBAC roles 9J) + JWT client (`project_id` scope-bound 9M-bis) + AuthGuard frontend issuer-aware (Phase 2). |
| A02:2021 | Cryptographic Failures | ✅ HS256 JWT (jose lib), SHA-256 pour email hash (Sentry GDPR), HMAC-SHA256 webhook Stripe. ⚠ TLS at-rest dépend du déploiement. |
| A03:2021 | Injection | ✅ asyncpg paramétrisé `$1/$2` partout. 1 cas f-string SQL annoté `nosec B608` avec whitelist statique. |
| A04:2021 | Insecure Design | ✅ ADRs documentent les choix critiques (07-34). Live gates `UBA_LIVE_*` fail-safe par défaut. Kill switches `UBA_KILL_*`. |
| A05:2021 | Security Misconfiguration | ✅ HeadersMiddleware (HSTS, X-Frame-Options, CSP, Referrer-Policy) Phase 9J. CORS allow_origins typed (pas de `*`). |
| A06:2021 | Vulnerable Components | ⚠ `requirements.txt` à scanner avec `pip-audit` ou Snyk en CI (recommandé V10). Pas de scan auto V9. |
| A07:2021 | Identification & Authentication | ✅ JWT signé HS256, expiration courte (admin 60min / client 24h). 503 fail-closed si secret absent. ⚠ Pas de 2FA / WebAuthn (V10). |
| A08:2021 | Software & Data Integrity | ✅ Audit triggers append-only (BEFORE UPDATE/DELETE RAISE EXCEPTION) sur 5 tables critiques. Evidence chain hash. Webhooks idempotency UNIQUE key. |
| A09:2021 | Security Logging & Monitoring | ✅ AdminAuditLogger trace toutes actions override. V9Metrics 16 métriques + Sentry context. ⚠ Centralized SIEM dépend du déploiement. |
| A10:2021 | Server-Side Request Forgery | ✅ Pas d'endpoint user-controlled URL fetch dans V9. Webhooks vérifiés par signature HMAC. ⚠ httpx calls vers Stripe/Hostinger/Anthropic gated par live mode + CB. |

---

## 3. Static analysis

### Bandit (severity ≥ Medium, V9 modules)

| Scope | High | Medium | Low |
|---|---|---|---|
| `app/saas_factory/` | 0 | 0 | 0 |
| `app/security/` | 0 | 0 | 0 |
| `app/routers/client.py` | 0 | 0 | 0 |
| `app/routers/admin/` | 0 | 0 | 0 |
| `app/observability/` | 0 | 0 | 0 |

**V9 scope clean.**

### Bandit (legacy modules — dette à traiter V10)

13 Medium issues dans `app/osint/`, `app/tools/`, `app/intelligence/` :
- B608 SQL injection false-positives (whitelist enums) — nosec
  recommandé.
- B311 random PRNG — déjà `secrets.SystemRandom` partout en V9 ; legacy
  utilise `random.Random()`.
- B105 hardcoded password string (placeholder dans tests).

**Aucun blocker production.** Listées dans
`V9_IMPROVEMENTS_REPORT.md` comme dette V10.

### Ruff

| Scope | Erreurs |
|---|---|
| V9 modules | 0 |
| Legacy V5-V8 | 122 |

**0 erreur sur les fichiers V9.** Legacy = dette refactor V10.

### Secrets in code (grep audit)

Pattern recherchés : `password|secret|api_key|token = "<20+ chars>"`.

**Résultat** : 0 match dans `app/` et `tests/` après filtrage des
fixtures (placeholder, mock, stub, test_).

---

## 4. Audit chain hash integrity (ADR-23)

5 tables append-only avec triggers BEFORE UPDATE/DELETE :
- `audit_events` (rétention 7 ans, SOC 2)
- `evidence_ledger` (chain hash)
- `mandates` (eIDAS)
- `admin_actions` (RBAC override traceability)
- `ai_decisions_log` (FinOps audit)

Toute tentative UPDATE/DELETE lève `RAISE EXCEPTION 'audit_events is
append-only'`. **Migration 042 testée**, vérifiée avec test smoke
sur la chain hash linkage.

---

## 5. Auth flow security

### Admin (Phase 9J, ADR-22)

- **JWT HS256** signé avec `JWT_ADMIN_SECRET` (≥ 32 chars enforced).
- **Issuer** distinct `uba-studio/admin` rejette cross-issuer.
- **Roles** : admin / viewer / auditor (RBAC granular).
- **Mode legacy** `X-Admin-Token` désactivé si JWT mode actif (priorité).
- **Failure modes** : 401 (no auth) / 403 (invalid token) / 503 (no secret).

### Client (Phase 9M-bis, ADR-33)

- **JWT HS256** signé avec `JWT_CLIENT_SECRET` (séparé du admin).
- **Issuer** `uba-studio/client` rejette cross-issuer.
- **Claim `project_id` scope-bound** : tous les endpoints `/client/*`
  filtrent automatiquement.
- **AuthGuard frontend** (Phase 2) : décode `iss` et bloque
  cross-area navigation.
- **Test** : `test_admin_token_rejected_by_client_verify` confirme
  le rejet cross-issuer même si secrets identiques.

---

## 6. Webhooks (Phase 9H)

- Stripe `Stripe-Signature` HMAC-SHA256 verified avec
  `STRIPE_WEBHOOK_SECRET`.
- Idempotency : UNIQUE `idempotency_key` sur `webhook_events` table.
  Replay → 200 OK silent.
- Tests : signature mismatch / replay / live gate / pdf token
  validation.

---

## 7. Privacy GDPR

- Email **jamais** envoyé brut à Sentry — SHA-256[:16] hash (ADR-28).
- IP hash SHA-256 dans `user_consents.ip_hash`.
- Erasure préserve audit chain (Art 17§3, ADR-26) — tables eIDAS /
  SOC 2 / FinOps non touchées.
- Documents légaux versioned + checksum SHA-256.

---

## 8. Recommandations dynamiques (Phase 7 staging)

Avant promotion prod, exécuter en staging :

- [ ] **pip-audit** sur `requirements.txt` : detect CVE upstream.
- [ ] **npm audit** sur `frontend/package-lock.json`.
- [ ] **OWASP ZAP** sur l'app déployée : test passive scan +
  active scan (sandbox).
- [ ] **Burp Suite** ou équivalent : explorer les endpoints
  `/admin/*` et `/client/*` avec un proxy.
- [ ] **TLS configuration** : `testssl.sh` ou Mozilla Observatory
  ≥ B+.
- [ ] **DNS CAA records** configurés (Let's Encrypt only).
- [ ] **Rate limiting** test : 1000 req/s sur `/api/v1/auth/login`
  doit être bloqué.
- [ ] **JWT brute-force resistance** : tester 100k tentatives en 1h
  avec rate limiter.
- [ ] **Secrets rotation drill** : rotate `JWT_ADMIN_SECRET` et
  vérifier que tous les tokens en vol sont invalidés (utilisateurs
  doivent re-login).

---

## 9. Dette sécurité documentée (V10+)

- **2FA / WebAuthn admin** : recommandé pour comptes admin (Yubikey).
- **Distributed JWT revocation list** : pour rotation immédiate
  cross-pods. Aujourd'hui = restart pod nécessaire.
- **Encryption at-rest** : dépend du provider DB (RDS chiffré OK).
  Pas de chiffrement applicatif additionnel.
- **HSM pour secrets** : Vault déjà câblé (`VAULT_ADDR`), à activer
  en prod pour secrets sensibles.
- **CSP report-uri** : actuellement CSP statique, pas de reporting
  des violations.
- **Honeytokens** : aucun token leurre dans les logs / DB pour
  détecter exfiltration.

---

## Verdict Phase 4

**PASS** pour V9 production-ready côté audit statique.

**Pentest dynamique** à exécuter en staging (Phase 7) avec les
outils listés section 8.

**Voir aussi** :
- `docs/v9/16_security.md` — security overview
- `docs/v9/17_gdpr.md` — GDPR compliance
- `docs/v9/13_incident_response.md` — playbooks scénarios
- `V9_IMPROVEMENTS_REPORT.md` — dette V10 documentée
