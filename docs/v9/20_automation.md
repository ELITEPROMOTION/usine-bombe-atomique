# 20 — n8n automation

Référence : Phase 9Q (`docs/V9_PHASE_9Q_REPORT.md`), ADR-34.

## Pourquoi n8n et pas un scheduler interne ?

Cf. ADR-34 :
- Itération non-dev : ops/marketing peuvent ajuster sans code
- Visualisation : flux flagués, executions tab pour debug
- Failover découplé : n8n down ≠ backend down

## Workflows livrés (6)

| # | Fichier | Trigger | But |
|---|---|---|---|
| 01 | `01_paywall_reminder.json` | Cron 09:00 UTC | Relance projets `paywall_pending` > 24h |
| 02 | `02_handoff_escalation.json` | Cron @hourly | Escale handoffs > 24h vers Slack #ops |
| 03 | `03_gdpr_request_notify.json` | Webhook | Slack #compliance + email DPO |
| 04 | `04_payment_retry.json` | Cron @hourly | Ouvre handoff payment_confirm si fail > 6h |
| 05 | `05_weekly_project_digest.json` | Cron Mon 09:00 | Email recap clients actifs |
| 06 | `06_churn_alert.json` | Cron 08:30 | Détecte projets inactifs 14j → sales |

Source : `automation/n8n/*.json` + `automation/n8n/README.md`.

## Variables d'env n8n

```bash
UBA_API_BASE=https://api.ubastudio.io
UBA_WEB_BASE=https://app.ubastudio.io
UBA_ADMIN_TOKEN=<jwt admin>          # pour les endpoints /admin/*
RESEND_API_KEY=re_...
SLACK_WEBHOOK_OPS=https://hooks.slack.com/...
SLACK_WEBHOOK_SALES=https://hooks.slack.com/...
SLACK_WEBHOOK_COMPLIANCE=https://hooks.slack.com/...
DPO_EMAIL=dpo@ubastudio.io
```

## Procédure d'import

```bash
# UI : Settings → Workflows → Import from file
# Pour chaque JSON dans automation/n8n/

# OU CLI :
n8n import:workflow --input=./automation/n8n/01_paywall_reminder.json
# ... répéter pour les 6
```

⚠ Workflows désactivés par défaut. **Activer manuellement** depuis
l'UI après vérification des env vars.

## Endpoints attendus (statut)

| Endpoint | Phase qui l'a livré | Statut |
|---|---|---|
| `GET /admin/projects?status=...` | 9N | ✅ |
| `GET /admin/handoffs?states=...` | 9A + 9N | ✅ |
| `POST /admin/handoffs/{id}/escalate` | 9A | ✅ |
| `POST /admin/handoffs` | 9A + 9N | ✅ |
| `GET /admin/payments?status=failed&min_age_hours=...` | (futur) | ⚠ |
| `GET /admin/projects/inactive?days=...` | (futur) | ⚠ |
| Webhook UBA → n8n `gdpr.request_submitted` | (futur) | ⚠ |

Workflows 04, 06 et 03 nécessitent ces additions backend, à câbler
en V10 ou phase wiring.

## Source of truth

Le **JSON dans le repo** est la source de vérité. Si un ops modifie
un workflow depuis l'UI :
1. `n8n export:workflow --id=N --output=./automation/n8n/0X_*.json`
2. Commit le diff.

Sans ce protocole, le repo divergera de l'état runtime.

## Tests

Pas de tests automatisés en CI. Validation :
- Syntaxe JSON : `python -c "import json; json.load(open(f))"`
- Run staging : déclencher manuellement chaque workflow + vérifier
  Slack/email reçus.

## Voir aussi

- [11 — Deployment](./11_deployment.md)
- `automation/n8n/README.md`
- `docs/V9_PHASE_9Q_REPORT.md`
