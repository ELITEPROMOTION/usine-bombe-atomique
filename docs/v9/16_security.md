# 16 — Security overview

## Modèles d'authentification

### Admin (Phase 9J, ADR-22)

- **JWT HS256** signé avec `JWT_ADMIN_SECRET` (≥ 32 chars).
- Issuer `uba-studio/admin`.
- Roles : `admin` / `viewer` / `auditor` (RBAC).
- TTL par défaut : 60 min.
- **Mode legacy** : `X-Admin-Token: <UBA_ADMIN_TOKEN>` (ADR-17,
  stopgap 9N).

### Client (Phase 9M-bis, ADR-33)

- **JWT HS256** signé avec `JWT_CLIENT_SECRET` (séparé du admin).
- Issuer `uba-studio/client`.
- Claim **`project_id`** scope-bound.
- TTL par défaut : 24h.
- Pas de role : un client = un projet.

### Failure modes

| Cas | Code |
|---|---|
| Aucun secret configuré | 503 |
| Pas d'Authorization header | 401 |
| Token invalide / expired / wrong issuer | 403 |

## Webhooks (Phase 9H)

- Stripe : signature `Stripe-Signature` HMAC-SHA256 avec
  `STRIPE_WEBHOOK_SECRET`.
- Idempotency : table `webhook_events` avec UNIQUE
  `idempotency_key`. Replay → 200 OK silent.

## Audit (Phase 9J, ADR-23)

5 tables append-only avec `BEFORE UPDATE/DELETE` triggers RAISE
EXCEPTION :
- `audit_events` (rétention 7 ans)
- `evidence_ledger` (chain hash)
- `mandates` (eIDAS, durée vie + 7 ans)
- `admin_actions` (toute action override admin)
- `ai_decisions_log` (rétention 3 ans)

## Rate limiting (Phase 9J)

Token bucket in-memory LRU. Limites par défaut :
- 100 req/min par IP sur `/api/v1/*`
- 10 req/min par IP sur `/api/v1/auth/login`

Configurable via env vars (cf. `app.middleware.rate_limiter`).

## Headers sécurité (Phase 9J)

`HeadersMiddleware` ajoute :
- `Strict-Transport-Security: max-age=63072000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'; ...`

## Secrets management

- `app.security.vault_secrets` : chargement secrets depuis env ou
  vault externe (HashiCorp Vault si configuré).
- Aucune secret dans le code source. Tous via env vars.
- `.env*` dans `.gitignore`.

## Live gates (3 garde-fous)

Pour les opérations payantes (Stripe charge, Hostinger provision,
Anthropic call) :
1. **Pydantic** : payload typé avec valeurs validées.
2. **Live gate env var** (`UBA_LIVE_*=1`) : sinon → Stub provider.
3. **Token vérifié** : `STRIPE_API_KEY` etc. checked à init.

## Privacy GDPR

- Email hash SHA-256[:16] avant tout tagging Sentry (ADR-28).
- `_hash_ip` SHA-256 dans `user_consents` pour traçabilité sans PII.
- Erasure (Art 17) anonymise les colonnes PII (cf. [17 GDPR](./17_gdpr.md)).

## Cross-Origin

CORS config dans `app/main.py` :
```python
allow_origins = settings.CORS_ORIGINS    # liste explicite, pas "*"
allow_credentials = True
allow_methods = ["GET", "POST", "PATCH", "DELETE"]
allow_headers = ["Authorization", "Content-Type", "X-Admin-Token"]
```

## Voir aussi

- [17 — GDPR](./17_gdpr.md)
- [13 — Incident response](./13_incident_response.md)
- `docs/V9_PHASE_9J_REPORT.md`
