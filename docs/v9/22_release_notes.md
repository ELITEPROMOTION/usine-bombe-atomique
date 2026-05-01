# 22 — Release Notes V9

## V9.0 — UBA Studio Platform (May 2026)

V9 est la première version "production-ready" de UBA Studio
Platform : un orchestrateur SaaS auto-buildé. 22 phases livrées sur
la branche `feature/vague9-bootstrap`.

### Highlights

#### Plateforme self-building
- **Phase 9-BOOT** : platform_config singleton + seed cryptographique.
- **Phase 9P** : consolidation FK rétroactives + deliverables injection.

#### Workflow client end-to-end
- **Phase 9F** : onboarding wizard 6 steps.
- **Phase 9E** : intelligence (pricing + qualification + assembly).
- **Phase 9H** : billing (Stripe + 50+ TVA + invoices PDF).
- **Phase 9G** : infrastructure (Hostinger DNS / VPS / SSL / backup).
- **Phase 9A** : handoff orchestrator (state machine 7 états).
- **Phase 9C** : direct links (token + validation).
- **Phase 9M** : dashboard client luxe (frontend).
- **Phase 9M-bis** : backend `/client/*` (12 endpoints + JWT client).

#### IA orchestration
- **Phase 9D** : AIRouter + CostGuard 3-niveau + LoopDetector +
  retry exponential. Stub providers pour offline tests.

#### Compliance & sécurité
- **Phase 9I** : GDPR Art 6/15/17/20 (consents, export, erasure
  avec retention 17§3).
- **Phase 9J** : JWT admin + RBAC + audit triggers append-only +
  rate limiter + headers middleware.

#### Observability & resilience
- **Phase 9K** : V9Metrics (16 métriques Prometheus) + 9 SLOs
  + V9HealthCheck + Sentry no-op gracieux.
- **Phase 9L** : CircuitBreaker async + TimeoutPolicy + KillSwitch +
  ChaosInjector offline-only.

#### Frontend & UX
- **Phase 9M / 9O** : design system luxe étendu (~30 composants),
  page styleguide, animations framer-motion, dark luxe theme.

#### Operations
- **Phase 9Q** : 6 workflows n8n pré-câblés (paywall reminder,
  handoff escalation, GDPR notify, payment retry, weekly digest,
  churn alert).
- **Phase 9N** : admin endpoints + dual-mode auth (JWT + legacy).
- **Phase 9R** : E2E pipeline tests (mock pool sequenced).

#### Documentation
- **Phase 9S** : 22 docs hub (architecture, deployment,
  observability, GDPR, etc.). Cf. [README hub](./README.md).

### Stats finales

| Métrique | Valeur |
|---|---|
| Phases livrées | 22 |
| Tests backend | 758 verts |
| Coverage globale | 98% |
| LoC backend | ~32 000 |
| LoC frontend | ~3 000 (avec 9M + 9O) |
| Migrations SQL | 50 (001 → 050) |
| ADRs | 28 (07 → 34) |
| Composants design system | 30+ |
| Endpoints admin | 25+ |
| Endpoints client | 12 |
| Workflows n8n | 6 |
| Métriques Prometheus | 16 |
| SLOs | 9 |
| Politiques résilience | 6 |
| Scenarios chaos | 8 |

### Breaking changes vs V8

- Nouvelle table canonique `projects` (047). Anciens project_id en
  TEXT → UUID FK rétroactives (049).
- JWT admin remplace progressivement `X-Admin-Token` legacy (mais
  legacy reste supporté pour migration).
- Live gates obligatoires : `UBA_LIVE_HOSTINGER` et
  `UBA_LIVE_STRIPE` doivent être set explicitement à `1` en prod.
- `JWT_ADMIN_SECRET` ≥ 32 chars requis pour mode JWT.
- `JWT_CLIENT_SECRET` ≥ 32 chars requis pour `/client/*` endpoints.

### Migration V8 → V9

```bash
# 1. Backup DB
pg_dump $DATABASE_URL > backup_pre_v9.sql

# 2. Apply migrations 037-050 dans l'ordre
for f in migrations/versions/0{37,38,39,40,41,42,43,44,45,46,47,48,49,50}_*.sql; do
  psql $DATABASE_URL -f "$f"
done

# 3. Bootstrap V9
python -m app.saas_factory.self_bootstrap.bootstrap_runner

# 4. Configurer env vars (cf. 11_deployment.md)
# 5. Déployer code V9
# 6. Vérifier /api/v1/health/v9 retourne pass
```

### Hors scope V9 (V10+)

- Distributed circuit breakers (Redis-backed)
- Multi-project per client (claim `project_ids`)
- Magic-link login flow client
- Endpoints `/admin/payments?status=failed` + `/admin/projects/inactive`
- Webhook UBA → n8n pour GDPR
- ESLint v9 config frontend
- Storybook + Playwright frontend tests
- Light theme

### Contributeurs

V9 livrée en collaboration Ahmed Dendani + Claude Opus 4.7
(Anthropic). 22 phases, ~5 mois de développement.

### Licences

- Code : (à définir)
- Stripe SDK : MIT
- FastAPI : MIT
- React : MIT
- n8n : Sustainable Use License

## Voir aussi

- [README hub](./README.md)
- [02 — Master plan](./02_master_plan.md)
- [11 — Deployment](./11_deployment.md)
