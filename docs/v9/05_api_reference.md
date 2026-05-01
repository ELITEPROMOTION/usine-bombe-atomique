# 05 — API reference

OpenAPI spec auto-générée à `/docs` (Swagger UI) et `/redoc`. Ce
doc liste les **groupes d'endpoints** et leur authentification.

## Auth modes

| Header | Mode | Phase |
|---|---|---|
| `Authorization: Bearer <jwt>` (issuer admin) | JWT admin | 9J |
| `Authorization: Bearer <jwt>` (issuer client) | JWT client | 9M-bis |
| `X-Admin-Token: <token>` | Legacy admin (stopgap) | 9N (ADR-17) |

Si **aucune** auth env n'est configurée, les routes admin et client
retournent 503 (fail-closed).

## Groupes

### `/api/v1/auth/*` — Auth admin/login flows
Phase 9J. Login admin, refresh token.

### `/api/v1/admin/*` — Admin dashboard endpoints
Phase 9N + extensions. Projets, paiements, handoffs, ai decisions,
direct links, setup wizard, onboarding.

| Route | Phase |
|---|---|
| `GET /admin/projects` | 9N |
| `POST /admin/projects/:id/notify` | 9N |
| `GET /admin/handoffs` | 9A + 9N |
| `POST /admin/handoffs` | 9A + 9N |
| `POST /admin/handoffs/:id/escalate` | 9A |
| `GET /admin/ai/decisions` | 9D + 9N |
| `GET /admin/direct-links` | 9C + 9N |

### `/api/v1/client/*` — Client area (12 endpoints)
Phase 9M-bis. Auth = JWT client avec claim `project_id`.

| Method | Route | Action |
|---|---|---|
| GET | `/client/project` | Projet du token |
| GET | `/client/milestones` | 5 milestones dérivées |
| GET | `/client/activity?limit=N` | Audit events filtrés |
| GET | `/client/deliverables` | (stub vide en V9) |
| GET | `/client/deliverables/:token/download` | (stub 404) |
| GET | `/client/invoices` | Factures du projet |
| GET | `/client/invoices/:token/pdf` | 302 → pdf_url |
| GET | `/client/handoffs` | Handoffs ouverts/récents |
| GET | `/client/profile` | Profile + consents agrégés |
| PATCH | `/client/profile/consents` | Toggle marketing/analytics |
| POST | `/client/profile/gdpr/export` | 202 + request_id |
| POST | `/client/profile/gdpr/erasure` | 202 + executable_after |

### `/api/v1/health/*` — Health checks
Phase 9K. `/health/v9` agrège platform_config, evidence_chain,
live_modes, jwt_mode.

### `/api/v1/observability/*` — Metrics + SLO catalog
Phase 9K. `/metrics` Prometheus standard, `/observability/slos`
catalogue 9 SLOs.

### Webhooks externes
- `POST /webhooks/stripe` — Phase 9H, signature HMAC-SHA256, idempotent.

## Codes d'erreur communs

| Code | Sens |
|---|---|
| 200 | OK |
| 202 | Accepted (GDPR async) |
| 302 | Redirect (PDF, signed URLs) |
| 401 | Auth absente |
| 403 | Token invalide / role insuffisant |
| 404 | Ressource introuvable |
| 409 | Conflict (idempotency, état incompatible) |
| 422 | Validation Pydantic échouée |
| 503 | Auth non configurée (fail-closed) |

## Voir aussi

- [04 — Backend dev](./04_backend_dev.md)
- [16 — Security](./16_security.md)
- `docs/V9_PHASE_9N_REPORT.md` (admin endpoints détails)
- `docs/V9_PHASE_9M_BIS_REPORT.md` (client endpoints détails)
