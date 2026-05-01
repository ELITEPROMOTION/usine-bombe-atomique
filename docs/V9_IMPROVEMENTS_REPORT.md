# V9 Improvements Report — Phase 2 production readiness

**Date** : 2026-05-01
**Branche** : `main`
**Statut** : PASS

---

## Résumé exécutif

Phase 2 du plan production V9 résout les **gaps locally fixables**
identifiés dans les phase reports 9-BOOT → 9S, **sans nouvelle infra**.

| Indicateur | Avant | Après |
|---|---|---|
| Tests | 758 | **771 (+13)** |
| Admin endpoints wired | 0 (bug 9N) | **21** |
| `/admin/payments` | absent | livré |
| `/admin/projects/inactive` | absent | livré |
| n8n GDPR webhook | manquant | fire-and-forget câblé |
| ESLint v9 config | absent | livré |
| AuthGuard issuer check | absent | livré (admin/client) |
| Sentry availability cache | re-import à chaque appel | `lru_cache(1)` |
| Bandit High global | 1 (HIBP SHA-1) | **0** (nosec annotation) |
| .env.example V9 keys | partiel | 30+ clés |

---

## Améliorations livrées

### 1. Bug 9N corrigé : admin routers wirés

**Avant** : `app/routers/admin/{ai,handoffs,projects,direct_links,
setup_wizard,onboarding}.py` étaient définis mais **non inclus** dans
`app/main.py`. En production tous les endpoints `/admin/*` retournaient
404. Bug latent depuis 9N.

**Après** : 7 routers admin wirés en bloc. 21 routes admin maintenant
exposées (vérifié via inspection FastAPI app routes).

**Tests** : importation FastAPI app + énumération des routes (script
de vérification).

### 2. Endpoint `/admin/payments?status=...&min_age_hours=N`

**Avant** : workflow n8n 04 (`payment_retry`) consommait un endpoint
inexistant. Workflow non activable.

**Après** : nouveau router `app/routers/admin/payments.py` avec query
params Pydantic-validated (`status`, `min_age_hours`, `limit`).

**Tests** : 3 tests (empty, filter, validation).

### 3. Endpoint `/admin/projects/inactive?days=N`

**Avant** : workflow n8n 06 (`churn_alert`) consommait un endpoint
inexistant.

**Après** : ajouté dans `app/routers/admin/projects.py`. Filtre
projects sans `audit_events` matching `payload_json->>'project_id'`
sur la fenêtre demandée. Respecte la convention status-aware
(exclut `cancelled`/`archived`).

**Tests** : 4 tests (empty, validation min/max, returns inactives).

### 4. GDPR webhook UBA → n8n (fire-and-forget)

**Avant** : workflow n8n 03 (`gdpr_request_notify`) attendait un
webhook entrant que le backend n'émettait pas. Workflow non
déclenchable.

**Après** : `_fire_and_forget_gdpr_webhook()` dans
`app/routers/client.py` :
- Lit `N8N_GDPR_WEBHOOK_URL` env (no-op silencieux si absent).
- Schedulé via `asyncio.create_task` (background, ne bloque pas la
  réponse 202 au client).
- Timeout 2s, toute exception attrapée + loggée DEBUG.
- Émis sur les 2 endpoints POST `/client/profile/gdpr/{export,erasure}`.

**Tests** : 3 tests (env unset → no-op, URL unreachable → no-op,
sync call sans loop → no-op).

### 5. AuthGuard frontend issuer-aware

**Avant** : tout user authentifié pouvait visiter `/` admin **et**
`/client/*`. Pas de séparation enforce côté UI.

**Après** : `AuthGuard` accepte `requiredIssuer` prop et décode le
JWT pour vérifier le claim `iss` :
- `<AuthGuard requiredIssuer="uba-studio/admin" fallbackPath="/client" />`
  pour les routes admin.
- `<AuthGuard requiredIssuer="uba-studio/client" fallbackPath="/" />`
  pour `/client/*`.
- Backward-compat : sans prop, comportement identique à avant.

**Code** : decode JWT via `atob` natif, extrait `payload.iss`,
compare. Tolère JWT malformé (return null → fallback redirect).

