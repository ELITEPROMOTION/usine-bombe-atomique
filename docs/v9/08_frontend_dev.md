# 08 — Frontend dev guide

## Stack

| Tech | Version |
|---|---|
| React | 18.3.1 |
| Vite | 6.0.1 |
| TypeScript | 5.5.4 |
| Tailwind | 3.4.14 |
| Zustand | 5.0.1 (state) |
| axios | 1.7.7 |
| framer-motion | 11.11.17 |
| lucide-react | 0.454.0 (icons) |
| react-router-dom | 6.27.0 |

## Setup

```bash
cd frontend/
npm install
npm run dev          # → http://localhost:5173
npm run build        # production bundle dist/
```

## Structure

```
src/
  api/                    # axios wrappers
    client.ts             # axios instance + interceptors
    client_*.ts           # 9M-bis client area wrappers
    client_fixtures.ts    # mock data (ADR-31)
    {analytics,auth,domains,inbox,osint,projects,tasks,workflows}.ts
  components/
    layout/
      AppShell.tsx        # admin layout
      ClientShell.tsx     # client layout (9M, ADR-32)
      AuthGuard.tsx
    ui/                   # raw components
  design-system/          # tokens + premium components
    tokens.ts
    Button.tsx, Card.tsx, ...
    motion.ts             # 9O presets
  hooks/                  # custom hooks
  pages/
    *.tsx                 # admin pages
    client/*.tsx          # 9M client pages
    StyleguidePage.tsx    # 9O showcase
  stores/                 # Zustand stores
  utils/
  App.tsx                 # router
  main.tsx                # entrypoint
```

## Routes

```tsx
/login              # public
/                   # admin (AppShell)
  /ceo, /ahmed_inbox, /domains, /fleet, ...
  /styleguide       # 9O
/client             # client (ClientShell, 9M)
  /client/deliverables
  /client/payments
  /client/profile
```

## Design system

26 composants exportés depuis `@/design-system` :
- **Layout** : Card, Modal, Sheet (9O)
- **Form** : Button (CSS class `.btn-primary` etc), inputs via `.input` class
- **Feedback** : AlertBanner, HealthDot, Skeleton (9O), Toast (9O)
- **Navigation** : Tabs (9O), Tooltip (9O)
- **Display** : Badge, KPIWidget, Timeline, MilestoneTimeline (9M),
  ProgressGauge (9M), DeliverableCard (9M), InvoicePreview (9M),
  EmptyState (9O)
- **Tokens** : `colors.{ink,gold,success,warn,danger,info,neutral}`,
  `spacing`, `radii`, `shadows`
- **Motion** : `fadeUp`, `fadeIn`, `slideInRight`, `stagger`, `easing`

## Conventions

- **Imports** : `@/...` alias vers `src/...` (Vite config).
- **Couleurs** : utiliser tokens `text-ink-50`, `bg-gold-500/10`, etc.
  Pas de hex hardcodé sauf dans tokens.ts.
- **Animations** : framer-motion pour interactions, Tailwind
  transitions pour state simple (hover, focus).
- **Accessibility** : `role`, `aria-*` sur composants overlay
  (Sheet, Tooltip, Tabs).

## Build & deploy

```bash
npm run build
# dist/ contient l'app statique
# Servir via Nginx (cf. frontend/nginx.conf)
```

## Voir aussi

- [09 — Design system reference](./09_design_system.md)
- [10 — Client area integration](./10_client_area.md)
- `docs/V9_PHASE_9M_REPORT.md` (client dashboard)
- `docs/V9_PHASE_9O_REPORT.md` (design system étendu)
