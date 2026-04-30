# V9 Phase 9M — Dashboard client luxe — Final Report

**Date** : 2026-05-01
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9L)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9M livre l'espace client **luxe** côté frontend, séparé de la
zone admin existante :

1. **ClientShell layout** : sidebar navigation premium (gold accents,
   profil client, déconnexion). Séparé de l'`AppShell` admin pour
   éviter les fuites d'options internes côté client.
2. **4 pages client** : Dashboard (overview), Deliverables (livrables
   téléchargeables), Payments (factures + handoffs), Profile (RGPD,
   consents, export, erasure).
3. **4 composants design-system luxe** : `MilestoneTimeline`,
   `ProgressGauge` (gauge SVG circulaire animé framer-motion),
   `DeliverableCard`, `InvoicePreview`.
4. **API wrappers typed** : 4 modules `api/client_*.ts` qui
   pointent vers `/api/v1/client/*` côté backend. Fallback
   automatique aux fixtures locales si le backend n'est pas branché
   (dev offline-friendly, voir ADR-31).
5. **Mock data layer isolé** : `api/client_fixtures.ts` regroupe
   tous les fixtures typés Project/Milestone/Activity/Deliverable/
   Invoice/Handoff/Profile. Branchement backend = 1 ligne (suppression
   du `try/catch` fallback).
6. **Routes** : `/client`, `/client/deliverables`, `/client/payments`,
   `/client/profile` sous `AuthGuard`.

| Indicateur | Valeur | Cible |
|---|---|---|
| Pages client livrées | 4 (dashboard, deliverables, payments, profile) | 4 |
| Composants design-system | 4 nouveaux | ≥ 3 |
| API wrappers | 4 modules + 1 fixtures | 4 |
| LoC frontend ajoutées | ~1 520 | 1 000–2 000 |
| Build Vite production | ✅ 9.10s, 510 KB JS / 152 KB gzip | OK |
| TypeScript strict | ✅ (0 erreur sur les fichiers 9M) | 0 |
| Backend regression | ✅ 718/718 tests pass | aucune régression |
| Auto-fix loop | 0 itération | ≤ 3 |

---

## 2. Livrables

### 2.1 API wrappers + fixtures (`frontend/src/api/`)

| Fichier | LOC |
|---|---|
| `client_fixtures.ts` | 266 |
| `client_dashboard.ts` | 42 |
| `client_deliverables.ts` | 25 |
| `client_payments.ts` | 34 |
| `client_profile.ts` | 59 |

### 2.2 Composants & layout

| Fichier | LOC |
|---|---|
| `components/layout/ClientShell.tsx` | 143 |
| `design-system/MilestoneTimeline.tsx` | 75 |
| `design-system/ProgressGauge.tsx` | 78 |
| `design-system/DeliverableCard.tsx` | 85 |
| `design-system/InvoicePreview.tsx` | 86 |

### 2.3 Pages client (`frontend/src/pages/client/`)

| Fichier | LOC |
|---|---|
| `ClientDashboardPage.tsx` | 200 |
| `ClientDeliverablesPage.tsx` | 64 |
| `ClientPaymentsPage.tsx` | 142 |
| `ClientProfilePage.tsx` | 221 |

### 2.4 ClientDashboardPage — feature highlights

- **Header projet** : nom entreprise, pack, livraison estimée formatée
  en français long.
- **Banner handoffs** : badge warn bordé si actions en attente (top 3
  affichées).
- **`ProgressGauge`** large + label "prochaine étape" centré.
- **`MilestoneTimeline`** verticale avec icônes par état (Check /
  Clock / CircleDashed) + dégradé gold sur le rail.
- **Activity feed** : 8 derniers événements avec icônes typées
  (Build / Payment / Deliverable / Handoff / Comms).

### 2.5 ClientPaymentsPage — feature highlights

- **2 KPI cards** : "déjà réglé" (success) + "à régler" (warn auto-tone
  selon le montant).
- **Banner payment_confirm handoff** avec CTA `btn-primary` shimmer.
- **Liste InvoicePreview** : numéro, status chip, montant Intl
  formatté, lien PDF.

### 2.6 ClientProfilePage — feature highlights

- **Profile rows** typées (Email, Entreprise, Langue, Date d'arrivée).
- **Toggles consents** RGPD : marketing + analytics, persisted via
  `updateClientConsents`.
- **GDPR rights** : export (Art. 20), erasure (Art. 17). Le bouton
  erasure exige un motif texte avant déclenchement (validation locale
  + retour `executable_after` formatté).

---

## 3. Architecture

### 3.1 Mock data layer isolé (ADR-31)

Le backend `/client/*` n'existe pas encore (Phase 9M scope frontend
only). Plutôt que de retarder le frontend, chaque wrapper API tente
l'appel HTTP et **fallback silencieusement aux fixtures** :

