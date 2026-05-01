# 04 — Backend dev guide

## Setup local

```bash
cd backend/
python -m venv .venv && source .venv/Scripts/activate     # Windows
pip install -r requirements.txt
```

## Variables d'env requises

Voir `.env.example`. Clés critiques V9 :

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN |
| `JWT_ADMIN_SECRET` | Min 32 chars, signe les tokens admin (@phase-9J) |
| `JWT_CLIENT_SECRET` | Min 32 chars, signe les tokens client (@phase-9M-bis) |
| `UBA_LIVE_HOSTINGER` | `1` pour activer Hostinger réel (par défaut OFF) |
| `UBA_LIVE_STRIPE` | `1` pour activer Stripe réel (par défaut OFF) |
| `STRIPE_API_KEY` | seulement si LIVE=1 |
| `HOSTINGER_API_KEY` | seulement si LIVE=1 |
| `ANTHROPIC_API_KEY` | optionnel — sinon stub |
| `OPENAI_API_KEY` | optionnel — fallback |
| `RESEND_API_KEY` | transactional email |
| `SENTRY_DSN` | optionnel (no-op si absent) |

## Lancer le serveur

```bash
uvicorn app.main:app --reload
```

Endpoint health : `GET /api/v1/health`. Documentation OpenAPI :
`/docs`.

## Structure

Cf. [01 — Architecture](./01_architecture.md). Règles clés :

- **Routers** : `app/routers/<topic>.py`, dependencies dans
  `app/routers/admin/dependencies.py` ou `app/routers/client.py`.
- **Domain** : `app/saas_factory/<module>/`, services + types
  + helpers privés (préfixe `_`).
- **Migrations** : `migrations/versions/NNN_<name>.sql`, idempotent
  (CREATE TABLE IF NOT EXISTS), append-only triggers pour audit.
- **Tests** : `tests/saas_factory/test_<module>.py`, mock asyncpg
  via `_make_pool()` pattern (cf. ADR-21).

## Commandes courantes

```bash
# Tests
python -m pytest tests/saas_factory/ -q
python -m pytest tests/saas_factory/test_<module>.py -v

# Coverage
python -m pytest --cov=app/saas_factory tests/saas_factory/ --cov-report=term-missing

# Lint + format
python -m ruff check app/ --fix
python -m bandit -r app/ -ll

# Migrations
psql "$DATABASE_URL" -f migrations/versions/NNN_<name>.sql
```

## Gates qualité (commit accepté seulement si)

- pytest → 100% pass
- ruff → 0 erreur
- bandit `-ll` → 0 issue Medium+
- coverage critique ≥ 99% / globale ≥ 90%

## Patterns à connaître

### `_do_call` no-cover

Les clients prod (Stripe, Hostinger, Anthropic) ont :
```python
def _do_call(self, ...) -> ...: # pragma: no cover
    # appel réel (live mode only)
```
Et un Stub pour les tests offline. Le live gate (`UBA_LIVE_*=1`)
décide quel client est instancié.

### `safeGet` (frontend)

Frontend `client_*.ts` utilise `safeGet(url, fallback)` pour
fallback sur fixtures si backend pas dispo. Cf. ADR-31.

### State machines

`HandoffOrchestrator` (9A), `ProjectStateMachine` (9F) — toujours
async-safe via lock + transitions explicites.

## Voir aussi

- [05 — API reference](./05_api_reference.md)
- [07 — Testing](./07_testing.md)
- [21 — Onboarding](./21_onboarding.md)
