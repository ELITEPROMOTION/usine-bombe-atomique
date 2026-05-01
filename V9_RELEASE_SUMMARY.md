# V9 ULTIMATE — Release Summary

**Tag** : `v9.0.0-rc1`
**Date** : 2026-05-01
**Statut** : Release Candidate 1 — production-ready, en attente de déploiement staging.

---

## Repo & release

| | |
|---|---|
| Repository | https://github.com/ELITEPROMOTION/usine-bombe-atomique |
| Release tag | https://github.com/ELITEPROMOTION/usine-bombe-atomique/releases/tag/v9.0.0-rc1 |
| Branche `main` | commit `6712a31` (merge V9) |
| Branche `feature/vague9-bootstrap` | pushée pour archive |

---

## Stats finales

| Indicateur | Valeur |
|---|---|
| Phases livrées | **22** (9-BOOT, 9A→9S + 9M-bis) |
| Tests backend | **758 verts** |
| Coverage globale | **98%** |
| LoC backend | ~32 000 |
| LoC frontend | ~4 200 |
| Migrations SQL | 50 (001 → 050) |
| ADRs | 28 (ADR-07 → ADR-34) |
| Phase reports | 22 (`docs/V9_PHASE_9*_REPORT.md`) |
| Hub docs | 22 (`docs/v9/`) |
| Workflows n8n | 6 (`automation/n8n/`) |
| Endpoints admin | 25+ |
| Endpoints client | 12 (`/api/v1/client/*`) |
| Métriques Prometheus | 16 |
| SLOs | 9 |
| Composants design system | 30+ |
| Régressions cross-phase | 0 |
| Appels externes payants en CI | 0 (Stripe/Hostinger/Anthropic gated) |

---

## 22 phases livrées

| Phase | Sujet | Commit |
|---|---|---|
| 9-BOOT | Bootstrap platform_config + seed | `bba1fa1` |
| 9A | Handoff orchestrator + state machine | `71896b1` |
| 9B | Setup wizard admin (6 steps) | `7db1b10` |
| 9C | Direct links + validation engine | `b668e2f` |
| 9D | AI router + cost guard + loop detector | `9927877` |
| 9E | Intelligence (pricing + qualification + assembly) | `2c4ef0e` |
| 9F | Client onboarding wizard | `bcdbdb9` |
| 9G | Infrastructure (Hostinger gated) | `8ffc735` |
| 9H | Billing (Stripe + 50+ TVA + invoices) | `6b83ed7` |
| 9I | Legal Framework (GDPR Art 6/15/17/20) | `1cff9e2` |
| 9J | Sécurité Enterprise (JWT + RBAC + audit) | `ec92b4c` |
| 9K | Observabilité 360° (V9Metrics + SLO + Health + Sentry) | `fbdc83f` |
| 9L | Resilience + Chaos (CB + Kill switch) | `6828047` |
| 9M | Dashboard client luxe (frontend) | `b2ae431` |
| 9M-bis | Backend `/client/*` (12 endpoints + JWT client) | `0a8af5b` |
| 9N | Admin endpoints + dual-mode auth | `f227b0b` |
| 9O | Design System Luxe étendu | `60bb03d` |
| 9P | Consolidation FK + deliverables injection | `7711c68` |
| 9Q | n8n workflows (6 templates) | `f76dbbe` |
| 9R | E2E pipeline tests + bug fix | `b8d590a` + `b34b88a` |
| 9S | 22 docs hub | `d23fd85` |
| **Merge V9** | (sur `main`) | **`6712a31`** |

---

## Checklist déploiement staging

### Pre-deploy
- [ ] DNS staging configuré (`api-staging.<domain>`, `app-staging.<domain>`)
- [ ] Postgres staging provisionné, accessible depuis l'API
- [ ] Redis staging provisionné (rate limiter + n8n queue)
- [ ] Secrets générés et stockés dans le secret manager :
  - [ ] `DATABASE_URL`
  - [ ] `JWT_ADMIN_SECRET` (≥ 32 chars random)
  - [ ] `JWT_CLIENT_SECRET` (≥ 32 chars random, distinct du admin)
  - [ ] `STRIPE_API_KEY` (test mode en staging)
  - [ ] `STRIPE_WEBHOOK_SECRET`
  - [ ] `RESEND_API_KEY`
  - [ ] `SENTRY_DSN` (optionnel mais recommandé)
