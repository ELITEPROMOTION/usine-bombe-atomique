# V9 Temporary Hosting Playbook — Fly.io (free, sans carte de crédit)

**Objectif** : valider V9 en conditions réelles **sans achat** avant
de provisionner le VPS définitif.

**Plateforme retenue** : **Fly.io** (Render exigeait carte → switch).

**Free allowance Fly.io** :
- 3 shared-cpu-1x VMs (256MB RAM chacune)
- 3GB volume storage total
- 160GB outbound bandwidth/mois
- Postgres dev single-node 256MB
- **0 carte de crédit requise** au signup (signup email + GitHub OAuth)

---

## Architecture déploiement

```
┌────────────────────────┐    ┌──────────────────────────┐
│ uba-staging-app.fly.dev│    │uba-staging-api.fly.dev   │
│ Frontend (Nginx serve  │───▶│ Backend (FastAPI uvicorn │
│ Vite dist + proxy /api)│    │ Docker)                  │
│ 256MB RAM / shared-cpu │    │ 256MB RAM / shared-cpu   │
└────────────────────────┘    └────────────┬─────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ uba-staging-db (Postgres)│
                              │ 256MB single-node        │
                              └──────────────────────────┘
```

3 apps Fly = pile poil dans la free allowance (3 VMs).

---

## Limite honnête de cette session

Je ne peux **pas** :
- Installer flyctl sur ta machine (binaire Windows téléchargé/exécuté toi)
- `flyctl auth login` (browser OAuth interactif)
- Voir les URLs publiques générées (uniquement dans ton dashboard Fly)

Je **peux** :
- Configs prêtes à l'emploi (`fly_backend.toml`, `fly_frontend.toml`,
  `frontend/Dockerfile.fly`, `frontend/nginx.fly.conf`) ✅
- Script automation (`scripts/staging_validation/deploy_fly.sh`) ✅
- Une fois que tu colles les URLs ici, je relance smoke tests + k6 +
  Lighthouse contre les URLs réelles et te livre le rapport.

---

## Étape 1 — Installer flyctl sur Windows

**PowerShell** (recommandé, official) :

```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

Cette commande télécharge `flyctl.exe` dans `~\.fly\bin\` et l'ajoute au
PATH user. **Ferme et rouvre ton terminal** pour activer le PATH.

Vérifier l'installation :
```powershell
flyctl version
```

Doit afficher `flyctl v0.X.Y` avec un OS/arch info.

**Alternative scoop** :
```powershell
scoop install flyctl
```

**Alternative manuelle** :
1. Aller sur https://github.com/superfly/flyctl/releases/latest
2. Télécharger `flyctl_X.Y.Z_Windows_x86_64.zip`
3. Extraire `flyctl.exe` dans un dossier au PATH

---

## Étape 2 — Auth Fly.io (~2 minutes, 0 carte)

```bash
flyctl auth signup        # premier compte (browser flow + email)
# OU si tu as deja un compte :
flyctl auth login         # browser flow uniquement
```

Le browser ouvre `fly.io/app/sign-up` :
- Email + password OU "Continue with GitHub"
- Aucune carte demandée pour les apps free allowance
- Validation email auto, retour terminal sur "Successfully logged in"

Vérifier :
```bash
flyctl auth whoami
```

Doit afficher ton email.

---

## Étape 3 — Deploy automatisé (1 commande)

Depuis la racine du repo :

```bash
bash scripts/staging_validation/deploy_fly.sh
```

Le script execute en séquence :

1. **Postgres dev create** : `flyctl postgres create --name uba-staging-db
   --region cdg --vm-size shared-cpu-1x --volume-size 1`
   - Demandera un mot de passe admin Postgres (note-le !)
   - ~2 minutes
2. **Backend app create** : `flyctl apps create uba-staging-api`
3. **Postgres attach** : `flyctl postgres attach uba-staging-db --app
   uba-staging-api` → injecte `DATABASE_URL` automatiquement
4. **Secrets generation** : `JWT_ADMIN_SECRET` + `JWT_CLIENT_SECRET`
   générés via `openssl rand -hex 32`, set via `flyctl secrets set
   --stage` (pas de redeploy immédiat)
5. **Backend deploy** : `flyctl deploy --config fly_backend.toml
   --remote-only --strategy rolling` → ~5-7 min (Docker build remote)
6. **Frontend app create + deploy** : idem pour `uba-staging-app` →
   ~3 min

**Durée totale** : ~10-15 minutes (Fly remote build).

**URLs auto-générées** :
- Backend : `https://uba-staging-api.fly.dev`
- Frontend : `https://uba-staging-app.fly.dev`

Le script imprime ces URLs à la fin + smoke test basique.

---

## Étape 4 — Secrets manuels (Stripe test mode, optionnel)

Si tu veux tester le checkout Stripe en staging :

```bash
flyctl secrets set --app uba-staging-api \
  STRIPE_API_KEY=sk_test_xxx \
  STRIPE_WEBHOOK_SECRET=whsec_xxx
```

Le redeploy auto se déclenche après `secrets set` (sauf `--stage`).

Ou exporter avant le deploy_fly.sh :
```bash
export STRIPE_API_KEY=sk_test_xxx
export STRIPE_WEBHOOK_SECRET=whsec_xxx
bash scripts/staging_validation/deploy_fly.sh
```

Le script détecte ces env vars et les set automatiquement.

---

## Étape 5 — Vérification smoke tests

Une fois les URLs disponibles :

```bash
bash scripts/staging_validation/smoke_tests.sh \
  https://uba-staging-api.fly.dev \
  https://uba-staging-app.fly.dev
```

