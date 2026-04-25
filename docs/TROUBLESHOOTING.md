# UBA — Troubleshooting (30 scenarios)

Chaque entree suit le format **Symptome → Diagnostic → Fix → Prevention**.

---

## I. Disponibilite

### 1. Backend renvoie 502 Bad Gateway via Cloudflare
- **Symptome**: `https://uba.dendani.dz` → 502.
- **Diagnostic**: backend down ou CF ne le voit pas. `curl -v http://127.0.0.1:8000/api/v1/health` sur le VPS.
- **Fix**: `docker compose restart backend`. Si KO, `docker compose logs backend --tail 200` et chercher la cause.
- **Prevention**: SLO alert sur `availability < 99%` 5 min.

### 2. 503 Service Unavailable persistant
- **Symptome**: tous les endpoints renvoient 503.
- **Diagnostic**: mode maintenance probablement active.
- **Fix**: `curl -X POST https://uba.dendani.dz/api/v1/admin/maintenance/stop` (avec admin token).
- **Prevention**: bouton de stop maintenance visible dans `/admin`.

### 3. Frontend blanc / "Failed to fetch chunks"
- **Symptome**: ecran blanc, console JS: `chunk-XXX.js failed`.
- **Diagnostic**: cache navigateur sur ancienne version apres deploy.
- **Fix**: hard reload (CTRL+SHIFT+R). Si nginx cache, `docker compose exec frontend nginx -s reload`.
- **Prevention**: hash dans les noms de chunks (deja en place via Vite).

### 4. Cloudflare 525 SSL handshake failed
- **Symptome**: error 525 dans le navigateur.
- **Diagnostic**: cert origine invalide ou expire.
- **Fix**: `certbot certificates && certbot renew --force-renewal && nginx -s reload`.
- **Prevention**: timer systemd `certbot.timer` doit etre `active`.

---

## II. Base de donnees

### 5. Migration "permission denied for schema public"
- **Diagnostic**: l'user `uba` n'a pas `CREATE` sur `public`.
- **Fix**: `psql -c "GRANT ALL ON SCHEMA public TO uba;"` (en superuser postgres).
- **Prevention**: cloud-init pose ce GRANT a la creation.

### 6. "could not serialize access due to concurrent update"
- **Diagnostic**: conflit serializable isolation.
- **Fix**: l'app retry automatiquement (backoff exponentiel). Verifier les logs pour le `retry_count`.
- **Prevention**: garder `MAX_RETRIES=3` dans `.env`.

### 7. postgres OOM killed
- **Symptome**: `dmesg | grep oom-killer` montre postgres tue.
- **Diagnostic**: `shared_buffers` trop grand vs RAM dispo.
- **Fix**: ajuster `shared_buffers = 2GB` (1/4 de la RAM totale).
- **Prevention**: alert SLO sur `pg_stat_database.deadlocks > 0`.

### 8. Connexions saturees ("FATAL: too many connections")
- **Diagnostic**: `SELECT count(*) FROM pg_stat_activity;` proche de `max_connections`.
- **Fix court-terme**: `KILL` les connexions idle > 1h.
- **Fix long-terme**: ajouter PgBouncer en pooler.

### 9. Disque postgres plein
- **Diagnostic**: `df -h /var/lib/docker/volumes`.
- **Fix**: `VACUUM FULL audit_events;` (libere les tuples morts). Ou augmenter le disque VPS.
- **Prevention**: alert quand disque > 80%.

---

## III. Redis / queue / workers

### 10. Workers ARQ ne traitent rien
- **Symptome**: queue grandit, jobs en `pending`.
- **Diagnostic**: `docker compose logs worker_automation`. Souvent: redis down.
- **Fix**: `docker compose restart redis worker_automation worker_automation_2`.
- **Prevention**: healthcheck redis cote workers.

### 11. Queue lag > 5 min
- **Diagnostic**: `redis-cli -n 0 XLEN arq:queue:default` grand.
- **Fix**: scale workers `docker compose up -d --scale worker_automation=4`.
- **Prevention**: KPI lag dans `/observability`.

### 12. Redis OOM (`OOM command not allowed when used memory > 'maxmemory'`)
- **Fix**: `redis-cli CONFIG SET maxmemory-policy allkeys-lru`.
- **Prevention**: `maxmemory 1gb` dans `redis.conf`.

---

## IV. Backups

### 13. Backup quotidien manquant
- **Diagnostic**: `crontab -l | grep backup`. Si absent, le timer n'est pas installe.
- **Fix**: `bash deploy/scripts/install_backup_cron.sh`.
- **Prevention**: alert si le dernier backup > 26h.

### 14. Backup echoue silencieusement
- **Diagnostic**: `tail /var/log/uba/backup.log` — souvent 0 octets ecrits.
- **Fix**: verifier l'espace disque, les credentials Scaleway, le `pg_dump --version`.
- **Prevention**: `set -euo pipefail` dans tous les scripts (deja en place).