- [ ] `UBA_LIVE_HOSTINGER=0` confirmé (pas de prod call en staging)
- [ ] `UBA_LIVE_STRIPE=0` confirmé (sandbox uniquement)
- [ ] `UBA_CHAOS_ENABLED` **NON défini** (jamais en prod)

### Database
- [ ] Backup pré-déploiement (`pg_dump`)
- [ ] Migrations appliquées dans l'ordre `001` → `050`
- [ ] Bootstrap V9-BOOT exécuté (`platform_config` row id=1 présent)
- [ ] Vérification : `SELECT version FROM platform_config WHERE id=1` retourne row

### Code deploy
- [ ] Backend image buildée depuis tag `v9.0.0-rc1`
- [ ] Frontend bundle Vite build OK (`dist/`)
- [ ] Nginx config servant `dist/` + reverse-proxy vers FastAPI
- [ ] Health check post-deploy : `GET /api/v1/health/v9` → `status: pass`
- [ ] Sub-checks : `platform_config: pass`, `evidence_chain: pass|warn`, `live_modes: pass` (tout OFF en staging), `jwt_mode: pass`

### n8n (Phase 9Q)
- [ ] n8n self-hosted déployé sur VPS séparé
- [ ] Variables d'env configurées (8 vars : `UBA_API_BASE`, `UBA_ADMIN_TOKEN`, `RESEND_API_KEY`, `SLACK_WEBHOOK_*`, `DPO_EMAIL`)
- [ ] 6 workflows importés depuis `automation/n8n/*.json`
- [ ] Workflows désactivés par défaut, à activer après vérification staging

### Tests post-deploy staging
- [ ] Smoke test API : `curl /api/v1/health/v9` → 200
- [ ] Smoke test frontend : `https://app-staging.../login` charge
- [ ] Login admin avec un JWT généré : `curl -H "Authorization: Bearer ..." /admin/projects` → 200
- [ ] Login client avec JWT client : `curl -H "Authorization: Bearer ..." /client/project` → 200
- [ ] Webhook Stripe test : envoyer un event sandbox → vérifier idempotency
- [ ] Sentry reçoit les events (si configuré)
- [ ] Prometheus scrape `/metrics` OK

### Soak (24h)
- [ ] Aucune erreur Sentry critique
- [ ] SLO `webhook_handler_success` ≥ 99.99% sur 24h
- [ ] SLO `ai_router_availability` ≥ 99.9% sur 24h
- [ ] Pas de circuit breaker en OPEN persistant
- [ ] DB pool jamais saturé (`pg_stat_activity` < 80% max)

### Promotion staging → prod (après validation soak)
- [ ] Documentation de la release sur GitHub Releases (UI)
- [ ] Re-tag `v9.0.0` (production) depuis `v9.0.0-rc1` si soak OK
- [ ] Switch `UBA_LIVE_HOSTINGER=1` + `UBA_LIVE_STRIPE=1` en prod
- [ ] Activer les 6 workflows n8n manuellement
- [ ] Annonce client via email + landing page

---

## Documentation

- **Hub** : [`docs/v9/README.md`](docs/v9/README.md)
- **Onboarding nouveau dev** : [`docs/v9/21_onboarding.md`](docs/v9/21_onboarding.md)
- **Release notes V9** : [`docs/v9/22_release_notes.md`](docs/v9/22_release_notes.md)
- **Deployment runbook** : [`docs/v9/11_deployment.md`](docs/v9/11_deployment.md)
- **Incident response** : [`docs/v9/13_incident_response.md`](docs/v9/13_incident_response.md)
- **ADR index** : [`docs/v9/03_adr_index.md`](docs/v9/03_adr_index.md)

---

## Limitations connues V9 (à traiter V10+)

- Distributed circuit breakers (Redis-backed)
- Multi-project per client (claim `project_ids`)
- Magic-link login flow client
- Endpoints `/admin/payments?status=failed` + `/admin/projects/inactive` (workflows n8n 04+06)
- Webhook UBA → n8n pour `gdpr.request_submitted` (workflow n8n 03)
- ESLint v9 config frontend
- Storybook + Playwright tests
- Light theme

Cf. [`docs/v9/02_master_plan.md`](docs/v9/02_master_plan.md) section "Hors scope V9".

---

V9 ULTIMATE — UBA Studio Platform — production-ready.
