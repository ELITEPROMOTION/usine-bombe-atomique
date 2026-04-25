# Deploiement UBA en production — Guide pas a pas pour Ahmed

> Genere automatiquement le **2026-04-25** depuis tes reponses du wizard.
> Compte cible: **ahmed@dendani.dz** · Domaine: **uba.dendani.dz** · Phone: **+213555000000**
> VPS Hetzner: plan **cpx21** en region **nbg1** · Timezone: **Africa/Algiers**
> Auto-backup: **OUI** · SMTP: **none**

Ce guide t'accompagne *de zero a UBA en ligne sur https://uba.dendani.dz*.
Tu peux le suivre a ton rythme; chaque section est independante.

---

## Sommaire

1. [Creation des 5 comptes](#1-creation-des-5-comptes)
2. [Validation identite Hetzner](#2-validation-identite-hetzner-environ-24h)
3. [Collecte des tokens API](#3-collecte-des-tokens-api)
4. [Execution du wizard](#4-execution-du-wizard)
5. [Acces post-deploiement](#5-acces-post-deploiement)
6. [Operations quotidiennes](#6-operations-quotidiennes)
7. [Troubleshooting — 10 scenarios courants](#7-troubleshooting--10-scenarios-courants)

---

## 1. Creation des 5 comptes

Tu vas creer 5 comptes externes. Pour chaque compte:
1. Utilise **ahmed@dendani.dz** comme adresse principale (sauf indication).
2. Active la **2FA TOTP** des que possible (Google Authenticator, Authy, ...).
3. Sauvegarde les **codes de recovery** dans un coffre (1Password, Bitwarden).

### 1.1 Hetzner Cloud (compute) — *obligatoire*
- URL: https://accounts.hetzner.com/signUp
- Plan recommande: **cpx21** (4 vCPU AMD / 8 GB RAM / 160 GB NVMe — env. 14 EUR/mois)
- Region a choisir: **nbg1** (proche de l'audience cible)
- Capture d'ecran attendue: **Console > Projects** avec un projet vide

### 1.2 Cloudflare (DNS + TLS proxy) — *obligatoire*
- URL: https://dash.cloudflare.com/sign-up
- Apres inscription: **Add a site** → entre **uba.dendani.dz**
- Cloudflare te donnera 2 nameservers (`xxx.ns.cloudflare.com`); va chez ton
  registrar de domaine pour les configurer.
- Capture attendue: zone **uba.dendani.dz** en statut "Active" (peut prendre 24h).

### 1.3 Scaleway (object storage backups) — obligatoire
Obligatoire car auto-backup est ACTIVE.
- URL: https://console.scaleway.com/register
- Apres inscription: **Project Dashboard > IAM > API keys > Generate**

### 1.4 Registrar du domaine — *obligatoire si tu n'as pas uba.dendani.dz*
- Si tu possedes deja **uba.dendani.dz**, saute cette etape.
- Sinon, registrar populaires DZ: NIC.dz / international: Cloudflare Registrar,
  Namecheap, Gandi, Porkbun.
- Apres achat, configure les nameservers Cloudflare (etape 1.2).

### 1.5 GitHub — *obligatoire pour deploy SSH*
- URL: https://github.com/signup
- Genere une cle SSH ED25519 sur ta machine:
  ```bash
  ssh-keygen -t ed25519 -C "ahmed@dendani.dz" -f ~/.ssh/uba_deploy_ed25519
  ```
- Ajoute la cle publique (`.pub`) sur GitHub: **Settings > SSH and GPG keys**.

---

## 2. Validation identite Hetzner (environ 24h)

Hetzner exige de verifier ton identite avant de provisionner du compute.

1. Connecte-toi a https://console.hetzner.cloud
2. **Account > Verify identity**: televerse une **piece d'identite** (CNI ou passeport).
3. Hetzner verifie sous 24h ouvrees. Tu reverras un email.
4. Tant que la verification n'est pas finie, le wizard echouera a "Phase 3: deploy".

Astuce: lance la verification d'identite **AVANT** de creer les autres comptes;
pendant l'attente, prepare Cloudflare et le registrar.

---

## 3. Collecte des tokens API

Tu auras besoin de 4 (ou 5) tokens. Garde-les dans un gestionnaire de mots
de passe — le wizard va les chiffrer localement avant tout stockage disque.

### 3.1 Hetzner API token
- **Console > Projects > {ton projet} > Security > API Tokens > Generate**
- Permission: **Read & Write**
- Format attendu: 64 caracteres alphanumeriques (le wizard verifie).

### 3.2 Cloudflare API token + Zone ID
- Token: **My Profile > API Tokens > Create Token**
  - Template: "Edit zone DNS" → Zone Resources: include zone **uba.dendani.dz**
  - Permissions additionnelles: `Zone:Zone Settings:Edit`, `Zone:Zone:Read`
- Zone ID: page d'overview de la zone, en bas a droite (32 hex chars).

### 3.3 Scaleway (si auto-backup)
- **IAM > API keys**: 3 valeurs (access_key, secret_key, project_id).

### 3.4 Claude API key (production)
- **https://console.anthropic.com/settings/keys**
- Genere une cle dediee `uba-prod`, format `sk-ant-...`

### 3.5 Cle SSH GitHub deja prete
- Chemin: `~/.ssh/uba_deploy_ed25519` (cree a l'etape 1.5)

---

## 4. Execution du wizard

Le wizard tourne **localement sur ta machine** (pas sur le VPS). Il a 4
phases sequentielles. Chaque phase verifie le travail des precedentes.

### 4.1 Pre-requis sur ta machine
- Python 3.12+
- `terraform` >= 1.6 (https://developer.hashicorp.com/terraform/install)
- `git` et acces clone au depot UBA
- Le package Python `cryptography` (deja inclus dans `requirements.txt`)

### 4.2 Phase 1 — `init` (ta config)
```bash
cd /chemin/vers/uba
python backend/scripts/prod_deployment_wizard.py --phase init
```
Le wizard te demande **8 valeurs** (avec des valeurs par defaut sensees,
deja remplies depuis tes reponses initiales). Resultat:
`deploy/config/ahmed_answers.json` (chmod 600).

### 4.3 Phase 2 — `credentials` (tes tokens)
```bash
python backend/scripts/prod_deployment_wizard.py --phase credentials
```
Pour chaque token, le wizard:
1. **Verifie le format** localement (longueur, charset).
2. **Test live** via API (HEAD/GET) — affiche OK ou KO + code HTTP.
3. **Chiffre** avec Fernet (cle locale `.fernet_key`, chmod 600).
4. Sauvegarde dans `deploy/config/credentials.enc`.

Aucun token n'est ecrit en clair sur le disque.

### 4.4 Phase 3 — `deploy` (provisioning + app)
```bash
# Optionnel: dry-run pour voir le terraform.tfvars sans appliquer
python backend/scripts/prod_deployment_wizard.py --phase deploy --dry-run

# Vrai deploiement
python backend/scripts/prod_deployment_wizard.py --phase deploy
```
Le wizard:
1. Genere `terraform/terraform.tfvars` depuis tes reponses.
2. `terraform init && plan && apply` — provisionne **VPS Hetzner +
   DNS Cloudflare + bucket Scaleway**.
3. Te donne l'IP publique du VPS.

Pour l'install applicative sur le VPS (Docker, repo, certbot Let's Encrypt),
utilise ensuite:
```bash
bash deploy/scripts/deploy_full.sh
```

### 4.5 Phase 4 — `validate` (smoke tests)
```bash
python backend/scripts/prod_deployment_wizard.py --phase validate
```
5 verifications:
- `https_reachable` — https://uba.dendani.dz repond
- `api_health` — /api/v1/health renvoie 200
- `workers_healthy` — workers ARQ enregistres
- `backups_listed` — backups visibles
- `slo_dashboard` — SLO en lecture

Toutes vertes → tu es **en production**.

---

## 5. Acces post-deploiement

| Ressource         | URL                                            |
|-------------------|------------------------------------------------|
| App principale    | https://uba.dendani.dz                               |
| Dashboard CEO     | https://uba.dendani.dz/ceo                           |
| Ahmed Inbox       | https://uba.dendani.dz/ahmed_inbox                   |
| API documentation | https://uba.dendani.dz/docs                          |
| Observability     | https://uba.dendani.dz/observability                 |
| Domaines          | https://uba.dendani.dz/domains                       |

Login admin:
- Email: **ahmed@dendani.dz**
- Mot de passe: celui que tu as defini en phase 2

---

## 6. Operations quotidiennes

### 6.1 Voir les logs
```bash
ssh root@<vps-ip> 'cd /opt/uba && docker compose logs -f --tail 200'
```

### 6.2 Declencher un backup manuel
```bash
ssh root@<vps-ip> 'cd /opt/uba && bash deploy/scripts/backup_enhanced.sh'
```
Apparaitra dans le bucket Scaleway sous `uba-backups/manual-YYYY-MM-DD.sql.gz`.

### 6.3 Restart des services
```bash
ssh root@<vps-ip> 'cd /opt/uba && docker compose restart backend worker_automation'
```

### 6.4 Voir le SLO dashboard
Ouvre https://uba.dendani.dz/observability → onglet **Metrics** ou **Errors**.

### 6.5 Verifier les alertes
Page Observability → **CI/CD** + **Errors**.
Pour les erreurs critiques, le webhook Sentry te previendra par email
a l'adresse ahmed@dendani.dz.

### 6.6 Mise a jour UBA
```bash
ssh root@<vps-ip> 'cd /opt/uba && git fetch && git checkout vX.Y.Z && \
    docker compose pull && docker compose up -d --remove-orphans'
```
Toujours **tagger le release** d'abord pour faciliter le rollback.

---

## 7. Troubleshooting — 10 scenarios courants — voir aussi `docs/TROUBLESHOOTING.md` pour 30 cas exhaustifs.

### 7.1 "terraform apply" plante avec `quota exceeded`
Hetzner limite a 5 VPS par defaut. Va sur **Console > Account > Quotas**
et augmente la limite a 10.

### 7.2 Cloudflare renvoie HTTP 525 SSL handshake failed
Le proxy CF est actif mais l'origine n'a pas encore son cert Let's Encrypt.
Solution: passe le DNS en mode **DNS Only** (nuage gris), termine
`certbot --nginx`, puis remets en mode **Proxied** (nuage orange).

### 7.3 Le wizard n'arrive pas a tester le token Hetzner (timeout)
Probablement que ta connexion bloque sortant 443. Verifie avec:
```bash
curl -v https://api.hetzner.cloud/v1/locations
```

### 7.4 SSH au VPS demande un mot de passe
La cle publique GitHub n'a pas ete uploadee dans Hetzner Cloud avant le
`terraform apply`. Solution rapide:
```bash
hcloud server ssh-key add uba-prod --ssh-key-id <id>
```
Sinon: re-run `terraform apply` avec `vps_ssh_keys = ["uba-deploy"]`.

### 7.5 docker compose up plante: "no space left on device"
`docker system prune -af --volumes` libere les anciennes images.
Si le disque est plein structurellement, redimensionne le VPS via Hetzner
et `terraform apply`.

### 7.6 Migrations en erreur "permission denied for schema public"
Le user postgres dans `.env.production` a un role insuffisant. Corrige:
```sql
GRANT ALL ON SCHEMA public TO uba;
```

### 7.7 Workers ARQ ne traitent rien
Verifie Redis: `docker compose exec redis redis-cli ping` doit renvoyer PONG.
Si OK, regarde les logs worker: `docker compose logs worker_automation`.

### 7.8 SLO dashboard vide
Pas de trafic = pas de SLO. Lance des requetes test:
```bash
for i in {1..50}; do curl -s https://uba.dendani.dz/api/v1/health >/dev/null; done
```

### 7.9 Backup quotidien manquant
Verifie le cron: `ssh root@<vps-ip> 'crontab -l | grep backup'`.
Re-installe avec `bash deploy/scripts/install_backup_cron.sh`.

### 7.10 SSL expire sous 7 jours
Renouvellement auto via certbot. Verifie le timer:
```bash
ssh root@<vps-ip> 'systemctl list-timers | grep certbot'
```
Force-renew: `certbot renew --force-renewal`.

---

## 8. Securite : checklist post-deploiement

Apres ton premier login admin, parcours cette checklist en moins de 30 minutes.

### 8.1 Comptes et mots de passe
- [ ] Active la **2FA TOTP** sur le compte admin **ahmed@dendani.dz**.
- [ ] Imprime ou note les **codes de recovery** dans un endroit sur.
- [ ] Change le **mot de passe par defaut** des comptes systeme (postgres,
  redis si exposes).
- [ ] Verifie qu'il n'existe pas de compte `admin/admin` ou `test/test`.

### 8.2 Reseau et firewall
- [ ] Confirme que **seuls 22, 80, 443** sont ouverts sur le VPS:
  ```bash
  ssh root@<vps-ip> 'ufw status numbered'
  ```
- [ ] Restreint l'acces SSH a ta plage IP via `ufw allow from <ton-ip>/32 to any port 22`.
- [ ] Active `fail2ban` (deja inclus dans cloud-init) — verifie:
  ```bash
  ssh root@<vps-ip> 'fail2ban-client status sshd'
  ```

### 8.3 SSL/TLS
- [ ] Test SSL Labs: https://www.ssllabs.com/ssltest/analyze.html?d=uba.dendani.dz
  → cible: **A+**.
- [ ] Verifie HSTS: `curl -sI https://uba.dendani.dz | grep -i strict-transport`.
- [ ] Programme un rappel calendrier 14 jours avant expiration du certificat.

### 8.4 Sauvegardes
- [ ] Confirme la presence de **3 backups** dans le bucket Scaleway (pour
  pouvoir restaurer J-1, J-2, J-3).
- [ ] Effectue un **test de restore** dans un environnement disposable:
  ```bash
  ./deploy/scripts/restore.sh --from s3://uba-backups/uba-2026-04-25.sql.gz \
                                --to /tmp/uba_restore_test
  ```
- [ ] Documente le RTO (Recovery Time Objective) mesure.

### 8.5 Audit
- [ ] Active le log JSON sur le backend (`LOG_FORMAT=json` dans `.env.production`).
- [ ] Verifie qu'**aucun secret** n'est dans `git log`:
  ```bash
  git log -p | grep -E "(api_key|password|token)" | head
  ```
- [ ] Lance le scan Bandit en local:
  ```bash
  cd backend && bandit -r app -ll
  ```

---

## 9. Liste blanche IP (recommande pour /admin)

L'API admin n'est pas exposee publiquement par defaut, mais tu peux ajouter
une couche supplementaire de defense en profondeur:

```nginx
# /etc/nginx/conf.d/uba-admin-allowlist.conf
location /api/v1/admin/ {
    allow 1.2.3.4/32;        # remplacer par ton IP fixe
    allow 5.6.7.8/32;        # IP secondaire (telephone 4G via Tailscale, etc.)
    deny all;
    proxy_pass http://backend:8000;
}
```

Apres modification, recharge nginx:
```bash
ssh root@<vps-ip> 'nginx -t && systemctl reload nginx'
```

---

## 10. Tableau de bord d'observabilite

Une fois en prod, ton workflow quotidien devrait commencer par:
https://uba.dendani.dz/observability

Les **6 onglets** te donnent une vue 360°:

| Onglet      | Quand le consulter                                           |
|-------------|--------------------------------------------------------------|
| Overview    | Tous les matins (sparkline des dernieres 30 min)             |
| Traces      | Quand une requete est lente — voir le span coupable          |
| Metrics     | Une fois par semaine — verifie SLO, p99, breaker states      |
| Logs        | En cas d'incident — `action: workflow_task_failed` filter    |
| Errors      | Si Sentry t'a notifie — voir le grouping par fingerprint     |
| CI / CD     | Avant un merge — verifie que les workflows sont verts        |

### Astuce: bookmarks navigateur
Cree 6 raccourcis dans la barre de marque-pages de ton navigateur:
- `https://uba.dendani.dz/observability?tab=overview`
- `https://uba.dendani.dz/observability?tab=metrics`
- ...

---

## 11. Plan de mise a l'echelle (scaling)

Quand UBA passera de **1 utilisateur (toi)** a **10+ utilisateurs**, voici
les leviers a actionner dans l'ordre de cout:

### 11.1 Etape 1 — Vertical scale (1 a 50 utilisateurs)
- Passe de **cpx21** a `cpx41` (8 vCPU / 16 GB) → +20 EUR/mois.
- Augmente le pool postgres a 50 connexions:
  ```yaml
  POSTGRES_POOL_MAX: 50
  ```
- Ajoute un 3e worker ARQ:
  ```bash
  docker compose up -d --scale worker_automation=3
  ```

### 11.2 Etape 2 — Horizontal scale (50 a 500 utilisateurs)
- Sors postgres du VPS principal vers une instance Hetzner managed
  (Postgres for Hetzner ou DBaaS Scaleway).
- Ajoute un **load balancer Hetzner** (5 EUR/mois) devant 2 VPS application.
- Active **Redis cluster** (2 nodes minimum).
- Considere un CDN edge pour les assets frontend (Cloudflare Pages).

### 11.3 Etape 3 — Multi-region (500+)
- Replicate postgres en read-replica dans une 2eme region.
- Geo-DNS via Cloudflare (Argo) — routing utilisateur vers la region la plus proche.
- Hetzner ne fait pas multi-region natif: bascule sur AWS/GCP a ce stade.

### 11.4 Indicateurs declencheurs
- p99 latency > 500 ms pendant 30 min → upgrade VPS.
- Pool postgres satures > 80% → augmente `POSTGRES_POOL_MAX`.
- Cron worker_automation_2 en lag > 5 min → ajouter un worker.

---

## 12. Mise a jour majeures (versions)

UBA suit semver: **MAJOR.MINOR.PATCH**.

- **PATCH** (ex: 5.5.5 → 5.5.6): aucun risque, applique direct sur prod.
- **MINOR** (ex: 5.5 → 5.6): peut introduire de nouvelles migrations DB.
  Procedure:
  ```bash
  ./deploy/scripts/backup.sh                       # backup avant
  git fetch && git checkout v5.6.0
  docker compose pull && docker compose up -d
  docker compose exec backend python -m app.migrations.runner --apply
  ```
- **MAJOR** (ex: 5.x → 6.x): peut casser l'API. Lis le **CHANGELOG**
  et fais un **dry-run sur staging** d'abord.

### Rollback rapide
```bash
bash deploy/scripts/rollback_full.sh
```

---

## 13. Compliance & RGPD/GDPR (DZ)

UBA stocke des donnees personnelles (emails, telephones, NIF). Tu dois:

1. Designer un **Delegue a la Protection des Donnees (DPO)** — peut etre toi.
2. Maintenir un **registre des traitements** (template fourni dans `docs/SECURITY.md`).
3. Repondre aux **droits d'acces et d'effacement** sous 30 jours.
4. **Notifier la CNDP** (Commission Nationale algerienne) en cas de fuite > 72h.
5. Activer le scrubbing PII automatique dans Sentry (deja fait par defaut).

---

## 14. FAQ rapide

**Q: Combien ca coute par mois?**
R: Hetzner (cpx21) ~14 EUR + Cloudflare 0 EUR + Scaleway storage ~3 EUR + Claude API selon usage = **environ 20 EUR/mois fixe** + variable Claude.

**Q: Puis-je heberger ailleurs (OVH, AWS, Scaleway compute)?**
R: Oui. Le module Terraform est multi-cloud. Modifie `terraform/main.tf` et utilise un module compatible (ex: `terraform-aws-modules/ec2-instance`).

**Q: Comment ajouter un autre admin?**
R: Connecte-toi en admin, va sur `/admin/users`, cree l'utilisateur. Force la 2FA des le premier login.

**Q: Comment integrer mon outil de notification (Slack, Telegram)?**
R: Configure le webhook dans `/observability` ou via `.env.production`:
```ini
UBA_NOTIFY_SLACK_WEBHOOK=https://hooks.slack.com/services/...
UBA_NOTIFY_TELEGRAM_BOT_TOKEN=123:abc
UBA_NOTIFY_TELEGRAM_CHAT_ID=-100...
```

**Q: La verification d'identite Hetzner echoue?**
R: Verifie que la photo est nette, eclairee, et que le numero du document est lisible. Sinon, ouvre un ticket support Hetzner (reponse < 4h).

---

## Annexe: contacts d'urgence

- **Domaine deploye**: uba.dendani.dz
- **Compte principal**: ahmed@dendani.dz
- **Telephone d'urgence**: +213555000000
- **Region VPS**: nbg1
- **Plan VPS**: cpx21
- **Timezone**: Africa/Algiers

Bonne mise en prod !

---

## Annexe: glossaire

- **VPS**: Virtual Private Server (machine virtuelle dediee).
- **DNS**: Domain Name System (annuaire des noms de domaine).
- **TLS/SSL**: Transport Layer Security (chiffrement HTTPS).
- **CDN**: Content Delivery Network (cache distribue).
- **CRON**: Planificateur de taches Unix.
- **ARQ**: file de tasks asynchrones backed-by Redis (workers UBA).
- **SLO**: Service Level Objective (objectif de qualite mesurable).
- **SLI**: Service Level Indicator (mesure brute).
- **OTel**: OpenTelemetry (standard d'observabilite).
- **HSTS**: HTTP Strict Transport Security (force HTTPS).
- **CSP**: Content Security Policy (anti-XSS).
- **NIF**: Numero d'Identification Fiscale (Algerie, 15 chiffres).
- **CNDP**: Commission Nationale de la Protection des Donnees (Algerie).
- **Fernet**: chiffrement symetrique authentifie (AES-128 + HMAC-SHA256).
- **GHCR**: GitHub Container Registry.
- **Codecov**: service d'analyse de couverture de tests.

---

*Genere le 2026-04-25 par `backend/scripts/generate_deployment_guide.py`. Re-execute le script si tes reponses changent.*
