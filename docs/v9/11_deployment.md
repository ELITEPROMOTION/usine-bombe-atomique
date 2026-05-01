# 11 — Deployment runbook

## Topologie cible (V9 production-ready)

```
                ┌──────────────┐
   internet → ──┤    Nginx      ├── /static (frontend dist/)
                └──────┬───────┘
                       │
            ┌──────────┴────────────┐
            ▼                        ▼
       ┌─────────┐            ┌──────────┐
       │ FastAPI │            │  n8n     │
       │ uvicorn │            │ workers  │
       └────┬────┘            └────┬─────┘
            │                       │
            ▼                       ▼
       ┌─────────┐            ┌─────────┐
       │Postgres │            │  Redis  │ (rate limiter, n8n queue)
       └─────────┘            └─────────┘
```

## Pré-requis env (prod)

| Var | Valeur attendue |
|---|---|
| `DATABASE_URL` | Postgres DSN (managed RDS / DigitalOcean) |
| `JWT_ADMIN_SECRET` | 64 chars random (rotate annuel) |
| `JWT_CLIENT_SECRET` | 64 chars random (rotate mensuel) |
| `UBA_LIVE_HOSTINGER` | `1` en prod, `0` en staging |
| `UBA_LIVE_STRIPE` | `1` en prod, `0` en staging |
| `STRIPE_API_KEY` | live key |
| `STRIPE_WEBHOOK_SECRET` | whsec_... |
| `HOSTINGER_API_KEY` | live key |
| `RESEND_API_KEY` | re_... |
| `SENTRY_DSN` | optionnel mais recommandé en prod |
| `UBA_CHAOS_ENABLED` | **NEVER `1`** en prod (cf. ADR-30) |
| `UBA_KILL_*` | OFF par défaut, à toggler en cas d'incident |

## Procédure de déploiement

### 1. Préparer le bundle

```bash
# Backend
cd backend/
python -m pytest tests/saas_factory/   # 758 tests pass
python -m ruff check app/
python -m bandit -r app/ -ll

# Frontend
cd ../frontend/
npm run build                          # dist/ ready
```

### 2. Migrations

```bash
# Apply migrations dans l'ordre
for f in migrations/versions/*.sql; do
  psql "$DATABASE_URL" -f "$f"
done
```

⚠ **Migration 049** (FK rétroactives) requiert un cleanup data
préalable. Vérifier les rows orphelines avant en staging.

### 3. Bootstrap V9-BOOT (une seule fois)

```python
# Seed platform_config singleton id=1
python -m app.saas_factory.self_bootstrap.bootstrap_runner
```

### 4. Déploiement code

Stratégie blue/green :
1. Déployer backend sur slot blue
2. Run health checks (`GET /api/v1/health/v9` → status pass)
3. Switch traffic Nginx
4. Stop slot green ancien

### 5. Active n8n workflows (Phase 9Q)

Import les 6 workflows JSON depuis `automation/n8n/`. Vérifier les
env vars (RESEND_API_KEY, SLACK_WEBHOOK_*, UBA_API_BASE,
UBA_ADMIN_TOKEN). **Activer manuellement** chaque workflow.

## Health checks post-deploy

```bash
curl https://api.ubastudio.io/api/v1/health/v9 | jq

# Attendu :
# status: "pass"
# checks: {
#   platform_config: "pass",
#   evidence_chain: "pass",  # ou "warn" si <5 maillons
#   live_modes: "warn",       # OK car prod = ON
#   jwt_mode: "pass"
# }
```

## Rollback

Stratégie : revert au commit précédent + redéploiement (~5min).

⚠ **Migrations** ne sont pas rollbackables automatiquement. Si une
migration cause un incident :
1. Revert le code à la version pré-migration.
2. Lancer un script `down` manuel si la migration est destructive
   (rare en V9 — toutes les migrations 9 sont additives).

## Monitoring post-deploy

- Sentry : `SENTRY_DSN` configuré, vérifier 0 erreur dans les 5min.
- Prometheus : `/metrics` scrapé par Grafana.
- SLO `webhook_handler_success` ≥ 99.99% sur 30d.
- SLO `ai_router_availability` ≥ 99.9% sur 7d.

## Voir aussi

- [12 — Admin runbook](./12_admin_runbook.md)
- [13 — Incident response](./13_incident_response.md)
- [14 — Observability](./14_observability.md)