### 15. Restore fail "version mismatch"
- **Diagnostic**: `pg_dump` v15 vs serveur v16.
- **Fix**: utiliser `pg_dump` du conteneur postgres (meme version).
- **Prevention**: documente la version dans le filename: `uba-2026-04-25-pg16.sql.gz`.

---

## V. SSL / DNS

### 16. SSL expire sous 7 jours
- **Diagnostic**: alert auto si `notAfter - now < 7d`.
- **Fix**: `certbot renew --force-renewal`.
- **Prevention**: timer systemd actif.

### 17. DNS ne resout pas
- **Diagnostic**: `dig uba.dendani.dz @1.1.1.1`.
- **Fix**: re-run `bash deploy/scripts/configure_dns.sh uba.dendani.dz <ip>`.
- **Prevention**: verifier que les nameservers du registrar pointent bien sur Cloudflare.

### 18. Cloudflare cache stale
- **Symptome**: changement deploy non visible.
- **Fix**: dashboard CF > Caching > Purge everything (ou API).

---

## VI. Securite

### 19. Tentatives de brute-force SSH
- **Diagnostic**: `fail2ban-client status sshd` -> banned IPs.
- **Fix**: deja gere (auto-ban). Pour bannir manuellement: `fail2ban-client set sshd banip 1.2.3.4`.
- **Prevention**: SSH key-only (deja en place via cloud-init).

### 20. Token API leake (push accidentel sur GitHub)
- **Reaction immediate**: revoke le token dans Hetzner/Cloudflare/Anthropic.
- **Fix**: re-run `prod_deployment_wizard.py --phase credentials` avec un nouveau token.
- **Prevention**: pre-commit hook `trufflehog` (a ajouter).

### 21. Rate limit DDoS
- **Diagnostic**: spike de 429 dans Datadog.
- **Fix**: serrer le rate limit (`RATE_LIMIT_RPM=30`), activer Cloudflare "Under Attack Mode".
- **Prevention**: WAF Cloudflare actif.

---

## VII. Monitoring / observability

### 22. Datadog ne recoit rien
- **Diagnostic**: `curl /api/v1/observability/datadog/status` → mode `cloud` mais pas de data.
- **Fix**: verifier `DATADOG_API_KEY`, region `DATADOG_SITE=datadoghq.eu` (pas .com).
- **Prevention**: snapshot de test en CI.

### 23. Sentry events absents
- **Diagnostic**: mode `cloud` actif mais pas de capture visible.
- **Fix**: trigger `POST /api/v1/observability/sentry/test` — si "captured":true, le pipeline marche; sinon verifier le DSN.
- **Prevention**: smoke test sentry/test apres chaque deploy.

### 24. SLO degrade artificiellement
- **Symptome**: SLO chute mais la stack semble OK.
- **Diagnostic**: trafic test ou healthcheck mal configure (compte les checks comme echec).
- **Fix**: exclure le path `/api/v1/health` du calcul SLO.

---

## VIII. Performance

### 25. p99 latency > 500 ms persistant
- **Diagnostic**: `/observability/metrics` -> `uba.domain.operations.latency_ms.p99`.
- **Fix**: identifier le domain coupable, profile avec `pyinstrument`.
- **Prevention**: benchmark CI fail si +20%.

### 26. Memoire backend > 1.5 GB
- **Diagnostic**: `docker stats backend`.
- **Fix**: restart le service. Investiguer fuite memoire (top objets via `tracemalloc`).
- **Prevention**: limit memoire docker `mem_limit: 1g`.

---

## IX. Frontend

### 27. WebSocket disconnect frequent
- **Diagnostic**: console navigateur "WebSocket closed code 1006".
- **Fix**: verifier que Cloudflare Websocket est ON (Network tab du dashboard).
- **Prevention**: heartbeat client toutes les 30s.

### 28. Connection refused on port 3000
- **Diagnostic**: en local, frontend pas demarre.
- **Fix**: `docker compose up -d frontend`.

---

## X. Misc

### 29. Migration N°XXX echoue avec syntax error
- **Diagnostic**: `psql -f backend/migrations/versions/0XX_name.sql` pour reproduire.
- **Fix**: corriger le SQL, recommit + redeploy.
- **Prevention**: linter SQL en pre-commit.

### 30. "wizard --phase deploy" plante "Permission denied" sur deploy/config/
- **Diagnostic**: `ls -la deploy/config/` → permissions trop ouvertes? Le wizard `chmod 600`.
- **Fix**: `chmod -R 700 deploy/config/`.
- **Prevention**: le wizard force chmod a chaque ecriture.

---

## En cas de blocage total

Contacte: dev@dendani.dz ou ouvre un issue avec:
- Sortie de `docker compose ps`
- 200 dernieres lignes de `docker compose logs backend`
- Capture du dashboard `/observability/overview`
- Sortie de `bash deploy/scripts/smoke_tests.sh uba.dendani.dz`

---

*UBA V5.9 / Vague 6 troubleshooting catalog.*
