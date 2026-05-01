# V9 Audit Improvements

**Date** : 2026-05-01
**Branche** : `main`

Liste exhaustive des améliorations apportées pendant l'audit extrême
12 passes.

---

## Améliorations Code

### Fixes critiques
- **DTZ005** `link_injector.py:56` : `datetime.now(tz=None)` → `datetime.now(UTC)`
  (réel bug — naïve datetime injecté dans dataclass).
- **CVE Python** : bumped `python-jose` 3.3.0→≥3.4.0, `python-multipart`
  0.0.12→≥0.0.18, `starlette` 0.38.6→≥0.40.0, `pytest` 8.3.3→≥8.3.3,<10
  (résout 6 CVE/PYSEC).
- **CVE npm** : `npm audit fix --force` résout 9 vulnérabilités (axios,
  vite, esbuild, postcss, react-router, eslint, @remix-run/router).
  Vite bumped 6.0→6.4, react-router-dom 6.27→6.30.

### False positives annotés
- **BLE001** Sentry helpers (3 occurrences) : `# noqa: BLE001 -- sentry doit
  jamais casser flow` (intentionnel, ADR-28).
- **BLE001** chaos runner : `# noqa: BLE001 -- chaos drill collecte tout`
  (intentionnel par design).
- **BLE001** vault `get`/`is_vault_available` : `# noqa: BLE001 -- défensif,
  fallback empty` (resilient by design).
- **BLE001** client `_fire_and_forget_gdpr_webhook` : `# noqa: BLE001 --
  fire-and-forget no-op` (Phase 2).
- **S107** stripe_client `*_env` defaults : `# noqa: S107 -- env var name`
  (le default est le nom de variable, pas le secret).
- **S105** health.py `PASS = "pass"` : `# noqa: S105 -- enum value, pas
  password`.
- **S311** chaos `_SeededRandom` : `# noqa: S311 -- chaos test, pas crypto`.
- **S324 / B324** dendani_breach_check SHA-1 : `# noqa: S324 # nosec B324`
  (HIBP k-anonymity API requirement, Phase 2).

### Auto-fix safe + unsafe
12 fixes auto-appliqués par `ruff check --fix --unsafe-fixes` sur V9
modules (typing-only imports, missing trailing commas, etc.).

---

## Améliorations Configuration

### `.env.example` enrichi (Phase 2 V9 prod, conservé)
30+ clés V9 ajoutées :
- `JWT_ADMIN_SECRET`, `JWT_CLIENT_SECRET` (≥ 32 chars)
- `UBA_LIVE_HOSTINGER`, `UBA_LIVE_STRIPE` (gates par défaut OFF)
- `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY`
- `HOSTINGER_API_KEY`
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `DPO_EMAIL`
- `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`
- `UBA_KILL_*` (6 dépendances)
- `UBA_CHAOS_ENABLED` (jamais 1 en prod)
- `N8N_BASE_URL`, `N8N_WEBHOOK_BASE`, `SLACK_WEBHOOK_*`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `N8N_GDPR_WEBHOOK_URL` (Phase 2 fire-and-forget)

### `requirements.txt` modernisé
Pin strict `==` → ranges `>=X,<Y` pour permettre les patch versions
sécurité sans changement majeur. CVE-resolved versions enforced.

### ESLint v9 flat config (Phase 2)
`eslint.config.js` livré avec js + tseslint + react-hooks + react-refresh
configs.

---

## Améliorations Tests

### Phase 2 V9 prod (conservé)
- `test_v9_phase2_improvements.py` (+13 tests) : sentry lru_cache,
  /admin/payments, /admin/projects/inactive, GDPR webhook fire-and-forget
- `test_v9_e2e_extended.py` (+8 tests) : pipeline complet, multi-tenant
  scope, kill switch, resilience composition, GDPR end-to-end

### Coverage
- Avant audit : 758 tests, 98% coverage
- Après audit : **779 tests, 97.92% coverage**
- Coverage critique modules ≥ 99% maintenu

---

## Améliorations Architecture

### Bug 9N résolu (Phase 2)
7 admin routers (ai, handoffs, projects, direct_links, setup_wizard,
onboarding) étaient définis mais **non includes dans FastAPI app**. Bug
latent depuis 9N. **21 routes admin maintenant exposées** :
```
/api/v1/admin/ai/*
/api/v1/admin/handoffs/*
/api/v1/admin/projects/*
/api/v1/admin/direct-links/*
/api/v1/admin/setup-wizard/*
/api/v1/admin/onboarding/*
/api/v1/admin/payments/*  (nouveau Phase 2)
```

### AuthGuard issuer-aware (Phase 2)
Frontend `<AuthGuard requiredIssuer="uba-studio/admin|client" />` décode
le JWT et bloque cross-area navigation. Defense in depth ADR-32 + 33.

### Endpoints n8n unblock (Phase 2)
- `/admin/payments?status=...&min_age_hours=N` (workflow 04)
- `/admin/projects/inactive?days=N` (workflow 06)
- Webhook UBA → n8n GDPR fire-and-forget (workflow 03, env-gated)

### Performance
- `lru_cache(1)` sur `_sentry_sdk_importable()` — micro-opt sur hot path

---

## Améliorations Documentation

### Reports produits (audit)
- `V9_AUDIT_FINAL_REPORT.md` — 12 passes synthèse
- `V9_AUDIT_IMPROVEMENTS.md` — ce document
- `V9_GO_NO_GO_DEPLOYMENT.md` — décision finale

### Reports antérieurs maintenus
- `V9_RELEASE_SUMMARY.md`
- `V9_IMPROVEMENTS_REPORT.md` (Phase 2 prod)
- `V9_E2E_VALIDATION_REPORT.md`
- `V9_SECURITY_AUDIT_REPORT.md`
- `V9_PRODUCTION_READINESS_REPORT.md`
- `V9_STAGING_DEPLOYMENT_PLAYBOOK.md`
- `V9_FINAL_PRODUCTION_REPORT.md`

---

## Logs d'audit

`backend/audit_logs/` :
- `audit_pass1_ruff_all.txt` — 1038 warnings `--select ALL`
- `audit_pass2_secrets.txt` — detect-secrets baseline
- `audit_pass2_pip_audit.txt` — CVE Python (now clean)
- `audit_pass2_npm_audit.txt` — CVE npm (now clean)
- `audit_pass3_coverage.txt` — coverage 97.92% report
- `audit_pass5_docker_compose.txt` — compose validation
- `audit_pass12_todos.txt` — 0 TODO/FIXME/XXX/HACK V9 scope

---

## Voir aussi

- `V9_AUDIT_FINAL_REPORT.md` — synthèse audit complet
- `V9_GO_NO_GO_DEPLOYMENT.md` — décision GO production