12 checks couverts :
- API /health → 200
- API /health/v9 → status pass/warn
- API /docs → 200
- API /metrics → uba_* metrics
- API /client/project unauthed → 401/503
- API /admin/projects unauthed → 401/503
- CORS preflight → 200/204
- Frontend / → 200
- Frontend SPA fallback /client → 200
- HTTPS forced
- X-Frame-Options + X-Content-Type-Options
- SSL cert valid

---

## Étape 6 — Lighthouse + k6 + testssl

### Lighthouse CI (frontend)

```bash
npx -y @lhci/cli@latest autorun \
  --config=scripts/staging_validation/lighthouserc.json \
  --collect.url=https://uba-staging-app.fly.dev
```

Verdict si Performance ≥ 85 / Accessibility ≥ 95 / BP ≥ 90.

### k6 load test

Installer k6 sur Windows :
```powershell
choco install k6
# OU
winget install k6 --source winget
```

Puis :
```bash
API_BASE=https://uba-staging-api.fly.dev \
  k6 run scripts/staging_validation/k6_load_lite.js
```

2min ramp 10 users, threshold p95 < 1500ms + error_rate < 5%.

### testssl.sh

```bash
# Linux/macOS/WSL
bash scripts/staging_validation/testssl_audit.sh \
  https://uba-staging-api.fly.dev
```

Sur Windows pur, utiliser SSL Labs en alternative (online) :
https://www.ssllabs.com/ssltest/analyze.html?d=uba-staging-api.fly.dev

---

## Étape 7 — Verdict & GO/NO-GO

Si tous les checks passent :
- ✅ smoke 12/12
- ✅ Lighthouse Performance ≥ 85, A11y ≥ 95
- ✅ k6 p95 < 1500ms, error rate < 5%
- ✅ testssl ≥ B+ ou SSL Labs ≥ B

→ **GO** pour achat VPS définitif + déploiement production via
`V9_STAGING_DEPLOYMENT_PLAYBOOK.md` (avec ta confirmation explicite).

Sinon, j'analyse les fails et on itère.

---

## Commandes utiles Fly.io

```bash
# Logs en temps réel
flyctl logs --app uba-staging-api
flyctl logs --app uba-staging-app

# SSH dans un container
flyctl ssh console --app uba-staging-api

# Status + machines
flyctl status --app uba-staging-api

# Restart
flyctl machine restart --app uba-staging-api

# Scale (modifier RAM/CPU)
flyctl scale memory 512 --app uba-staging-api

# Run migrations manuellement (si release_command a échoué)
flyctl ssh console --app uba-staging-api \
  -C 'sh -c "for f in migrations/versions/0*.sql; do psql \"$DATABASE_URL\" -f \"$f\"; done"'

# Bootstrap V9
flyctl ssh console --app uba-staging-api \
  -C 'python -m app.saas_factory.self_bootstrap.bootstrap_runner'

# Issue token admin (pour tests)
flyctl ssh console --app uba-staging-api \
  -C "python -c 'from app.security.jwt_admin import create_admin_token, AdminRole; print(create_admin_token(admin_id=\"ahmed\", role=AdminRole.ADMIN))'"

# Suppression complète (nettoyage)
flyctl apps destroy uba-staging-api
flyctl apps destroy uba-staging-app
flyctl postgres destroy uba-staging-db
```

---

## Limites Fly.io free tier (à connaître)

- **256MB RAM par VM** : tendu pour Docker build local du frontend
  (utilise `--remote-only` qui build sur les serveurs Fly).
- **auto_stop_machines = "stop"** : VM s'éteint après idle, **cold
  start ~3-5s** sur premier hit. Acceptable pour staging.
- **Postgres dev single-node** : pas de HA, pas de backup automatique.
  Pour staging only, OK. Snapshot manuel possible :
  `flyctl postgres backup snapshot --app uba-staging-db`.
- **Bandwidth 160GB/mo** : largement suffisant.
- **Volume 3GB total** : si Postgres + assets dépasse, upgrade ($1.50/mo
  par GB additionnel).

---

## Si Fly.io plante aussi (fallback Neon + Railway)

**Neon** (Postgres serverless free 0.5GB sans carte) +
**Railway.app** (free trial $5 sans carte au signup parfois) :

1. Créer Postgres sur https://console.neon.tech (signup GitHub, 0 carte)
2. Copier la connection string `DATABASE_URL`
3. Sur Railway : "New Project" → "Deploy from GitHub" →
   `ELITEPROMOTION/usine-bombe-atomique`
4. Backend : Service → root `backend/` → variables `DATABASE_URL` +
   `JWT_*_SECRET`
5. Frontend : Service séparé → root `frontend/` → build `npm run build`
   → publish `dist/`

→ Plus de friction (3 services à wirer manuellement) mais 0 carte.

---

## Voir aussi

- `fly_backend.toml` — config backend Fly
- `fly_frontend.toml` — config frontend Fly
- `frontend/Dockerfile.fly` — multi-stage Node→Nginx pour Fly
- `frontend/nginx.fly.conf` — Nginx avec proxy_pass dynamique
- `scripts/staging_validation/deploy_fly.sh` — automation deploy
- `scripts/staging_validation/smoke_tests.sh` — 12 checks
- `scripts/staging_validation/k6_load_lite.js` — load test
- `scripts/staging_validation/lighthouserc.json` — Lighthouse CI config
- `V9_STAGING_DEPLOYMENT_PLAYBOOK.md` — VPS définitif (Phase ultérieure
  après validation Fly)