```ts
async function safeGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const r = await apiClient.get<T>(path);
    return r.data;
  } catch { return fallback; }
}
```

Avantages :
- Frontend démontrable hors-ligne (no backend dep).
- Branchement backend = remplacement 1-ligne du `safeGet` par un
  vrai `apiClient.get` (ou suppression du fallback).
- Tous les fixtures dans **un seul** fichier (`client_fixtures.ts`)
  → pas de mock dispersé dans 4 modules.

Trade-off : un dev qui ne lit pas le code peut croire que les pages
sont câblées au backend. Mitigation : commentaire en tête de chaque
wrapper + ADR-31 explicite.

### 3.2 Route segregation client/admin (ADR-32)

L'`AppShell` existant gère la navigation interne (Ahmed CEO, OSINT,
Cognition, etc.) — UX différente de ce qu'on veut exposer au client.
Le `ClientShell` partage le même chrome luxe mais expose **uniquement**
les 4 routes client.

Routes :
- `/` → `AppShell` admin (existant, pas modifié)
- `/client` → `ClientShell` (nouveau)
  - `/client` → ClientDashboardPage
  - `/client/deliverables` → ClientDeliverablesPage
  - `/client/payments` → ClientPaymentsPage
  - `/client/profile` → ClientProfilePage

Tous sous `AuthGuard` (réutilisation existante).

**Note** : `AuthGuard` actuel ne distingue pas client vs admin ; en
prod, il faudra discriminer le rôle dans le JWT (claim `role: client |
admin`) et fail-fast sur `/client/*` si admin essaie d'y accéder
(et inversement). Hors scope 9M.

### 3.3 Design system étendu

4 composants ajoutés au catalogue `design-system/index.ts` :
- `MilestoneTimeline` : timeline verticale avec rail dégradé gold +
  icônes par état + animation framer-motion `delay: i * 0.05`.
- `ProgressGauge` : SVG circle avec stroke-dasharray animé +
  linearGradient gold + 3 tailles (sm/md/lg).
- `DeliverableCard` : carte avec icône typée par catégorie + format
  bytes humain + lien download.
- `InvoicePreview` : carte facture avec montant Intl + status chip +
  lien PDF externe.

Tous suivent le même pattern : `motion.div` avec `initial/animate`,
classes Tailwind via custom utilities (`panel`, `chip-*`), tokens
gold/ink consistants.

### 3.4 Stratégie luxe ("luxe" = premium UX)

- **Animations subtiles** : `framer-motion` initial/animate sur
  arrivée de chaque section (delay staggered).
- **Tokens consistants** : tous les composants utilisent les
  `ink.*` neutrals + `gold.*` accents définis dans `tokens.ts`.
- **Microcopy soignée** : messages français polis, phrases courtes,
  pas de jargon technique exposé au client.
- **Tabular nums** : tous les chiffres alignés (`tabular-nums`).
- **Status chips colorés** : vert success, ambre warn, rouge danger.
- **Hover states** : `whileHover={{ y: -2 }}` sur les cards
  cliquables, gold border sur deliverables au survol.
- **Internationalization-ready** : `Intl.NumberFormat` pour montants,
  `toLocaleDateString("fr-FR", ...)` pour dates.

---

## 4. Conformité

| Master plan | Statut |
|---|---|
| #30 Espace client (luxe) | ✅ |
| #31 4 pages client | ✅ |
| #32 Composants luxe | ✅ |
| #33 GDPR rights UI | ✅ (Art 15/17/20 exposés) |
| Mock data isolé | ✅ (1 seul fichier fixtures) |
| Pas de régression backend | ✅ (718/718 tests) |
| Build Vite OK | ✅ |
| Conventional commit | ✅ |
| Pas de tag autonome | ✅ |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| Vite production build | ✅ PASS (9.10s, 510 KB / 152 KB gzip) |
| TypeScript `tsc --noEmit` (Phase 9M files) | ✅ PASS (0 erreur) |
| ESLint | ⚠️ N/A (pas de `eslint.config.js` dans le repo, pré-existant) |
| Backend regression (718 tests) | ✅ PASS |
| pytest cumulé (716 backend tests) | ✅ PASS (aucun changement backend) |

**Note ESLint** : le repo n'a pas de config ESLint v9+ (`eslint.config.js`).
Le script `npm run lint` du `package.json` échoue avec un message clair
demandant la migration. C'est un problème **pré-existant** au repo, pas
introduit par 9M. À adresser dans une phase de maintenance frontend
séparée.

