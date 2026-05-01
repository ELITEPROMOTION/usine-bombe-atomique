# 02 — Master plan & roadmap

## Phases livrées (V9 complete)

| Phase | Sujet | Tests | LoC | Commit |
|---|---|---|---|---|
| 9-BOOT | Bootstrap platform_config + seed | 58 | +2 970 | `bba1fa1` |
| 9A | Handoff orchestrator + state machine | +44 | +1 809 | `71896b1` |
| 9B | Setup wizard admin (6 steps) | +39 | +1 549 | `7db1b10` |
| 9C | Direct links + validation engine | +49 | +2 827 | `b668e2f` |
| 9D | AI router + cost guard + loop detector | +66 | +2 603 | `9927877` |
| 9E | Intelligence (pricing + qualification + assembly) | +29 | +1 558 | `2c4ef0e` |
| 9F | Client onboarding wizard | +48 | +1 856 | `bcdbdb9` |
| 9G | Infrastructure (Hostinger) | +46 | +2 315 | `8ffc735` |
| 9H | Billing (Stripe, invoices, refunds) | +67 | +2 891 | `6b83ed7` |
| 9I | Legal framework (GDPR Art 6/15/17/20) | +43 | +1 800 | `1cff9e2` |
| 9J | Security enterprise (JWT + RBAC + audit) | +49 | +1 610 | `ec92b4c` |
| 9K | Observability 360° (V9Metrics + SLO + Health + Sentry) | +42 | +1 731 | `fbdc83f` |
| 9L | Resilience + Chaos (CB + Kill switch) | +62 | +2 218 | `6828047` |
| 9M | Dashboard client luxe (frontend) | 0 | +1 964 | `b2ae431` |
| 9M-bis | Backend `/client/*` (12 endpoints + JWT client) | +40 | +2 137 | `0a8af5b` |
| 9N | Admin endpoints + auth | +45 | +2 189 | `f227b0b` |
| 9O | Design system étendu (6 composants + styleguide) | 0 | +812 | `60bb03d` |
| 9P | Consolidation FK + deliverables injection | +22 | +1 082 | `7711c68` |
| 9Q | n8n workflows (6 templates) | 0 | +709 | `f76dbbe` |
| 9R | E2E pipeline tests + bug fix | +9 | +700 | `b8d590a`+`b34b88a` |
| 9S | 22 docs documentaires | 0 | (cette phase) | (à venir) |

**Total** : 22 phases, **758 backend tests verts**, ~32 000 LoC, 25
ADRs.

## Dépendances inter-phases

```
9-BOOT ──┬── 9A ── 9C ── 9R
         ├── 9B
         ├── 9D ── 9E ── 9F ── 9P
         ├── 9G ─────────┘
         ├── 9H ─────────┘
         ├── 9I ─── 9M-bis
         ├── 9J ─── 9M-bis
         ├── 9K
         ├── 9L
         ├── 9N
         ├── 9M ─── 9M-bis ─── 9O ─── 9Q ─── 9S
```

## Critères "Done V9"

- ✅ Coverage critique ≥ 99% / globale ≥ 90%
- ✅ Aucune régression backend cross-phase
- ✅ Conventional commits sur `feature/vague9-bootstrap`
- ✅ ADRs documentés
- ✅ Pas de tag autonome
- ✅ Aucun appel externe payant (Stripe/Hostinger/Anthropic gated)
- ✅ Frontend client câblé sur backend réel

## Hors scope V9 (déféré V10+)

- Distributed circuit breakers (Redis-backed) — V10
- Multi-project per client (claim `project_ids`) — V10
- Magic-link login client — V10
- Endpoints `/admin/payments?status=failed` + `/admin/projects/inactive` — wiring n8n
- Webhook UBA → n8n pour GDPR — wiring 9Q
- ESLint v9 config frontend — maintenance
- Storybook — tooling
- Playwright tests frontend — tooling
- Light theme — design

## Voir aussi

- [01 — Architecture](./01_architecture.md)
- [22 — Release notes V9](./22_release_notes.md)
