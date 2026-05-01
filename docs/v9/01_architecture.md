# 01 — Architecture overview

## Stack

| Couche | Tech | Notes |
|---|---|---|
| Backend | FastAPI + asyncpg + Pydantic v2 | Python 3.12 |
| DB | PostgreSQL 15+ | JSONB, gen_random_uuid, UUID natif |
| Frontend | React 18 + Vite + TypeScript + Tailwind | Zustand pour state, framer-motion pour anim |
| Auth | JWT HS256 (jose) | Deux secrets : admin + client (@phase-9J + 9M-bis, ADR-22 + ADR-33) |
| Observability | Prometheus + (optionnel) Sentry | @phase-9K, ADR-27/28 |
| Resilience | CircuitBreaker async + KillSwitch + Chaos | @phase-9L, ADR-29/30 |
| Automation | n8n self-hosted | @phase-9Q, ADR-34 |
| Payment | Stripe (gated) | @phase-9H |
| Infra | Hostinger (gated) | @phase-9G |
| AI | Claude (Anthropic) + OpenAI fallback | @phase-9D |

## Layered structure (backend)

```
app/
  routers/        # FastAPI endpoints (admin/* + client.py + ...)
  saas_factory/   # Domain modules
    ai_orchestrator/    # 9D — router + cost guard + loop detector
    billing/             # 9H — Stripe + invoices + paywall
    chaos/               # 9L — failure injection (offline)
    client_area/         # 9M-bis — services pour /client/*
    client_onboarding/   # 9F — wizard 6-steps
    deliverables/        # 9P — link injector
    direct_links/        # 9C — token + validation
    handoff/             # 9A — orchestrator + state machine
    infrastructure/      # 9G — Hostinger / DNS / VPS / SSL / Backup
    intelligence/        # 9E — pricing + qualification + assembly
    legal/               # 9I — GDPR Art 6/15/17/20
    observability/       # 9K — V9Metrics + SLOs + HealthCheck
    resilience/          # 9L — CircuitBreaker + Timeout + KillSwitch
    self_bootstrap/      # 9-BOOT — platform_config seed
    setup_wizard/        # 9B — admin wizard
  security/        # JWT admin/client, rate_limiter, headers, vault
  saas_factory/     # cf. ci-dessus
migrations/versions/    # 50+ SQL migrations (001 — 050)
tests/saas_factory/     # 758 tests (98% coverage)
```

## Data flow critique : nouveau projet

```
Client                 Frontend           Backend                       Stripe
  |                      |                  |                             |
  |--- /client/onboard ->|                  |                             |
  |                      |--- POST /onboarding/submit -------------->     |
  |                      |                  | (qualification 9E)          |
  |                      |                  | (pricing 9E)                 |
  |                      |                  | (assembly 9E)                |
  |                      |                  | (paywall_pending status)     |
  |                      |<-- checkout URL -|                             |
  |                      |                  |                             |
  |--- pay -----------------------------------------------------> session |
  |                                         |<-- webhook checkout.completed|
  |                                         | (idempotent INSERT 9H)      |
  |                                         | (project -> in_production)  |
  |                                         | (provisioning 9G — gated)   |
```

## Cross-cutting concerns

| Concern | Modules | Phase |
|---|---|---|
| Audit trail | `audit_events`, `evidence_ledger` | 9-BOOT, append-only |
| Idempotency | webhook_events, ON CONFLICT clauses | 9H, 9R |
| Rate limiting | `app.middleware.rate_limiter` | 9J |
| Resilience | `resilience.CircuitBreaker` | 9L |
| Observability | `V9Metrics` + Sentry | 9K |
| GDPR | `legal.{ConsentManager,GDPRExporter,GDPREraser}` | 9I |

## Voir aussi

- [02 — Master plan](./02_master_plan.md)
- [03 — ADR index](./03_adr_index.md)
- `docs/V9_PHASE_9-BOOT_REPORT.md` (bootstrap initial)
