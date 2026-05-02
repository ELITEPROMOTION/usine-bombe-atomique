# V9 Temporary Hosting Playbook — Render.com (free, no card required for static + web)

**Objectif** : valider V9 en conditions réelles **sans achat** avant
de provisionner le VPS définitif.

**Plateforme retenue** : **Render.com** (Blueprint natif, free tier
permanent pour static + web service free 750h/mo, Postgres free 90j).

**Alternative** : Fly.io (cf. `fly.toml`) si Render plante.

---

## Limite honnête de cette session

Je ne peux **pas** :
- Créer le compte Render à ta place (auth GitHub OAuth interactif)
- Cliquer "Apply Blueprint" pour toi
- Lire les URLs publiques générées (que toi seul vois dans ton dashboard)

Je **peux** :
- Préparer le Blueprint (`render.yaml` ✅ committé)
- Écrire les scripts validation (`scripts/staging_validation/` ✅)
- Une fois que tu colles l'URL ici, je lance smoke tests + k6 + Lighthouse
  contre l'URL réelle et te livre le rapport.

---

## Étape 1 — Créer le compte Render (~2 minutes, 0 €)

1. Va sur https://render.com
2. Clique **"Get Started for Free"**
3. **"Continue with GitHub"** → autorise Render à voir ton repo
   `ELITEPROMOTION/usine-bombe-atomique`
4. **PAS de carte requise** pour Web Service Free + Static Site Free
   (Postgres Free demande parfois une carte de "verification" mais aucun
   débit pendant 90j — sinon Fly.io alternative)

---

## Étape 2 — Apply le Blueprint (~5 clics, ~5 minutes)

1. Dashboard Render → **"New +"** → **"Blueprint"**
2. Sélectionner ton repo `ELITEPROMOTION/usine-bombe-atomique`
3. Render lit `render.yaml` (au root) et propose 3 services :
   - `uba-staging-api` (Web Service free, Docker)
   - `uba-staging-app` (Static Site free)
   - `uba-staging-db` (Postgres free 90j)
4. Bouton **"Apply"** en bas → Render commence le provisioning
5. Attente ~5 min :
   - Backend Docker build : ~3-5 min
   - DB postgres : ~1 min
   - Frontend Vite build : ~1-2 min

Pendant le build, **2 secrets sont à remplir manuellement** dans
le dashboard Render → ton service `uba-staging-api` → Environment :
- `STRIPE_API_KEY` : ta `sk_test_...` (Stripe test mode dashboard)
- `STRIPE_WEBHOOK_SECRET` : `whsec_...` (Stripe → Developers → Webhooks
  → Add endpoint → URL = `https://uba-staging-api.onrender.com/webhooks/stripe`)
- (optionnel) `SENTRY_DSN`

Après remplissage → **"Save Changes"** déclenche un re-deploy.

---

## Étape 3 — Migrations DB (~2 commandes côté toi)

Une fois `uba-staging-db` provisionné :

```bash
# Render dashboard → uba-staging-db → "Connect" tab → copier "External Database URL"
export DATABASE_URL="postgres://uba:<password>@dpg-xxxxx.frankfurt-postgres.render.com/uba_staging"

# Local ou via Render Shell (free tier disponible) :
cd backend
for f in migrations/versions/0*.sql; do
  echo "=== $f ==="
  psql "$DATABASE_URL" -f "$f"
done

# Bootstrap V9-BOOT (une seule fois)
docker run --rm --env-file <(echo "DATABASE_URL=$DATABASE_URL") \
  ghcr.io/eliteproduction/usine-bombe-atomique-api:latest \
  python -m app.saas_factory.self_bootstrap.bootstrap_runner

# Vérifier
psql "$DATABASE_URL" -c "SELECT version, committed_at FROM platform_config WHERE id=1;"
```

Alternative : utiliser Render's **"Pre-Deploy Command"** dans le
dashboard pour automatiser les migrations sur chaque deploy.

