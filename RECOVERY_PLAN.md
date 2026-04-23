# UBA — Recovery Plan

Objectifs :
- **RTO (Recovery Time Objective)** : < 30 minutes
- **RPO (Recovery Point Objective)** : < 24 heures (backup quotidien 02:00 UTC)

---

## Quand déclencher ce plan

- Backend UBA down > 5 min (alerte `BackendDown`)
- Postgres corrompu / chain_hash cassée (alerte `EvidenceChainBreak`)
- VPS injoignable (alerte externe uptime)
- Compromission suspectée (activité IP anormale, fichier `.env` fuite)
- Disque plein > 95 % (alerte `DiskSpaceCritical`)
- Multi-services en cascade

**Contact humain obligatoire** : Ahmed (CEO) décide si la recovery est destructive (restore DB).

---

## Niveau 1 — Service degradé, données intactes

**Symptômes** : un service down, autres OK.

**Actions (5–10 min)** :
```bash
ssh deploy@uba.dendani.dz
cd /srv/uba
docker compose -f docker-compose.production.yml logs --tail 100 <service>
docker compose -f docker-compose.production.yml restart <service>
```

Si 3 restarts consécutifs échouent → passer en **Niveau 2**.

---

## Niveau 2 — Rollback du dernier déploiement

**Symptômes** : depuis un deploy récent, erreurs 5xx augmentent, tests smoke échouent.

**Actions (5 min)** :
```bash
ssh deploy@uba.dendani.dz
cd /srv/uba
./deploy/scripts/deploy.sh --rollback
```

Ou via CI :
```bash
gh workflow run deploy.yml -f mode=rollback
```

La version précédente est mémorisée dans `.uba_previous_version`.

Vérifier :
```bash
curl -f https://uba.dendani.dz/api/v1/health
```

---

## Niveau 3 — Corruption Postgres / evidence chain break

**Symptômes** : alerte `EvidenceChainBreak`, queries qui crashent, `pg_isready` échoue intermittemment.

### 3.1 Diagnostic

```bash
docker compose -f docker-compose.production.yml exec postgres \
  psql -U uba -d uba -c "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM evidence_ledger;"

docker compose -f docker-compose.production.yml exec backend python -c "
import asyncio
from app.database import init_pool, close_pool
from app.orchestration import evidence_ledger
async def main():
    p = await init_pool()
    r = await evidence_ledger.verify_chain(p, limit=50000)
    print(r)
    await close_pool()
asyncio.run(main())
"
```

Si `integrity_ok: false` + broken links → **restore depuis backup**.

### 3.2 Stop services applicatifs

```bash
docker compose -f docker-compose.production.yml stop backend worker worker_automation worker_automation_2 frontend
```

### 3.3 Lister backups disponibles

```bash
docker compose -f docker-compose.production.yml exec -T backup /restore.sh --list
```

Output attendu (plus récent en bas) :
```
 54321234 2026-04-22 02:00:15.000000000 postgres/2026/04/uba_20260422T020000Z.pgcustom
 54500123 2026-04-23 02:00:18.000000000 postgres/2026/04/uba_20260423T020000Z.pgcustom
```

### 3.4 Restore depuis backup

**Prod cassée → restore `--latest`** :
```bash
docker compose -f docker-compose.production.yml exec -T backup \
  /restore.sh --latest
```

**Point-in-time voulu → `--key`** :
```bash
docker compose -f docker-compose.production.yml exec -T backup \
  /restore.sh --key postgres/2026/04/uba_20260422T020000Z.pgcustom
```

Le script :
- Télécharge depuis Scaleway
- Vérifie SHA-256 vs manifest
- Drop + recrée toutes les tables (`pg_restore --clean --if-exists`)

### 3.5 Redémarrer

```bash
docker compose -f docker-compose.production.yml up -d backend worker worker_automation worker_automation_2 frontend

# Attendre 60s puis verify
sleep 60
curl -fsS https://uba.dendani.dz/api/v1/health

# Re-verify evidence chain
docker compose -f docker-compose.production.yml exec -T backend python -c "
import asyncio
from app.database import init_pool, close_pool
from app.orchestration import evidence_ledger
async def main():
    p = await init_pool()
    r = await evidence_ledger.verify_chain(p)
    print('integrity_ok:', r['integrity_ok'])
    await close_pool()
asyncio.run(main())
"
```

### 3.6 Post-mortem

- Taguer les audit_events dans la fenêtre perdue comme `recovery_ts=<ISO>`
- Documenter dans `docs/INCIDENTS.md` : cause, RTO réel, RPO réel, actions préventives

---

## Niveau 4 — VPS totalement perdu / compromis

**Symptômes** : SSH timeout > 10 min, Hetzner console inaccessible, soupçon de compromission.

**RTO cible** : 30 min — grâce aux backups externes Scaleway + GitHub code source + configs.

