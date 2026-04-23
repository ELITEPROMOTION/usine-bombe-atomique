# Dashboard UI/UX Audit - UBA (2026-04-23)

## Stack frontend detecte

- React 18.3.1 + TypeScript 5.5.4
- Vite 6.0.1 (dev + build)
- React Router DOM 6.27
- Tailwind CSS 3.4.14 + custom theme `ink` (dark luxe) + `gold` (champagne)
- Zustand 5.0 (state)
- Axios 1.7 (API)
- Framer Motion 11 (animations)
- Lucide React 0.454 (icons)

## Pages existantes (8)

| Route | Fichier | LOC | Role | Etat |
|---|---|---:|---|---|
| `/login` | LoginPage.tsx | 167 | Auth | OK |
| `/` | DashboardPage.tsx | 119 | Home operator | Basique |
| `/ceo` | CeoPage.tsx | 479 | Executive view | **Riche, mais a etoffer** |
| `/ahmed_inbox` | AhmedInboxPage.tsx | 240 | Boite A/B/C | **A reorganiser 3 colonnes** |
| `/new` | NewProjectPage.tsx | 194 | Creation task | OK |
| `/projects` | ProjectsPage.tsx | 60 | Historique | Minimal |
| `/tasks/:id` | ProgressPage.tsx | 212 | Live task progress | OK |
| `/tasks/:id/results` | ResultsPage.tsx | 219 | Resultats task | OK |

## Composants existants

**Design system partiel** : 3 components seulement
- `ui/Logo.tsx`
- `ui/ScoreRing.tsx`
- `ui/StatusChip.tsx`

**Layout** :
- `AppShell.tsx` : sidebar gauche 64 (desktop only, hidden sur < lg)
- `AuthGuard.tsx` : route guard

## Points faibles identifies

### Navigation
- Sidebar visible seulement desktop (`hidden lg:flex`). Mobile : pas de drawer
- Seulement 5 items navigation : pas de lien vers V5.3/V5.4/V5.5 dashboards
- Pas de top bar (notifications, theme toggle, user menu)

### Design system
- Components manques : Card, Panel, KPIWidget, Badge, HealthDot, Timeline, AlertBanner, Modal, Tooltip
- Pas de tokens structure (couleurs/typo sont dans tailwind.config mais pas exposed comme TS tokens)
- Classes style inline repetees dans chaque page (`panel`, `btn-primary`, etc. - sont en CSS mais non typees)

### Pages manquantes
- **`/observability`** : absent (logs, metrics, traces)
- **`/workflows/live`** : absent alors que backend V5.5 expose `/api/v1/workflows/*`
- **`/cognition/live`** : absent alors que backend V5.4 expose `/api/v1/cognition/*`
- **`/truth/live`** : absent alors que backend V5.3 expose `/api/v1/ctc/*`
- **`/fleet`** : absent (vue multi-entites Dendani)

### Densite info
- CeoPage : 4 KPIs seulement au top, beaucoup de sections mais empilement vertical sans hero
- Pas de streaming temps reel (pas de WebSocket integrations)

### Mobile responsive
- Sidebar `hidden lg:flex` -> mobile sans navigation
- Grilles `md:grid-cols-4` OK mais pas de gestion tablette optimisee
- Tables non scrollables horizontalement sur mobile

### Backend integration
- WebSocket hook absent (`useWebSocket.ts` supprime dans git status : "D frontend/src/hooks/useWebSocket.ts")
- Stores `chatStore` supprime
- Aucune connexion aux endpoints V5.3/V5.4/V5.5

### A11y / perf
- Pas de tests Playwright (`frontend/tests/e2e/` absent)
- Pas d'audit Lighthouse documentd
- Focus states Tailwind classiques (OK)
- Lazy loading non implemente

## Plan de campagne retenu

Focalisation sur les livrables a plus haute valeur Ahmed-CEO :
1. Design system tokens + 8 composants reutilisables
2. `/ceo` enrichi (8 sections dont hero + 12 KPIs + priority queue + live audit stream)
3. AppShell avec nouvelle navigation + drawer mobile
4. 3 nouvelles pages : `/observability`, `/fleet`, `/automation` (live)
5. `useWebSocket` hook universel
6. 5 tests Playwright e2e
7. Build + deploy + smoke tests

Les dashboards V5.3/V5.4 deja live via endpoints REST backend — priorite a consolider.
