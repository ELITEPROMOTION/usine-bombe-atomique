# UBA — Guide administrateur (operations courantes)

> Public cible: l'**ops** (toi pour le moment, eventuellement un dev de Dendani plus tard).
> Tout est manipulable depuis le shell sur le VPS, ou via l'API admin avec un token.

---

## 1. Connexion VPS

```bash
ssh root@<vps-ip>
cd /opt/uba
```

> Si tu n'as pas l'IP: `terraform -chdir=terraform output vps_ipv4` depuis ta machine locale.

---

## 2. Voir l'etat de la stack

```bash
docker compose -f docker-compose.production.yml ps
```

Tu dois voir 7 services en `Up (healthy)`:
- postgres, redis, vault, sonarqube, backend, frontend, worker_automation (×2)

Pour les logs en streaming:
```bash
docker compose -f docker-compose.production.yml logs -f --tail 200 backend worker_automation
```

---

## 3. Start / Stop / Restart

| Action                           | Commande                                                        |
|----------------------------------|-----------------------------------------------------------------|
| Restart backend uniquement       | `docker compose restart backend`                                |
| Restart workers uniquement       | `docker compose restart worker_automation worker_automation_2`  |
| Stop tout (maintenance window)   | `docker compose down`                                           |
| Up tout (apres maintenance)      | `docker compose up -d`                                          |
| Force-recreate (bug bizarre)     | `docker compose up -d --force-recreate <service>`               |

---

## 4. Voir les logs

### 4.1 Logs structures (JSON, dernier jour)
```bash
docker compose logs --since 24h backend | jq 'select(.level=="ERROR")'
```

### 4.2 Logs Datadog (si mode file)
```bash
tail -f /tmp/uba_datadog/datadog-metrics.jsonl
```

### 4.3 Logs Sentry (si mode file)
```bash
tail -f /tmp/uba_sentry/errors-capture.jsonl | jq
```

### 4.4 Logs nginx
```bash
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

---

## 5. Backups

### 5.1 Trigger un backup manuel
```bash
bash deploy/scripts/backup.sh             # full backup, tar.gz
bash deploy/scripts/backup_enhanced.sh    # incremental + scaleway push
```

### 5.2 Lister les backups
```bash
ls -lh /var/backups/uba/
# Si scaleway:
aws --endpoint-url https://s3.fr-par.scw.cloud s3 ls s3://uba-backups/
```

### 5.3 Restore
```bash
bash deploy/scripts/restore.sh --from /var/backups/uba/uba-2026-04-25.sql.gz
```
(Restore dans une DB temporaire `uba_restore` pour validation, puis swap manuel.)

---

## 6. Update UBA

### 6.1 Patch (5.5.5 -> 5.5.6) — sans risque
```bash
cd /opt/uba
git fetch --tags
git checkout v5.5.6
docker compose pull && docker compose up -d --remove-orphans
```

### 6.2 Minor (5.5 -> 5.6) — peut introduire migrations
```bash
cd /opt/uba
bash deploy/scripts/backup_enhanced.sh  # backup d'abord
git fetch --tags
git checkout v5.6.0
docker compose pull && docker compose up -d --remove-orphans
docker compose exec backend python -m app.migrations.runner --apply
```

### 6.3 Rollback
```bash
bash deploy/scripts/rollback_full.sh         # tag precedent
bash deploy/scripts/rollback_full.sh v5.5.5  # tag specifique
```

---

## 7. Security audit

### 7.1 Bandit (Python SAST)
```bash
cd /opt/uba/backend
docker compose exec backend bandit -r app -ll
```

### 7.2 Safety (CVE Python deps)
```bash
docker compose exec backend safety check --file requirements.txt
```

### 7.3 npm audit (frontend)
```bash
cd /opt/uba/frontend
npm audit --audit-level=high
```

### 7.4 Trivy (image scan)
```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image --severity HIGH,CRITICAL uba-backend:latest
```

### 7.5 Secret scan (in git history)
```bash
docker run --rm -v $(pwd):/repo trufflesecurity/trufflehog:latest \
  filesystem /repo --only-verified
```

---

## 8. User management

### 8.1 Lister les users
```bash
curl -s -H "Authorization: Bearer $UBA_ADMIN_TOKEN" \
  https://uba.dendani.dz/api/v1/admin/users | jq
