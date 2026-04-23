# UBA Production Deployment Guide

**Cible** : Hetzner CPX21 Nuremberg + Cloudflare + Scaleway Paris + Grafana Cloud.
**Coût mensuel estimé** : ~13€ (5€ VPS + 1-3€ bucket + 0€ CDN/monitoring free tiers).

---

## Table des matières

1. [Pré-requis](#1-pre-requis)
2. [Provisioning VPS Hetzner](#2-provisioning-vps-hetzner)
3. [Hardening VPS (firewall + SSH + fail2ban)](#3-hardening-vps)
4. [Configuration DNS + Cloudflare](#4-configuration-dns--cloudflare)
5. [Scaleway Object Storage (bucket backups)](#5-scaleway-object-storage)
6. [Grafana Cloud (monitoring free tier)](#6-grafana-cloud)
7. [Secrets GitHub Actions](#7-secrets-github-actions)
8. [Premier déploiement](#8-premier-deploiement)
9. [SSL Let's Encrypt](#9-ssl-lets-encrypt)
10. [Vérifications post-déploiement](#10-verifications)
11. [Déploiements suivants](#11-deploiements-suivants)

---

## 1. Pré-requis

- Compte Hetzner Cloud (carte bancaire) — https://console.hetzner.cloud
- Compte Scaleway (carte bancaire) — https://console.scaleway.com
- Compte Cloudflare (gratuit) — https://dash.cloudflare.com
- Compte Grafana Cloud (free tier 10k metrics) — https://grafana.com/auth/sign-up/create-user
- Domaine `dendani.dz` déjà enregistré avec accès à la zone DNS
- Compte GitHub avec le repo UBA + packages activés (ghcr.io)
- SSH key locale (`~/.ssh/id_ed25519`) — sinon : `ssh-keygen -t ed25519 -C "ahmed@dendani.dz"`
- Machine locale avec : `docker`, `docker-compose-plugin`, `git`, `ssh`, `rsync`, `make`

---

## 2. Provisioning VPS Hetzner

### 2.1 Ajouter la clé SSH à Hetzner

```bash
cat ~/.ssh/id_ed25519.pub    # copier le contenu
```
Dans Hetzner Console → **Security → SSH Keys → Add SSH Key** → coller le contenu. Nommer `ahmed-laptop`.

### 2.2 Créer le serveur

Hetzner Console → **Servers → Add Server** :
- **Location** : Nuremberg (nbg1)
- **OS** : Ubuntu 24.04
- **Type** : CPX21 (3 vCPU AMD, 4 GB RAM, 80 GB NVMe — ~5 € HT/mois)
- **Networking** : IPv4 + IPv6 activés
- **SSH Keys** : sélectionner `ahmed-laptop`
- **Firewall** : créer nouveau `uba-prod` — règles :
  - Allow TCP 22 (SSH) — source : votre IP uniquement
  - Allow TCP 80, 443 — source : Cloudflare IPs (voir §4) ou 0.0.0.0/0 si pas encore prêt
  - Allow ICMP (ping)
  - Drop all else
- **Name** : `uba-prod-nbg1`

Noter l'IPv4 — ex : `95.217.XX.XX`.

### 2.3 Premier SSH

```bash
ssh root@95.217.XX.XX
# Accepter l'empreinte
```

---

## 3. Hardening VPS

Les commandes ci-dessous s'exécutent en tant que **root** sur le VPS. Copier-coller bloc par bloc.

### 3.1 Utilisateur non-root

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
```

### 3.2 Désactiver root SSH + MFA

```bash
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
echo "AllowUsers deploy" >> /etc/ssh/sshd_config
systemctl reload ssh
```

**Tester depuis votre machine** (sans fermer la session root) :
```bash
ssh deploy@95.217.XX.XX    # doit fonctionner
ssh root@95.217.XX.XX      # doit échouer
```

### 3.3 Firewall UFW

```bash
apt-get update && apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

### 3.4 fail2ban

```bash
apt-get install -y fail2ban
cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
EOF
systemctl enable --now fail2ban
```

### 3.5 Docker + docker-compose-plugin

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
apt-get install -y docker-compose-plugin
```

### 3.6 Mises à jour auto

```bash
apt-get install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

### 3.7 Créer le dossier de deploy

```bash
mkdir -p /srv/uba
chown deploy:deploy /srv/uba
```

Quitter le shell root : `exit`. Désormais toute suite **en tant que `deploy`**.

---

## 4. Configuration DNS + Cloudflare

### 4.1 Ajouter `dendani.dz` à Cloudflare

Cloudflare Dashboard → **Websites → Add a Site** → `dendani.dz` → plan Free.
Cloudflare donne 2 serveurs DNS (ex : `gina.ns.cloudflare.com`, `zack.ns.cloudflare.com`).

**Chez votre registrar de `dendani.dz`** : remplacer les DNS par ceux de Cloudflare. Propagation 5 min à 2 h.

### 4.2 Créer l'enregistrement A

Cloudflare → zone `dendani.dz` → **DNS → Add record** :
- Type : `A`
- Name : `uba`
- IPv4 : `95.217.XX.XX` (IP du VPS)
- Proxy status : **Proxied** (orange cloud — active DDoS + CDN)
- TTL : Auto

Résultat : `uba.dendani.dz → 95.217.XX.XX` via proxy Cloudflare.

### 4.3 Activer SSL full strict + règles recommandées

Cloudflare → zone `dendani.dz` :
- **SSL/TLS → Overview** : mode **Full (strict)**
- **SSL/TLS → Edge Certificates** : Always use HTTPS = On, HTTP Strict Transport Security (HSTS) = On (max-age 6 mois)
- **Security → WAF → Managed Rules** : activer "Cloudflare Managed Ruleset"
- **Speed → Brotli** : On
- **Rules → Page Rules** (optionnel) :
  - `https://uba.dendani.dz/api/*` → Cache Level: Bypass
  - `https://uba.dendani.dz/*.{js,css,png,svg,woff2}` → Cache Level: Cache Everything, Edge TTL: 1 day

### 4.4 Restreindre firewall Hetzner aux IPs Cloudflare

Pour maximiser la sécurité (Cloudflare = seul ingress) :

Télécharger les ranges depuis https://www.cloudflare.com/ips-v4/ et https://www.cloudflare.com/ips-v6/, puis dans le firewall Hetzner `uba-prod` → remplacer les règles 80/443 source `0.0.0.0/0` par ces ranges.

---

## 5. Scaleway Object Storage

### 5.1 Créer le bucket

Scaleway Console → **Object Storage → Buckets → Create a bucket** :
- Name : `uba-backups`
- Region : `fr-par` (Paris)
- Visibility : **Private**
- Cost : ~0,01 €/GB/mois stockage, ~0,01 €/GB sortie. 30 jours de dumps ≈ 1 à 3 €/mois.

### 5.2 Créer un API key dédié

Scaleway Console → **IAM → API Keys → Generate API key** :
- Application : créer `uba-backup` (ou utiliser un existant)
- Permissions : `ObjectStorageObjectsFullAccess` scoped au bucket `uba-backups`
- Copier **Access Key** + **Secret Key** (affichés une seule fois)

### 5.3 Sauvegarder pour §7

À ajouter dans les secrets GitHub ET dans `.env.production` sur le VPS.

---

## 6. Grafana Cloud

### 6.1 Créer le stack

https://grafana.com → **Sign up free** → créer un stack (ex : `dendani`).

### 6.2 Récupérer Prometheus remote_write endpoint

Stack → **Connections → Connect data → Hosted Prometheus metrics** :
- **URL** : `https://prometheus-prod-XX-eu-west-X.grafana.net/api/prom/push`
- **Username (instance ID)** : `1234567`
- **Password** : créer un Token (Access Policy = `metrics:write`)

### 6.3 (Optionnel) Loki endpoint pour les logs

Même menu → **Loki logs** → URL + username + token similaire.

### 6.4 Importer dashboards

Après premier déploiement :
- Grafana Cloud UI → **Dashboards → New → Import**
- Uploader `deploy/monitoring/grafana-dashboards.json`
- Datasource : `grafanacloud-<nom>-prom`

### 6.5 Importer alerting rules

- **Alerting → Alert rules → Import rules** → coller `deploy/monitoring/alerting-rules.yml`
- **Alerting → Contact points → New** → email `ahmed@dendani.dz` (ou webhook Telegram/Slack)
- **Alerting → Notification policies** → routing par label `severity=critical → ahmed email + SMS`

---

## 7. Secrets GitHub Actions

Repo GitHub → **Settings → Secrets and variables → Actions → Secrets → New repository secret**. Ajouter :

| Nom | Valeur |
|---|---|
| `VPS_HOST` | `95.217.XX.XX` (IP Hetzner) |
| `VPS_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | Contenu de `~/.ssh/id_ed25519` (clé privée) |

Pas besoin de mettre les secrets Scaleway/Grafana/Postgres ici : ils vivent dans `.env.production` sur le VPS (voir §8.2).

---

## 8. Premier déploiement

### 8.1 Cloner le repo sur le VPS

```bash
ssh deploy@95.217.XX.XX
cd /srv/uba
git clone https://github.com/<org>/uba.git .
```

### 8.2 Créer `.env.production` (ne jamais commit)

```bash
cat > /srv/uba/.env.production <<'EOF'
# --- Postgres ---
POSTGRES_DB=uba
POSTGRES_USER=uba
POSTGRES_PASSWORD=<GENERATE: openssl rand -hex 32>

# --- Redis ---
REDIS_PASSWORD=<GENERATE: openssl rand -hex 32>

# --- Vault ---
VAULT_ROOT_TOKEN=<GENERATE: openssl rand -hex 32>

# --- App ---
JWT_SECRET=<GENERATE: openssl rand -hex 32>
ANTHROPIC_API_KEY=sk-ant-api03-...
ENV=production
CORS_ORIGINS=["https://uba.dendani.dz"]

# --- Scaleway backup ---
SCW_ACCESS_KEY=SCWXXXXXXXXXXXXXXXXX
SCW_SECRET_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
SCW_BUCKET=uba-backups
SCW_ENDPOINT=https://s3.fr-par.scw.cloud
SCW_REGION=fr-par
BACKUP_RETENTION_DAYS=30

# --- Grafana Cloud ---
GRAFANA_CLOUD_PROM_URL=https://prometheus-prod-XX-eu-west-X.grafana.net/api/prom/push
GRAFANA_CLOUD_PROM_USER=1234567
GRAFANA_CLOUD_API_KEY=glc_xxxxx
GRAFANA_CLOUD_LOKI_URL=
GRAFANA_CLOUD_LOKI_USER=

# --- Sonarqube (optionnel) ---
SONAR_TOKEN=
EOF
chmod 600 /srv/uba/.env.production
```

**Générer les secrets** en une fois :
```bash
for k in POSTGRES_PASSWORD REDIS_PASSWORD VAULT_ROOT_TOKEN JWT_SECRET; do
  echo "$k=$(openssl rand -hex 32)"
done
```

### 8.3 Démarrer sans SSL d'abord

Éditer temporairement `deploy/nginx/conf.d/uba.conf` pour n'avoir que la section HTTP (§9 réactive HTTPS après obtention du cert).

```bash
cd /srv/uba
docker compose -f docker-compose.production.yml up -d postgres redis vault sonarqube backend worker worker_automation worker_automation_2 frontend
sleep 30
docker compose -f docker-compose.production.yml ps
```

Vérifier que backend est healthy :
```bash
curl -f http://localhost:8000/api/v1/health
```

---

## 9. SSL Let's Encrypt

### 9.1 Démarrer nginx en mode HTTP

```bash
cd /srv/uba
# Fichier temporaire nginx sans SSL - seulement le vhost 80
cat > deploy/nginx/conf.d/uba.conf.http-only <<'EOF'
server {
  listen 80;
  server_name uba.dendani.dz;
  location /.well-known/acme-challenge/ { root /var/www/certbot; }
  location /healthz { return 200 "ok\n"; }
  location / { return 404; }
}
EOF
mv deploy/nginx/conf.d/uba.conf deploy/nginx/conf.d/uba.conf.ssl
mv deploy/nginx/conf.d/uba.conf.http-only deploy/nginx/conf.d/uba.conf

docker compose -f docker-compose.production.yml up -d nginx
sleep 5
```

### 9.2 Obtenir le certificat

⚠️ **Note Cloudflare** : si le proxy Cloudflare est déjà en **Full (strict)** et pas encore de cert, temporairement mettre le proxy sur **DNS only** (gris) le temps du `certbot --webroot`, puis remettre en Proxied.

```bash
docker compose -f docker-compose.production.yml run --rm certbot \
  certonly --webroot --webroot-path=/var/www/certbot \
  --email ahmed@dendani.dz --agree-tos --no-eff-email \
  -d uba.dendani.dz
```

Cert stocké dans le volume `certbot_data` → `/etc/letsencrypt/live/uba.dendani.dz/`.

### 9.3 Réactiver le vhost SSL

```bash
mv deploy/nginx/conf.d/uba.conf deploy/nginx/conf.d/uba.conf.http-only
mv deploy/nginx/conf.d/uba.conf.ssl deploy/nginx/conf.d/uba.conf
docker compose -f docker-compose.production.yml restart nginx
```

Remettre le proxy Cloudflare sur **Proxied**. Le container `certbot` renouvelle auto toutes les 12 h.

---

## 10. Vérifications

### 10.1 Smoke tests

```bash
curl -I https://uba.dendani.dz/healthz    # 200
curl -I https://uba.dendani.dz/api/v1/health  # 200
curl -I https://uba.dendani.dz/api/v1/workflows/scheduled  # 200 (ou 401)
```

### 10.2 Premier backup manuel

```bash
docker compose -f docker-compose.production.yml exec backup /backup.sh
```
Devrait apparaître dans Scaleway bucket `uba-backups/postgres/YYYY/MM/`.

### 10.3 Démarrer tous les services restants

```bash
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml ps
```

Tous en `Up (healthy)`.

### 10.4 Vérifier Grafana Cloud

Grafana UI → Explore → Datasource Prometheus → query `up{service="uba"}` → on doit voir tous les jobs.

Si Ø : check `docker compose -f docker-compose.production.yml logs grafana-agent`.

---

## 11. Déploiements suivants

### Automatique (GitHub Actions)

Push sur `main` → `deploy.yml` build + push images GHCR → SSH VPS → `./deploy/scripts/deploy.sh`. Rollback via workflow_dispatch → `mode=rollback`.

### Manuel

```bash
ssh deploy@95.217.XX.XX
cd /srv/uba
git pull
./deploy/scripts/deploy.sh                  # rolling
./deploy/scripts/deploy.sh --migrate        # rolling + applique migrations pending
./deploy/scripts/deploy.sh --full           # stop + rebuild + up complet
./deploy/scripts/deploy.sh --rollback       # revert à l'image précédente
```

Chaque deploy :
- Prend un backup **avant** l'opération
- Health-check post-deploy (échec → exit non-zero → alerte CI)
- Mémorise version précédente pour rollback

### Restauration d'urgence

Voir **RECOVERY_PLAN.md**.

---

## Coût mensuel estimé

| Poste | Montant |
|---|---|
| Hetzner CPX21 (Nürnberg) | 4,75 €/mois |
| Hetzner IPv4 | 0,60 €/mois |
| Scaleway Object Storage (~2 GB) | 0,50–2 €/mois |
| Cloudflare Free tier | 0 € |
| Grafana Cloud Free tier | 0 € |
| Let's Encrypt SSL | 0 € |
| GitHub Actions (2000 min gratuites/mois) | 0 € |
| **Total** | **~6 à 8 €/mois** |

Budget cloud utilisateur (20–30 €/mois) largement couvert. La marge permet d'ajouter un second VPS (staging) ou d'upgrader vers CPX31 (8 GB RAM) si besoin.
