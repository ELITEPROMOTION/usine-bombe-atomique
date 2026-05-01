# V9 Phase 9Q — n8n Workflows — Final Report

**Date** : 2026-05-01
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9O)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9Q externalise les automatisations récurrentes de la V9 vers
**n8n self-hosted** plutôt qu'un scheduler interne (cf. ADR-34) :

| # | Workflow | Trigger | Cible business |
|---|---|---|---|
| 01 | Paywall reminder | Cron 09:00 UTC | Relance projets `paywall_pending` > 24h |
| 02 | Handoff escalation | Cron @hourly | Escale handoffs ouverts > 24h vers ops |
| 03 | GDPR request notify | Webhook | Slack #compliance + email DPO |
| 04 | Payment retry | Cron @hourly | Ouvre handoff `payment_confirm` sur fail > 6h |
| 05 | Weekly project digest | Cron Mon 09:00 | Email recap client active |
| 06 | Churn alert | Cron 08:30 UTC | Détecte projets inactifs 14j → sales |

Bonus : `automation/n8n/README.md` documente les variables d'env
attendues, les endpoints backend consommés (avec statut "livré /
à livrer"), la procédure d'import et le protocole de versioning
JSON ↔ n8n UI.

| Indicateur | Valeur |
|---|---|
| Workflows livrés | 6 |
| LoC JSON | ~480 |
| Validation syntaxe | ✅ 6/6 (`python -c json.load`) |
| Backend regression | aucune (no-code phase) |
| ADR | ADR-34 (n8n vs interne) |

---

## 2. Architecture

### 2.1 Pattern workflow

Chaque workflow suit le même squelette :
1. **Trigger** : cron ou webhook.
2. **Fetch** : GET sur un endpoint admin UBA (avec `Authorization:
   Bearer {{$env.UBA_ADMIN_TOKEN}}`).
3. **SplitInBatches** : itère sur la liste retournée.
4. **Action(s)** : POST UBA (handoff/escalate), Resend (email),
   Slack webhook (notif).

Aucune logique business duplique le backend ; n8n se contente
d'orchestrer **quand** déclencher quoi.

### 2.2 Variables d'environnement

8 env vars attendues, documentées dans `automation/n8n/README.md` :
`UBA_API_BASE`, `UBA_WEB_BASE`, `UBA_ADMIN_TOKEN`, `RESEND_API_KEY`,
`SLACK_WEBHOOK_OPS`, `SLACK_WEBHOOK_SALES`,
`SLACK_WEBHOOK_COMPLIANCE`, `DPO_EMAIL`.

### 2.3 Endpoints attendus

Workflows 04 et 06 nécessitent des endpoints admin **pas encore
livrés** en V9 :
- `GET /admin/payments?status=failed&min_age_hours=N`
- `GET /admin/projects/inactive?days=N`

Documentés comme "⚠ à livrer" dans le README. Workflows désactivés
par défaut, à activer manuellement après livraison endpoints.

Workflow 03 (GDPR) attend un webhook entrant `POST` que le backend
`/client/profile/gdpr/*` doit envoyer (fire-and-forget vers l'URL
n8n configurée). À câbler en phase wiring (1 ligne par endpoint).

---

## 3. Quality Gates

| Gate | Statut |
|---|---|
| JSON syntax (json.load × 6) | ✅ PASS |
| Backend regression | ✅ N/A (no-code phase) |
| README + ADR | ✅ PASS |

---

## 4. Limitations & dette

- **Tests d'intégration n8n absents** : les workflows ne sont pas
  testés en CI. Validation par déclenchement manuel staging avant
  activation prod.
- **2 endpoints admin manquants** (workflows 04, 06) : à livrer en
  phase wiring ops V10.
- **1 webhook UBA → n8n manquant** (workflow 03) : à câbler dans
  `app/routers/client.py` (POST GDPR).
- **Source of truth = JSON dans repo** : ops doivent re-export après
  modification UI sinon perte de versioning Git.
- **Pas de tests workflow visuel** : un changement structurel (e.g.
  nœud déplacé) ne casse rien Git mais peut rendre l'UI illisible.
  Acceptable car édition rare.

---

## 5. État cumulé

Backend : **758 tests verts**, 18 phases backend.
Frontend : 9M (client area) + 9O (design system étendu).
Automation : 9Q (6 workflows n8n).