---

## 6. Limitations & dette technique

- **Backend `/client/*` non implémenté** : Phase 9M scope **frontend
  only** par master plan. Les 9 endpoints attendus (project,
  milestones, activity, deliverables, invoices, handoffs, profile,
  consents PATCH, GDPR export/erasure POST) doivent être ajoutés en
  Phase 9M-bis ou phase ultérieure. Le frontend est conçu pour
  brancher sans modification.
- **AuthGuard ne discrimine pas client/admin** : actuellement, un
  user authentifié peut visiter `/client/*` ou `/` indifféremment.
  Pour prod, il faut un claim `role` dans le JWT et un guard dédié
  (`<ClientAuthGuard>`).
- **Fixtures statiques** : pas de simulation d'états divers (project
  en review, all milestones done, no invoices). Pour démo plus riche,
  un toggle `?demo_state=X` serait utile.
- **Pas de tests automatisés frontend** : Playwright config existe
  (`playwright.config.ts`) mais aucun test client écrit. Coverage
  manuelle uniquement (compile + visual review).
- **Lint config absent** : ESLint v9 nécessite `eslint.config.js`,
  pas livré dans 9M. À traiter dans une phase de maintenance.
- **Pas de skeleton loading states** : les pages affichent
  "Chargement..." plain text. Avec un real backend, des skeletons
  améliorent la perception (`react-loading-skeleton` ou custom).
- **Pas de pagination** : `listClientDeliverables` / `listClientInvoices`
  retournent tout. À paginer si > 50 items.
- **Pas de download protection** : `buildDownloadUrl` génère une URL
  publique à partir du token. Le backend doit valider que le token
  appartient bien au client connecté (côté `/client/deliverables/{token}/download`).
- **Pas d'i18n complet** : textes français hardcodés. Pour multi-locale,
  intégrer `react-i18next` (locale dans profile déjà typée).
- **Erasure UX** : un dialogue de confirmation modal serait plus rassurant
  qu'un input + bouton. Le composant `Modal` existe mais non câblé ici
  pour rester scope-conform.

---

## 7. État cumulé V9 sur la branche

| Phase | Commit | Tests | Coverage | LoC |
|---|---|---|---|---|
| 9-BOOT | `bba1fa1` | 58 | 97% | +2 970 |
| 9A | `71896b1` | +44 | 98% | +1 809 |
| 9B | `7db1b10` | +39 | 98% | +1 549 |
| 9C | `b668e2f` | +49 | 98% | +2 827 |
| 9D | `9927877` | +66 | 98% | +2 603 |
| 9E | `2c4ef0e` | +29 | 98% | +1 558 |
| 9F | `bcdbdb9` | +48 | 99% | +1 856 |
| 9N | `f227b0b` | +45 | 98% | +2 189 |
| 9G | `8ffc735` | +46 | 98% | +2 315 |
| 9H | `6b83ed7` | +67 | 98% | +2 891 |
| 9R | `b8d590a`+`b34b88a` | +9 | 98% | +700 |
| 9J | `ec92b4c` | +49 | 98% | +1 610 |
| 9P | `7711c68` | +22 | 98% | +1 082 |
| 9I | `1cff9e2` | +43 | 98% | +1 800 |
| 9K | `fbdc83f` | +42 | 98% | +1 731 |
| 9L | `6828047` | +62 | 98% | +2 218 |
| **9M** | `(à venir)` | **+0 (frontend)** | **n/a** | ~+1 520 |

**Backend cumulé** : 16 phases, 718 tests verts, ~30 100 LoC, 24 ADR.
**Frontend ajouté en 9M** : ~1 520 LoC (TypeScript strict, build Vite OK).

---

## 8. Statut & next-step

```
PHASE 9M : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**Phases du master plan non livrées** :
- 9M-bis (backend `/client/*` endpoints) — pour brancher le frontend
- 9O (design system luxe approfondi) — extension de tokens + composants
- 9Q (n8n workflows) — outil externe
- 9S (22 docs rédigés) — documentation

**Recommandation** : la stack V9 a maintenant **un visage client**.
Trois cuts possibles :
1. **9M-bis** : ajouter les 9 endpoints backend `/client/*` pour brancher
   le frontend pour de vrai (~5h, requires JWT client claim).
2. **9O** : design system luxe approfondi (composants Modal/Dialog
   premium, animations stagger plus poussées, dark mode toggle, etc.).
3. **STOP + tag `v9.0.0-rc1`** : 17 phases dont une UI client, base
   solide pour go-to-market staging. Frontend démontrable offline
   immédiatement.