---

## Étape 4 — Récupérer les URLs

Render attribue automatiquement :
- **API** : `https://uba-staging-api.onrender.com`
- **APP** : `https://uba-staging-app.onrender.com`

(le sous-domaine peut varier si les noms sont déjà pris)

→ **Colle ces 2 URLs dans la conversation.** Je lance la validation.

---

## Étape 5 — Validation (je relance scripts contre tes URLs)

Quand tu me donnes les URLs, je lance :

```bash
# 1. Smoke tests (~10 secondes)
bash scripts/staging_validation/smoke_tests.sh \
  https://uba-staging-api.onrender.com \
  https://uba-staging-app.onrender.com

# 2. k6 load test lite (~2 minutes)
# k6 doit être installé local ou via cloud k6 (free trial)
API_BASE=https://uba-staging-api.onrender.com \
  k6 run scripts/staging_validation/k6_load_lite.js

# 3. Lighthouse CI (~2 minutes)
npx -y @lhci/cli@latest autorun \
  --config=scripts/staging_validation/lighthouserc.json \
  --collect.url=https://uba-staging-app.onrender.com

# 4. testssl.sh (~3-5 minutes, optionnel)
bash scripts/staging_validation/testssl_audit.sh \
  https://uba-staging-api.onrender.com
```

⚠ **k6 et Lighthouse CI ne sont pas installés dans ma session.** Je peux
les installer via npx pour Lighthouse, et essayer d'installer k6 binary
si possible. testssl.sh nécessite wget + bash mature (peut être limité
sur Windows Git Bash).

Si certains outils n'installent pas, je donne les commandes pour que tu
les lances toi-même et colles les outputs.

---

## Étape 6 — Verdict

Si tous les checks passent :
- ✅ smoke tests 12/12 PASS
- ✅ k6 p95 < 1500ms, error rate < 5%
- ✅ Lighthouse Performance ≥ 85, A11y ≥ 95, BP ≥ 90
- ✅ testssl ≥ B+

→ **GO** pour achat VPS définitif + production via
`V9_STAGING_DEPLOYMENT_PLAYBOOK.md` (avec confirmation explicite).

Sinon, on itère sur les fails.

---

## Limites Render free tier (à connaître)

- **Web service free sleep** après 15 min inactivité → **cold start
  ~30s** sur premier appel. Ne pas s'inquiéter du premier hit lent.
- **Postgres free** : 90 jours, puis $7/mo (Neon ou Supabase free
  alternatives si tu veux pas payer).
- **CPU/RAM** : 512MB RAM sur web free → Vite build peut être tendu
  mais doit passer (notre bundle 579KB).
- **Bandwidth** : 100GB/mo free → suffisant pour staging.

---

## Si Render ne marche pas (fallback Fly.io)

```bash
# Installer flyctl
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Deploy backend (utilise fly.toml au root)
flyctl launch --copy-config --no-deploy --name uba-staging
flyctl postgres create --name uba-staging-db --region cdg --vm-size shared-cpu-1x --volume-size 1
flyctl postgres attach uba-staging-db --app uba-staging
flyctl secrets set \
  JWT_ADMIN_SECRET=$(openssl rand -hex 32) \
  JWT_CLIENT_SECRET=$(openssl rand -hex 32) \
  UBA_LIVE_STRIPE=0 UBA_LIVE_HOSTINGER=0 UBA_CHAOS_ENABLED=0
flyctl deploy
```

URL : `https://uba-staging.fly.dev`

---

## Voir aussi

- `render.yaml` — Blueprint Render au root
- `fly.toml` — config Fly.io alternative
- `scripts/staging_validation/` — smoke + k6 + lighthouse + testssl
- `V9_STAGING_DEPLOYMENT_PLAYBOOK.md` — playbook VPS définitif (Phase
  ultérieure, après validation staging temporaire)
