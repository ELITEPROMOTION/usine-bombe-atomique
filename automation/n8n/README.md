# UBA Studio — n8n Workflows (Phase 9Q)

Six workflows n8n pré-câblés sur les endpoints UBA. Ces workflows
externalisent l'orchestration récurrente (cron jobs, dunning,
escalations) qui ne mérite pas un job interne.

## Pourquoi n8n et pas un scheduler interne ?

- **Visualisation** : les ops voient le flux et peuvent débugger
  visuellement.
- **Itération non-dev** : marketing / ops peuvent ajuster les
  templates email, les seuils de relance, sans push code.
- **Failover découplé** : si n8n est down, le backend continue de
  servir les requêtes — seules les automatisations s'arrêtent.

Trade-off : duplique la logique scheduling avec ce qu'on aurait pu
mettre en interne. Acceptable car n8n est l'outil retenu côté ops
pour la V9.

## Variables d'environnement attendues

| Variable | Usage |
|---|---|
| `UBA_API_BASE` | URL backend, ex `https://api.ubastudio.io` |
| `UBA_WEB_BASE` | URL frontend, ex `https://app.ubastudio.io` |
| `UBA_ADMIN_TOKEN` | JWT admin (issuer `uba-studio/admin`) |
| `RESEND_API_KEY` | API key Resend (transactional email) |
| `SLACK_WEBHOOK_OPS` | Slack incoming webhook channel #ops |
| `SLACK_WEBHOOK_SALES` | Slack incoming webhook channel #sales |
| `SLACK_WEBHOOK_COMPLIANCE` | Slack incoming webhook channel #compliance |
| `DPO_EMAIL` | adresse DPO pour alertes GDPR |

## Catalogue (6 workflows)

| Fichier | Trigger | But |
|---|---|---|
| `01_paywall_reminder.json` | Cron 09:00 UTC | Relance projets `paywall_pending` > 24h |
| `02_handoff_escalation.json` | Cron @hourly | Escale handoffs ouverts > 24h vers ops |
| `03_gdpr_request_notify.json` | Webhook | Alerte ops + DPO sur demande GDPR |
| `04_payment_retry.json` | Cron @hourly | Ouvre handoff `payment_confirm` sur payment.failed > 6h |
| `05_weekly_project_digest.json` | Cron Mon 09:00 | Email recap hebdomadaire aux clients actifs |
| `06_churn_alert.json` | Cron 08:30 | Détecte projets sans activity 14j + alerte sales |

## Import dans n8n

```bash
# Method 1 : UI
# Settings -> Workflows -> Import from file -> select JSON
# Repeat for each workflow

# Method 2 : CLI
n8n import:workflow --input=./automation/n8n/01_paywall_reminder.json
n8n import:workflow --input=./automation/n8n/02_handoff_escalation.json
# ... etc
```

Après import, **activer chaque workflow manuellement** depuis l'UI
(les workflows sont désactivés par défaut pour éviter les
déclenchements accidentels).

## Endpoints backend attendus

Certains endpoints sont **non encore implémentés** en V9 (à
adresser en phase ultérieure) :

| Endpoint | Phase qui l'a livré | Statut |
|---|---|---|
| `GET /admin/projects?status=...` | 9N | ✅ |
| `GET /admin/handoffs?states=...` | 9A | ✅ |
| `POST /admin/handoffs/{id}/escalate` | 9A | ✅ |
| `GET /admin/payments?status=failed&min_age_hours=...` | (futur) | ⚠ |
| `POST /admin/handoffs` | 9A | ✅ |
| `GET /admin/projects/inactive?days=...` | (futur) | ⚠ |
| Webhook UBA `gdpr.request_submitted` | (futur, le client.py 9M-bis ne l'emit pas encore) | ⚠ |

Workflows 04 et 06 nécessitent des endpoints admin supplémentaires.
À livrer en phase ops V10 ou via wiring incrémental.

## Tests

Les JSON sont validés par `jq . *.json` (syntaxe). Les workflows
**eux-mêmes** doivent être testés en environnement n8n staging avant
activation prod (déclenchement manuel + vérification Slack/email
reçus).

## Références

- ADR-34 : décision "n8n vs interne" (cf. `docs/V9_ARCHITECTURE_DECISIONS.md`)
- Phase 9A : Handoff orchestrator (`docs/V9_PHASE_9A_REPORT.md`)
- Phase 9I : GDPR framework (`docs/V9_PHASE_9I_REPORT.md`)
- Phase 9M-bis : `/client/*` endpoints (`docs/V9_PHASE_9M_BIS_REPORT.md`)