### 4.1 Provisioner nouveau VPS (15 min)

Suivre §2 et §3 de `DEPLOYMENT.md` sur un **nouveau VPS**. Même région Nuremberg ou fallback Falkenstein.

### 4.2 Mettre à jour DNS Cloudflare (2 min)

Cloudflare → DNS → record `uba` → IP nouvelle → Save.
Propagation Cloudflare : 1 min via proxy (pas besoin d'attendre TTL).

### 4.3 Cloner le repo + config

```bash
ssh deploy@<nouvelle-IP>
cd /srv/uba
git clone https://github.com/<org>/uba.git .
# Récupérer .env.production depuis un secret storage (Bitwarden, 1Password...)
# ou regénérer tous les secrets (Postgres, Redis, Vault, JWT)
```

### 4.4 Démarrer la stack

```bash
docker compose -f docker-compose.production.yml up -d postgres
sleep 30
```

### 4.5 Restore depuis Scaleway

```bash
docker compose -f docker-compose.production.yml up -d backup
docker compose -f docker-compose.production.yml exec -T backup /restore.sh --latest
```

### 4.6 Démarrer le reste

```bash
docker compose -f docker-compose.production.yml up -d
```

### 4.7 SSL Let's Encrypt

Cert du volume `certbot_data` est perdu → suivre §9 de `DEPLOYMENT.md` (cert neuf rate-limité à 5/semaine/domaine — ok dans ce cas).

### 4.8 Vérifier

```bash
curl -f https://uba.dendani.dz/api/v1/health
curl -f https://uba.dendani.dz/api/v1/workflows/scheduled
```

---

## Niveau 5 — Compromission (credentials fuite, backdoor suspect)

**Ordre d'opération non-négociable** :

1. **Isoler** : firewall Hetzner → drop all ingress 80/443 (seul SSH reste).
2. **Notifier Ahmed** : décision humaine pour tout le reste.
3. **Rotate tous les secrets** :
   - `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `VAULT_ROOT_TOKEN`, `JWT_SECRET` (sessions invalidées → tous logout)
   - `ANTHROPIC_API_KEY` → regénérer sur console Anthropic
   - `SCW_ACCESS_KEY`/`SCW_SECRET_KEY` → Scaleway → supprimer clé + créer nouvelle
   - `GRAFANA_CLOUD_API_KEY` → Grafana Cloud → rotate
   - `DEPLOY_SSH_KEY` (GitHub secret) → supprimer + regénérer `~/.ssh/deploy_key` + update `~/.ssh/authorized_keys` sur VPS
4. **Snapshot forensic** : dump des logs Docker, `dpkg --verify`, `ls -la /etc/cron.d/` pour backdoors éventuelles.
5. **Si backdoor confirmée** → rebuild complet Niveau 4 (nouveau VPS). L'ancien VPS : snapshot Hetzner conservé pour investigation, puis détruit.
6. **Audit Cloudflare Analytics** → identifier l'IP attaquante, ajouter à la WAF blocklist globale.

---

## Tableaux de bord et alertes

Grafana Cloud → dashboard **UBA - Overview** doit être vert avant de clôturer l'incident :
- Backend up = 1
- Postgres up = 1
- Redis up = 1
- `up{service="uba"}` = 1 pour tous les targets
- Success rate workflows > 90 % sur 1 h
- DLQ unresolved < 10

---

## Tests de recovery (obligatoire mensuel)

- **1er du mois** : Ahmed lance `restore.sh --key <backup-de-la-veille>` sur un VPS de test.
- Vérifie que la base contient les données attendues (COUNT workflow_executions, AUDIT events, autonomy_kpis).
- Documenter durée réelle dans `docs/INCIDENTS.md` section "Drills".

Sans ces tests, un backup n'est **pas vérifié** → équivaut à pas de backup.

---

## Contacts d'urgence

| Rôle | Nom | Contact |
|---|---|---|
| Décideur (CEO) | Ahmed | ahmed@dendani.dz / WhatsApp |
| Cloud admin | Ahmed | compte Hetzner / Scaleway / Cloudflare |
| Support Hetzner | — | https://console.hetzner.cloud/ → Support (1h SLA business) |
| Support Scaleway | — | https://console.scaleway.com/ → Tickets |
| Anthropic billing issue | — | https://console.anthropic.com/ |

---

## Checklist post-recovery

- [ ] Health endpoints répondent 200
- [ ] Evidence chain integrity OK
- [ ] Workflows schedules count = 26
- [ ] Event triggers count >= 9
- [ ] Dernier backup < 24 h (sinon déclencher un `docker compose exec backup /backup.sh`)
- [ ] Grafana Cloud dashboards live (metrics fraîches < 5 min)
- [ ] SSL cert valide > 30 j
- [ ] `docs/INCIDENTS.md` mis à jour (RTO, RPO, actions préventives)
- [ ] Ahmed informé + validation écrite
