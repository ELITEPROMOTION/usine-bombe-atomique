# V9 Staging Deployment Playbook — Phase 7

**Date** : 2026-05-01
**Statut** : à exécuter manuellement par Ahmed (infra requise non
provisionnable depuis cette session).

---

## Pourquoi un playbook plutôt qu'une exécution

Cette session ne dispose **pas** de :
- Accès DNS provider (Hostinger / Cloudflare / Route53)
- Compte cloud provider (AWS / Hostinger VPS / DO)
- Compte Stripe (test ou live)
- Compte Sentry / Datadog
- Compte Resend
- Instance n8n self-hosted
- Domaine + certificat SSL

→ **Toute action facturable nécessite confirmation explicite** (clause
plan production V9).

Le playbook ci-dessous est **prêt à coller** : chaque commande peut
être exécutée par Ahmed dans le terminal correspondant, avec
substitution des variables `<...>`.

---

## Pré-requis humain (achats / créations comptes)

⚠ **CES ACTIONS SONT FACTURABLES — confirmation explicite requise**

| Provider | Achat / Création | Coût indicatif |
|---|---|---|
| Domaine (Hostinger / OVH / Namecheap) | `<domaine>.com` | 10-15 €/an |
| VPS staging (Hostinger / DO / Hetzner) | 2 vCPU / 4 GB RAM | 5-10 €/mo |
| VPS n8n (séparé recommandé) | 1 vCPU / 2 GB RAM | 4-6 €/mo |
| Postgres managé (RDS / DO / Neon) | starter ~10 €/mo | 10 €/mo |
| Redis (DO / Upstash free tier) | free | 0 €/mo |
| Stripe (test mode) | gratuit | 0 €/mo |
| Resend (free tier 3k emails/mo) | gratuit | 0 €/mo |
| Sentry (free dev tier) | gratuit | 0 €/mo |

**Total mensuel staging** : ~25-35 €/mo (hors domaine).

---

## Étape 1 — DNS & domaine

```bash
# Sur Hostinger / Cloudflare DNS, configurer :
# api-staging.<domaine>.com    A     <IP VPS backend>
# app-staging.<domaine>.com    A     <IP VPS backend>
# n8n.<domaine>.com            A     <IP VPS n8n>
# mx.<domaine>.com             MX    10 mail.resend.com  (si email custom)

# CAA records pour Let's Encrypt only :
# <domaine>.com    CAA    0 issue "letsencrypt.org"
```

## Étape 2 — VPS staging setup

```bash
# SSH sur le VPS staging
ssh root@<IP_VPS>

# Updates
apt update && apt upgrade -y
apt install -y docker.io docker-compose nginx certbot python3-certbot-nginx ufw

# Firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Créer l'user uba
useradd -m -s /bin/bash uba
usermod -aG docker uba
mkdir -p /opt/uba && chown uba:uba /opt/uba

# Clone le repo
sudo -u uba git clone https://github.com/ELITEPROMOTION/usine-bombe-atomique.git /opt/uba/app
cd /opt/uba/app
git checkout v9.0.0
```

## Étape 3 — Secrets generation

```bash
# Générer les secrets random (64 chars hex)
echo "JWT_ADMIN_SECRET=$(openssl rand -hex 32)"
echo "JWT_CLIENT_SECRET=$(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"

# Stocker dans /opt/uba/.env (chmod 600)
sudo -u uba touch /opt/uba/.env
chmod 600 /opt/uba/.env

# Éditer .env avec :
# - DATABASE_URL=postgresql://uba:<password>@<host>:5432/uba_staging
# - JWT_ADMIN_SECRET=<generated>
# - JWT_CLIENT_SECRET=<generated>
# - STRIPE_API_KEY=sk_test_... (test mode !)
# - STRIPE_WEBHOOK_SECRET=whsec_... (à générer dans Stripe dashboard)
# - RESEND_API_KEY=re_...
# - SENTRY_DSN=https://...@sentry.io/...
# - UBA_LIVE_HOSTINGER=0
# - UBA_LIVE_STRIPE=0
# - UBA_CHAOS_ENABLED=0  (NEVER 1 en prod)
# Voir .env.example pour la liste complète
```

## Étape 4 — Database

```bash
# Postgres managé : créer la DB uba_staging
psql "$DATABASE_URL" -c "CREATE DATABASE uba_staging;"

# Apply migrations dans l'ordre
cd /opt/uba/app/backend
for f in migrations/versions/0*.sql; do
  echo "=== $f ==="
  psql "$DATABASE_URL" -f "$f"
done

# Bootstrap V9-BOOT (platform_config singleton)
docker run --rm --env-file /opt/uba/.env \
  uba-backend:v9.0.0 \
  python -m app.saas_factory.self_bootstrap.bootstrap_runner

# Vérifier
psql "$DATABASE_URL" -c "SELECT version, committed_at FROM platform_config WHERE id=1;"
```

## Étape 5 — Backend Docker deploy

```bash
# Build l'image avec le tag v9.0.0
cd /opt/uba/app/backend
docker build -t uba-backend:v9.0.0 .

# Run avec env-file
docker run -d \
  --name uba-api-staging \
  --restart unless-stopped \
  --env-file /opt/uba/.env \
  -p 127.0.0.1:8000:8000 \
  uba-backend:v9.0.0

# Logs
docker logs -f uba-api-staging
```

## Étape 6 — Frontend Vite + Nginx

