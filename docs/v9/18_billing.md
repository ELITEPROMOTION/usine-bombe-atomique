# 18 — Billing & invoicing

Référence : Phase 9H (`docs/V9_PHASE_9H_REPORT.md`), ADR-18/19/20.

## Stack

- **Stripe** : checkout sessions + webhooks (gated par `UBA_LIVE_STRIPE`).
- **StubStripeClient** : implémentation in-memory pour tests offline.
- **Tables** : `payments`, `invoices`, `refunds`, `webhook_events`
  (Phase 9H, migration 038).

## Flow checkout

```
Client                 Backend                       Stripe
  |                      |                              |
  |--- POST checkout --->|                              |
  |                      |--- create session --------->|
  |                      |<-- session_id, url ---------|
  |                      | INSERT payments (pending)    |
  |<-- session url ------|                              |
  |--------- pay -------------------- ----------------->|
  |                      |<--- webhook completed -------|
  |                      | (signature verify)           |
  |                      | (idempotency check)          |
  |                      | UPDATE payments succeeded    |
  |                      | INSERT invoice               |
```

## Idempotency (ADR-20)

Webhook `checkout.session.completed` retourné en succès même sur
replay :
1. Verify signature HMAC-SHA256.
2. INSERT INTO `webhook_events` ... ON CONFLICT (idempotency_key)
   DO NOTHING RETURNING.
3. Si aucune row retournée → already processed, return 200.

Idempotency key : `event.id` Stripe (ou hash du body si manquant).

## Paywall

`PaywallTrigger` (9H) : appelé quand un projet atteint 20% de
progression. Crée la session checkout.

## Invoices multi-pays / multi-langues

50+ taux TVA dans `vat_rates.py` :
- EU 27 (FR 20%, DE 19%, IE 23%, ...)
- UK 20%
- Maghreb (DZ 19%, MA 20%, TN 19%)
- Americas (US 0%, CA HST varie par province, BR 17%, MX 16%)
- Asia (JP 10%, IN 18%, AU GST 10%)
- Others

Génération :
1. Resolve VAT rate par `(country, locale)`.
2. Compute net + VAT + gross cents.
3. INSERT into `invoices` avec `invoice_number` séquentiel mensuel
   (`UBA-202604-000001`).
4. Génération PDF (job async) → `pdf_url` populated.

## Token IA invisibles (ADR-19)

Les invoices ne mentionnent **jamais** :
- `claude`, `anthropic`, `openai`, `gpt`, `llm`
- `tokens`, `prompt`, `inference`, `completion`

Test dédié vérifie ces 8 termes absents du HTML généré. Justification :
le client achète un **résultat**, pas une consommation de tokens.

## Refunds

`RefundManager` (9H) :
- Partial : `amount_cents < payment.amount_cents`
- Full : montant complet
- Tracé dans `refunds` table avec `reason`, idempotent par `refund_id`.

Status `payments.status` peut devenir `refunded` ou
`partially_refunded`.

## Live mode

```bash
# Production
UBA_LIVE_STRIPE=1
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Sans `UBA_LIVE_STRIPE=1`, le `StubStripeClient` est instancié →
aucun appel réel à Stripe.

## Voir aussi

- [11 — Deployment](./11_deployment.md)
- [13 — Incident response](./13_incident_response.md) (Stripe down playbook)
- `docs/V9_PHASE_9H_REPORT.md`