```

### 8.2 Creer un user
```bash
curl -s -X POST -H "Authorization: Bearer $UBA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"new@dendani.dz","role":"editor","force_2fa":true}' \
  https://uba.dendani.dz/api/v1/admin/users
```

### 8.3 Reset mot de passe
```bash
curl -s -X POST -H "Authorization: Bearer $UBA_ADMIN_TOKEN" \
  https://uba.dendani.dz/api/v1/admin/users/<id>/reset-password
```

### 8.4 Desactiver un user
```bash
curl -s -X POST -H "Authorization: Bearer $UBA_ADMIN_TOKEN" \
  https://uba.dendani.dz/api/v1/admin/users/<id>/disable
```

---

## 9. Database operations

### 9.1 Shell psql
```bash
docker compose exec postgres psql -U uba -d uba
```

### 9.2 Migrations
```bash
# Voir l'etat actuel
docker compose exec backend python -m app.migrations.runner --status

# Appliquer les pending
docker compose exec backend python -m app.migrations.runner --apply

# Rollback dernier (DESTRUCTIF, vérifier avant)
docker compose exec backend python -m app.migrations.runner --rollback 1
```

### 9.3 Vacuum / analyze
```bash
docker compose exec postgres psql -U uba -d uba -c "VACUUM ANALYZE;"
```

### 9.4 Top queries lentes
```sql
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC LIMIT 20;
```

---

## 10. Observability ops

### 10.1 Forcer un snapshot Datadog
```bash
curl -X POST https://uba.dendani.dz/api/v1/observability/datadog/snapshot
```

### 10.2 Verifier les SLO
```bash
curl https://uba.dendani.dz/api/v1/slo/status?window=1h | jq
```

### 10.3 Lancer un chaos scenario
```bash
curl -X POST -H "Authorization: Bearer $UBA_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scenario_id":"postgres_5s_delay"}' \
  https://uba.dendani.dz/api/v1/resilience/chaos/run
```

---

## 11. Ressources / quotas

| Ressource | Limite par defaut             | Comment changer            |
|-----------|-------------------------------|----------------------------|
| postgres pool | 30 connexions             | `POSTGRES_POOL_MAX` env    |
| arq workers | 2 instances                 | `--scale worker_automation=N` |
| rate limit | 100 req/min/user            | `RATE_LIMIT_RPM` env       |
| backup retention | 90 jours              | `BACKUP_RETENTION_DAYS` env |
| Cloudflare cache TTL | 4h            | `cf-cache-control` header  |

---

## 12. Cron jobs

Liste des jobs systemd-timers / cron sur le VPS:
```bash
systemctl list-timers --all | grep -E '(backup|certbot|uba)'
crontab -l
```

---

## 13. SSL (Let's Encrypt)

### 13.1 Verifier l'expiration
```bash
echo | openssl s_client -servername uba.dendani.dz -connect uba.dendani.dz:443 2>/dev/null \
  | openssl x509 -noout -dates
```

### 13.2 Forcer le renouvellement
```bash
certbot renew --force-renewal
systemctl reload nginx
```

---

## 14. Dashboard d'urgence

3 endpoints "boss button" pour gerer les incidents:

| Endpoint                                         | Effet                                        |
|--------------------------------------------------|----------------------------------------------|
| `POST /api/v1/admin/circuit-breakers/open-all`   | Ouvre tous les breakers (mode degrade)        |
| `POST /api/v1/admin/maintenance/start`           | Active le mode maintenance (HTTP 503 + page) |
| `POST /api/v1/admin/cache/flush`                 | Flush total du cache Redis                   |

---

## 15. Checklist hebdomadaire

Tous les **lundis matin**, 15 min:
- [ ] Verifie que tous les backups des 7 derniers jours existent.
- [ ] Verifie le SLO `availability` >= 99.5% sur la semaine.
- [ ] Verifie qu'il n'y a pas de PR ouverte de plus de 7 jours.
- [ ] Verifie qu'il n'y a pas de tickets Sentry HIGH non triages.
- [ ] Verifie que la quota Hetzner / Cloudflare / Scaleway n'est pas saturee a 80%.

---

*UBA V5.9 / Vague 6.*
