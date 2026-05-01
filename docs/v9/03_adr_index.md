# 03 — ADR index

Toutes les décisions d'architecture V9 sont consignées dans
`docs/V9_ARCHITECTURE_DECISIONS.md`. Ce doc est l'index navigable.

## Liste des ADRs

| # | Date | Phase | Sujet |
|---|---|---|---|
| 07 | 2026-04 | 9-BOOT | platform_config singleton id=1 |
| 08 | 2026-04 | 9A | Handoff state machine |
| 09 | 2026-04 | 9B | Setup wizard 6 steps fixes |
| 10 | 2026-04 | 9C | Direct link token format (hex 32 + SHA256 lookup) |
| 11 | 2026-04 | 9D | AIRouter fallback strategy |
| 12 | 2026-04 | 9D | CostGuard 3-niveau (call/project/daily) |
| 13 | 2026-04 | 9E | Pricing — Maghreb floor / North Europe ceiling |
| 14 | 2026-04 | 9F | Onboarding 6 steps fixes |
| 15 | 2026-04 | 9F | FK rétroactives reportées en 9P |
| 16 | 2026-04 | 9G | Hostinger client `_do_call` no-cover |
| 17 | 2026-04 | 9N | Token legacy `X-Admin-Token` (stopgap) |
| 18 | 2026-04 | 9H | Stripe checkout idempotent par session_id |
| 19 | 2026-04 | 9H | Token IA invisibles dans factures (8 termes interdits) |
| 20 | 2026-04 | 9H | Webhook idempotency via `idempotency_key UNIQUE` |
| 21 | 2026-04 | 9R | E2E tests no real DB, mock pool sequenced |
| 22 | 2026-04 | 9J | JWT admin + RBAC roles (admin/viewer/auditor) |
| 23 | 2026-04 | 9J | Audit triggers append-only (BEFORE UPDATE/DELETE) |
| 24 | 2026-04 | 9P | FK rétroactives data-aware (cleanup orphans first) |
| 25 | 2026-04 | 9I | GDPR strict for all countries (no per-country detection) |
| 26 | 2026-04 | 9I | Erasure preserves audit trail (Art 17§3) |
| 27 | 2026-04 | 9K | Prometheus CollectorRegistry injectable |
| 28 | 2026-04 | 9K | Sentry no-op gracieux |
| 29 | 2026-04 | 9L | CircuitBreaker async-first state machine |
| 30 | 2026-04 | 9L | Chaos engineering offline-only avec gate env |
| 31 | 2026-05 | 9M | Mock data layer single-file fixtures |
| 32 | 2026-05 | 9M | Route segregation client/admin via shells distincts |
| 33 | 2026-05 | 9M-bis | JWT client séparé avec claim `project_id` |
| 34 | 2026-05 | 9Q | n8n self-hosted vs scheduler interne |

## Comment lire un ADR

Format léger :
- **Contexte** : pourquoi la décision était nécessaire
- **Décision** : ce qui a été retenu
- **Justifications** : pourquoi cette option vs alternatives
- **Conséquences** : ce qui change pour le code / process / ops

## Comment ajouter un ADR

1. Append au fichier `docs/V9_ARCHITECTURE_DECISIONS.md` avec
   `## ADR-NN — <titre>`
2. Mettre à jour cette table d'index
3. Référencer l'ADR depuis le phase report concerné
