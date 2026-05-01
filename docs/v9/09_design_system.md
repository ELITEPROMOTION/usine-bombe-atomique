# 09 — Design system reference

## Tokens

### Couleurs (`design-system/tokens.ts`)

```ts
ink:    { 950, 900, 850, 800, 700, 600, 500, 400, 300, 200, 100, 50 }
gold:   { 300: "#e7c05b", 400: "#d9a63c", 500: "#c49129" }
success "#3ecf8e", warn "#f7c948", danger "#ef5b5b", info "#4a90e2"
```

### Typography

- `Inter` (sans), `JetBrains Mono` (mono).
- Sizes : h1 (1.875rem), h2 (1.5rem), h3 (1.125rem), body (0.875rem),
  small (0.75rem), micro (0.6875rem uppercase tracking 0.12em).

### Custom utilities (`index.css`)

| Class | Use |
|---|---|
| `panel` | dark glass panel + shadow + rounded-2xl |
| `panel-inner` | inner panel variation |
| `btn-primary` | premium gold button avec shimmer |
| `btn-outline` | outlined neutral |
| `btn-ghost` | text-only |
| `input` | form input avec focus ring gold |
| `chip-{gold,success,warn,danger,neutral}` | status chips |
| `hairline` | subtle divider |
| `divider` | gradient divider |

## Composants core

### Layout
- `Card` — generic content card
- `Modal` — focus-trapped dialog (existing)
- `Sheet` — drawer lateral (9O)

### Feedback
- `AlertBanner` — page-level alert
- `HealthDot` — colored status indicator
- `Skeleton` / `SkeletonText` (9O) — loading placeholders
- `Toast` / `useToast` / `ToastProvider` (9O) — ephemeral notif

### Navigation
- `Tabs` (9O) — controlled/uncontrolled tabs
- `Tooltip` (9O) — 4-side tooltip avec delay

### Display
- `Badge`, `KPIWidget`, `Timeline`
- `MilestoneTimeline` (9M) — vertical timeline avec icônes par état
- `ProgressGauge` (9M) — SVG circle gauge animé
- `DeliverableCard` (9M) — file card avec download CTA
- `InvoicePreview` (9M) — invoice card avec status chip
- `EmptyState` (9O) — illustration empty avec CTA

### Buttons
- `Button` — base composant React (existant)
- Plus les classes utilitaires `.btn-primary`, `.btn-outline`, `.btn-ghost`

## Motion presets (9O)

```ts
import { fadeUp, fadeIn, slideInRight, stagger, easing } from "@/design-system";

<motion.div variants={fadeUp} initial="hidden" animate="show" />
```

## Showcase

Page `/styleguide` (admin only) montre tous les composants avec
exemples. Source : `frontend/src/pages/StyleguidePage.tsx`.

## Voir aussi

- [08 — Frontend dev](./08_frontend_dev.md)
- `docs/V9_PHASE_9O_REPORT.md`
