# V9 Go/No-Go Deployment Decision

**Date** : 2026-05-01
**Branche** : `main`
**Tag posé** : `v9.0.0-production-certified`

---

## Décision

🟢 **GO** pour les actions ne nécessitant pas d'infrastructure externe.
🟡 **CONDITIONAL GO** pour le déploiement production réel : conditionné
à exécution Phases 7-8 (staging + soak 24h) par Ahmed avec confirmation
explicite des actions facturables.

---

## Critères PASS audit 12 passes

| Critère | Statut |
|---|---|
| 779/779 tests verts | ✅ |
| Coverage 97.92% globale (cible 95%) | ✅ |
| Coverage critique ≥ 99% (jwt_client, rate_limiter, headers, etc.) | ✅ |
| 0 CVE Python (pip-audit clean) | ✅ |
| 0 vulnerability npm (audit clean) | ✅ |
| 0 secret en clair (grep + detect-secrets baseline) | ✅ |
| 0 Bandit High global | ✅ |
| 0 Bandit Medium+ V9 modules | ✅ |
| 0 ruff erreur (config default) sur V9 | ✅ |
| 0 TODO/FIXME/XXX/HACK V9 scope | ✅ |
| Vite build < 600 KB (579 KB) | ✅ |
| Docker build OK | ✅ |
| docker-compose.production.yml YAML valide | ✅ |
| 50 migrations idempotent | ✅ |
| 28 ADRs documentés | ✅ |
| 22 docs hub + 8 reports production | ✅ |
| ESLint v9 config livré | ✅ |
| 21 admin routes wirées (bug 9N résolu) | ✅ |
| 12 client endpoints (Phase 9M-bis) | ✅ |
| GDPR Art 6/15/17/20 | ✅ |
| 50+ pays TVA | ✅ |
| Mandats eIDAS | ✅ |

---

## Critères différés Phase 7 staging

Ces critères nécessitent **infrastructure réelle non disponible** dans
la session :

| Critère | Décision | Action |
|---|---|---|
| Pentest dynamique (ZAP/Burp/testssl.sh) | DIFFÉRÉ | Phase 7 staging |
| Lighthouse ≥ 95 | DIFFÉRÉ | Phase 7 staging |
| WCAG 2.1 AA browser audit | DIFFÉRÉ | Phase 7 staging |
| Browser compat (Chrome/Firefox/Safari/Edge) | DIFFÉRÉ | Phase 7 staging |
| Backup restore round-trip réel | DIFFÉRÉ | Phase 7 staging |
| Soak test 24h | DIFFÉRÉ | Phase 8 |
| k6 load test 100 users | DIFFÉRÉ | Phase 8 |
| Docker compose up tous healthy < 60s | DIFFÉRÉ | Phase 7 staging |
| Chaos kill containers réel | DIFFÉRÉ | Phase 7 staging |
| Performance queries < 100ms p95 | DIFFÉRÉ | Phase 7 + 8 staging |
| Datadog / Grafana / Slack alertes | DIFFÉRÉ | Phase 7 wiring |
| TLS 1.3 only | DIFFÉRÉ | Phase 7 (Nginx config) |
| AES-256-GCM at-rest | DIFFÉRÉ | Phase 7 (Postgres TDE provider) |
| Vault rotation 90j | DIFFÉRÉ | Phase 7 (Vault deploy) |

→ Tous documentés dans `V9_STAGING_DEPLOYMENT_PLAYBOOK.md` avec
commandes copy-paste pour exécution manuelle Ahmed.

---

## Actions facturables (confirmation explicite Ahmed requise)

⚠ **Ces actions ne peuvent pas être exécutées autonomément** :

| Action | Coût indicatif | Confirmation requise |
|---|---|---|
| Achat domaine | 10-15 €/an | OUI |
| VPS staging (Hostinger/DO) | 5-10 €/mo | OUI |
| Postgres managé staging | ~10 €/mo | OUI |
| VPS n8n self-hosted | 4-6 €/mo | OUI |
| Stripe live mode (UBA_LIVE_STRIPE=1) | 0 €/mo (commission) | OUI |
| Hostinger live mode (UBA_LIVE_HOSTINGER=1) | dépend | OUI |
| AWS / S3 backups | ~5 €/mo | OUI |

---

## Plan d'action recommandé

1. **Maintenant** : tag `v9.0.0-production-certified` sur le commit
   actuel (audit 12 passes complet PASS).
2. **Quand Ahmed prêt** : exécuter `V9_STAGING_DEPLOYMENT_PLAYBOOK.md`
   étape par étape.
3. **Phase 7 + 8** : staging deploy + soak 24h. Si SLOs respectés et 0
   alert critique → GO production absolu.
4. **Phase production** : promotion staging → prod avec confirmation
   explicite pour `UBA_LIVE_STRIPE=1` + `UBA_LIVE_HOSTINGER=1`.
5. **Rollback** : disponible via `git checkout v9.0.0-rc1` + redeploy
   (procédure dans `docs/v9/13_incident_response.md`).

---

## Verdict final

```
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   V9 ULTIMATE — AUDIT EXTREME 12 PASSES : PASS 🟢        ║
║                                                          ║
║   - 779 tests verts (97.92% coverage)                    ║
║   - 0 CVE Python / 0 CVE npm                             ║
║   - 0 secret en clair / 0 Bandit High                    ║
║   - 0 TODO/FIXME V9 scope                                ║
║   - Documentation complète (28 docs + 28 ADRs)           ║
║                                                          ║
║   TAG : v9.0.0-production-certified                      ║
║                                                          ║
║   GO PRODUCTION conditionnel staging soak Phase 7-8      ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

**Voir aussi** :
- `V9_AUDIT_FINAL_REPORT.md` — synthèse 12 passes
- `V9_AUDIT_IMPROVEMENTS.md` — toutes améliorations apportées
- `V9_STAGING_DEPLOYMENT_PLAYBOOK.md` — Phase 7 prêt à coller