### 6. ESLint v9 flat config

**Avant** : `npm run lint` échouait — repo n'avait pas de
`eslint.config.js`. Pré-existant, non bloquant mais bug-prone.

**Après** : `frontend/eslint.config.js` livré, configure :
- `js.configs.recommended` + `tseslint.configs.recommended`
- `react-hooks` plugin
- `react-refresh` warn
- `no-unused-vars` ignore `_*` prefixes
- `no-empty` allow empty catch
- ignores `dist/`, `node_modules/`, `tests/`

### 7. `lru_cache` sur sentry availability

**Avant** : chaque appel à `is_sentry_available()` re-tentait l'import
de `sentry_sdk`. Sur SDK absent, 5-10 µs perdus par appel × thousands
of calls/min en prod = micro-friction inutile.

**Après** : `_sentry_sdk_importable()` séparé + `@lru_cache(maxsize=1)`.
Importable une fois pour toujours. Helper
`_reset_sentry_cache_for_test()` exposé pour tests.

**Tests** : 3 tests (cache stores, returns bool, reset clears).

### 8. Bandit High HIBP SHA-1 annotation

**Avant** : `app/osint/dendani_breach_check.py:85` flagué High par
Bandit (CWE-327, SHA-1 weak hash). C'était un faux positif : HIBP
k-anonymity API exige SHA-1 (RFC k-anonymity model).

**Après** : `# noqa: S324 # nosec B324` annotation + commentaire
explicatif. Bandit High global = 0.

### 9. `.env.example` enrichi V9

**Avant** : `.env.example` reflétait V5/V8. Manquait `JWT_ADMIN_SECRET`,
`JWT_CLIENT_SECRET`, `UBA_LIVE_*`, `STRIPE_*`, `HOSTINGER_*`,
`RESEND_API_KEY`, `SENTRY_DSN`, `UBA_KILL_*`, `UBA_CHAOS_ENABLED`,
n8n env vars, `OPENAI_API_KEY`, `N8N_GDPR_WEBHOOK_URL`.

**Après** : 30+ clés V9 ajoutées avec sections clairement délimitées
et commentaires sur la rotation/usage/sécurité.

---

## Limitations restantes (V10+)

Les limitations ci-dessous **nécessitent infrastructure** ou
investissement non disponibles dans la session actuelle :

- **Distributed circuit breakers** (Redis-backed) — nécessite Redis +
  refactor `CircuitBreaker` async pour persister stats.
- **Multi-project per client** — refactor JWT claim `project_ids:
  list[UUID]` + endpoint `/client/projects` + UI multi-project picker.
- **Magic-link login flow client** — endpoint `/auth/client/request-link`
  + email service Resend + UI page d'attente.
- **Storybook** — tooling investment, ~1 jour de setup.
- **Playwright tests** — tests E2E browser, nécessite Playwright deps
  + CI runner.
- **Light theme** — refactor design tokens + tests visuels.
- **2FA / WebAuthn admin** — nouvelle feature, libs (webauthn-py),
  flow UI.
- **Translations / i18n complet** — `react-i18next` + extraction +
  traductions.

Ces points sont documentés dans `V9_RELEASE_SUMMARY.md` section
"Limitations connues" et `docs/v9/02_master_plan.md` "Hors scope V9".

---

## Quality Gates

| Gate | Statut |
|---|---|
| pytest cumulative | ✅ **771/771 verts** |
| ruff V9 modules | ✅ 0 erreur |
| bandit V9 modules | ✅ 0 Medium+ |
| bandit global High | ✅ 0 (HIBP nosec) |
| Vite build | ✅ 525 KB / 156 KB gzip |
| Docker build | ✅ uba-backend:v9-rc1 |
| FastAPI admin routes | ✅ 21 routes wirées |

---

## Voir aussi

- `V9_RELEASE_SUMMARY.md` — release V9 ULTIMATE
- `docs/v9/02_master_plan.md` — phases livrées + hors scope
- `docs/v9/15_resilience.md` — patterns CB / chaos
- `docs/v9/20_automation.md` — workflows n8n