```bash
cd /opt/uba/app/frontend
npm ci --prefer-offline
npm run build       # produit dist/

# Nginx config /etc/nginx/sites-available/uba-staging
cat > /etc/nginx/sites-available/uba-staging <<'EOF'
server {
    listen 80;
    server_name app-staging.<domaine>.com;
    root /opt/uba/app/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri /index.html;
    }
}
EOF
ln -s /etc/nginx/sites-available/uba-staging /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# SSL Let's Encrypt
certbot --nginx -d app-staging.<domaine>.com -d api-staging.<domaine>.com
```

## Étape 7 — n8n self-hosted

```bash
# Sur le VPS n8n (séparé recommandé)
docker run -d \
  --name n8n \
  --restart unless-stopped \
  -p 5678:5678 \
  -e N8N_HOST=n8n.<domaine>.com \
  -e WEBHOOK_URL=https://n8n.<domaine>.com/ \
  -e UBA_API_BASE=https://api-staging.<domaine>.com \
  -e UBA_ADMIN_TOKEN=<JWT admin généré via create_admin_token> \
  -e RESEND_API_KEY=<...> \
  -e SLACK_WEBHOOK_OPS=<...> \
  -e DPO_EMAIL=dpo@<domaine>.com \
  -v n8n_data:/home/node/.n8n \
  n8nio/n8n

# Importer les 6 workflows
for f in /opt/uba/app/automation/n8n/0*.json; do
  curl -X POST https://n8n.<domaine>.com/rest/workflows \
    -H "Content-Type: application/json" \
    -d @"$f"
done

# Activer manuellement chaque workflow depuis l'UI n8n
```

## Étape 8 — Smoke tests post-deploy

```bash
# 1. Health check
curl https://api-staging.<domaine>.com/api/v1/health/v9 | jq
# Attendu : {"status": "pass", "checks": {...}}

# 2. Frontend charge
curl -I https://app-staging.<domaine>.com/login
# Attendu : HTTP/2 200

# 3. Admin auth (issue token + call /admin/projects)
ADMIN_TOKEN=$(docker exec uba-api-staging python -c "
from app.security.jwt_admin import create_admin_token, AdminRole
print(create_admin_token(admin_id='ahmed', role=AdminRole.ADMIN, ttl_minutes=60))
")
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api-staging.<domaine>.com/api/v1/admin/projects | jq

# 4. Stripe webhook test (Stripe dashboard → Webhooks → "Send test event")
# checkout.session.completed → vérifier idempotency_key UNIQUE table

# 5. Sentry events
# Trigger une exception volontaire → vérifier dans Sentry dashboard

# 6. Prometheus scrape
curl https://api-staging.<domaine>.com/api/v1/metrics | head -20
```

## Étape 9 — Soak test 24h

Laisser le staging tourner 24h avec :
- Trafic synthétique léger (1 req/min sur `/health/v9`)
- Vérifier Sentry : 0 erreur critique
- Vérifier Prometheus :
  - SLO `webhook_handler_success` ≥ 99.99%
  - SLO `ai_router_availability` ≥ 99.9%
  - Pas de CB en OPEN persistant
- Vérifier DB pool : `SELECT count(*) FROM pg_stat_activity` < 80% max
- Backups quotidiens automatiques fonctionnent (vérifier S3 bucket /
  storage)
- Lighthouse audit https://app-staging.<domaine>.com/login : ≥ 95

---

## Rollback procédure

Si un incident grave en staging :

```bash
# Revert au tag précédent (v9.0.0-rc1)
cd /opt/uba/app && git checkout v9.0.0-rc1
docker stop uba-api-staging && docker rm uba-api-staging
docker run -d --name uba-api-staging --restart unless-stopped \
  --env-file /opt/uba/.env -p 127.0.0.1:8000:8000 uba-backend:v9.0.0-rc1

# Migrations : non rollback automatique. Si la migration a cassé :
psql "$DATABASE_URL" -c "DROP TABLE <table_problematique> CASCADE;"
# Ou pg_restore depuis backup pré-deploy
```

---

## Promotion staging → production

Après 24h soak validé :

```bash
# 1. Tag prod (si pas déjà fait)
git checkout main
git tag -a v9.0.0-prod -m "V9.0.0 promoted to production after staging soak"
git push origin v9.0.0-prod

# 2. Mêmes étapes 2-7 sur le VPS prod, avec :
#    - DATABASE_URL pointant sur la DB prod
#    - UBA_LIVE_STRIPE=1 (avec sk_live_... — confirmation explicite Ahmed)
#    - UBA_LIVE_HOSTINGER=1 (avec api_key live — confirmation explicite Ahmed)
#    - SENTRY_ENVIRONMENT=production
#    - JWT_ADMIN_SECRET / JWT_CLIENT_SECRET prod (différents du staging)

# 3. DNS switch : api.<domaine>.com → IP prod
# 4. Communication clients (email + landing page)
# 5. Activer les 6 workflows n8n en prod
```

---

## Notifications & alerting

Configurer dans Sentry / Slack :
- Alert si `uba_webhook_processing_duration_seconds` p99 > 1s
- Alert si `uba_payment_failed_total` rate > 5/min
- Alert si `uba_ai_loop_detected_total` > 0
- Alert si `uba_active_projects{status='paywall_pending'}` > 50
- Alert si circuit breaker en OPEN > 5 min
- Alert si `pg_stat_activity` count > 80% du max_connections

---

## Voir aussi

- `docs/v9/11_deployment.md` — deployment runbook
- `docs/v9/12_admin_runbook.md` — admin tasks
- `docs/v9/13_incident_response.md` — incident playbooks
- `V9_RELEASE_SUMMARY.md` — checklist staging à la racine
- `V9_PRODUCTION_READINESS_REPORT.md` — verdict final V9
