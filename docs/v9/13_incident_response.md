# 13 — Incident response

## Triage initial

| Symptôme | Premier check |
|---|---|
| API timeouts | `GET /api/v1/health/v9` |
| 503 sur tous les endpoints | env vars `JWT_*_SECRET` configurées ? |
| Webhooks Stripe non traités | `STRIPE_WEBHOOK_SECRET` correct ? |
| Activity feed vide | DB up + audit_events row count |
| Frontend ne charge pas | Vite build artifacts servis ? |

## Playbooks par scénario

### Scénario 1 : Stripe down

**Symptôme** : checkout sessions échouent, webhooks 5xx.

**Action** :
1. Activer kill switch : `UBA_KILL_STRIPE=1`.
2. Le CB Stripe (Phase 9L) doit déjà s'être ouvert — vérifier
   `/admin/resilience/cb/stripe` (TODO endpoint).
3. Communiquer aux clients en cours via `/admin/projects/notify`.
4. Monitorer `https://status.stripe.com`.

### Scénario 2 : Boucle IA (cost guard hit)

**Symptôme** : `uba_ai_loop_detected_total` Prometheus counter
augmente ; `uba_ai_budget_blocked_total` aussi.

**Action** :
1. Le `LoopDetector` (Phase 9D) bloque automatiquement après N
   répétitions.
2. Inspecter `ai_decisions_log` table pour identifier le projet :
   ```sql
   SELECT project_id, COUNT(*)
     FROM ai_decisions_log
    WHERE created_at > NOW() - INTERVAL '1 hour'
    GROUP BY project_id ORDER BY 2 DESC LIMIT 5;
   ```
3. Reset cost guard : restart le pod (in-memory state).

### Scénario 3 : DB pool exhausted

**Symptôme** : timeouts sur tous les endpoints, `db_pool_exhausted`
chaos scenario en réalité.

**Action** :
1. Vérifier `pg_stat_activity` pour idle connections :
   ```sql
   SELECT count(*) FROM pg_stat_activity WHERE state = 'idle';
   ```
2. Tuer les long-running queries :
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity
    WHERE state = 'active' AND query_start < NOW() - INTERVAL '5 minutes';
   ```
3. Augmenter `pool_max_size` temporairement.

### Scénario 4 : Webhook Stripe replay malicieux

**Symptôme** : `uba_webhook_replay_blocked_total` counter spike.

**Action** :
1. C'est **normal** — l'idempotency (Phase 9H) bloque les replays.
2. Inspecter les origins IP dans logs Nginx pour identifier
   l'attaquant.
3. Block au niveau WAF / CloudFlare si nécessaire.

### Scénario 5 : Secret leak (JWT_ADMIN_SECRET ou JWT_CLIENT_SECRET)

**Symptôme** : tokens forgés repérés dans audit logs.

**Action** :
1. **Rotation immédiate** :
   ```bash
   kubectl set env deploy/api JWT_ADMIN_SECRET="<new-64-chars>"
   kubectl rollout restart deploy/api
   ```
2. Tous les tokens en vol deviennent invalides → utilisateurs
   doivent se re-login.
3. Pour client : reissue tokens via `create_client_token` et envoyer
   par email.
4. Audit `admin_actions` table pour identifier les actions
   frauduleuses pendant la fenêtre de leak.

### Scénario 6 : GDPR erasure mass abuse

**Symptôme** : volume anormal de demandes GDPR (>10/jour).

**Action** :
1. Examiner `data_erasure_requests` pour identifier l'origine :
   ```sql
   SELECT requester_email, COUNT(*)
     FROM data_erasure_requests
    WHERE requested_at > NOW() - INTERVAL '24 hours'
    GROUP BY 1 ORDER BY 2 DESC;
   ```
2. La fenêtre 30j (ADR-26) donne le temps de réagir.
3. `cancel_erasure(request_id)` côté admin si suspicion fraude.

## Communication client

Endpoint admin : `POST /admin/projects/:id/notify` (à câbler)
ou directement via `Resend` API depuis Python REPL.

Template de comm incident :
> Bonjour, nous rencontrons actuellement [DESCRIPTION] sur la
> plateforme. Nos équipes investiguent. ETA résolution :
> [TIMESTAMP]. Pas d'action requise de votre part.

## Post-mortem

Format minimum :
1. **Timeline** : ce qui s'est passé, quand
2. **Impact** : nb clients affectés, durée, $
3. **Root cause** : 5 whys
4. **Detection** : qui a détecté, comment, en combien de temps
5. **Resolution** : ce qui a été fait
6. **Prevention** : ADR si décision durable, action items concrets

Stocker dans `docs/incidents/YYYY-MM-DD-<slug>.md`.

## Voir aussi

- [11 — Deployment](./11_deployment.md)
- [12 — Admin runbook](./12_admin_runbook.md)
- [14 — Observability](./14_observability.md)
- [15 — Resilience](./15_resilience.md)
