# V9 Phase 9R — Tests E2E — Final Report

**Date** : 2026-04-30
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9H)
**Statut final** : **PASS** (+ 1 bug réel attrapé et corrigé)

---

## 1. Résumé exécutif

Phase 9R livre des **tests d'intégration transverses** validant que les
modules 9-BOOT/9A/9B/9C/9D/9E/9F/9G/9H s'enchaînent correctement. **Pas
de nouveaux modules ni migration** — uniquement un fichier de tests E2E
qui chaîne les engines réels avec un état asyncpg mocké.

**Highlight** : le test E2E-6 (Direct link → Handoff resolve) a attrapé
un **bug réel** dans `HandoffOrchestrator` — l'orchestrateur référençait
`card.body` alors que `ActionCard` expose `description`. Les tests
unitaires 9E ne l'avaient pas vu (mock MagicMock avec `.body` ad hoc).
Bug corrigé avant que ça parte en prod.

| Indicateur | Valeur | Cible |
|---|---|---|
| Scénarios E2E | 6 + 1 smoke | 6 |
| Tests Phase 9R | 9 / 9 ✅ | 6+ |
| Tests cumulés (9-BOOT à 9R) | **500 / 500** ✅ | toutes |
| Bug production attrapé | 1 (HandoffOrchestrator card.body→description) | bonus |
| Coverage cumulée | **98%** (inchangée) | ≥ 90% |
| Ruff | 0 erreur (8 autofix + 1 RUF013 manuel) | 0 |
| Bandit (≥ Medium) | 0 issue | 0 |
| Auto-fix loop | 1 itération (E2E-5 séquence fetchrow réordonnée) | ≤ 3 |

---

## 2. Stratégie

### 2.1 Pas de DB réelle — pourquoi

Les schemas PostgreSQL de la V9 utilisent :
- `JSONB` (`payload_json`, `metadata_json`)
- `gen_random_uuid()` (UUID PK généré côté DB)
- `INTERVAL '24 hours'` (vues `v_revenue_30d`, `v_ai_cost_24h`)
- `pgcrypto digest()` pour les seals evidence_ledger
- Triggers complexes append-only sur `audit_events`

Un shim SQLite-en-mémoire devrait réécrire 50%+ des migrations. Le ROI
ne le justifie pas — les contracts entre modules sont testables avec
des mocks structurés, et les tests d'intégration DB-réels seront couverts
par la suite production_readiness existante (Phase 9 hors-scope).

### 2.2 Pas de SQLite shim — pourquoi

Tentative envisagée : adapter chaque module pour fonctionner contre une
DB SQLite. Coût : réécriture des SQL, perte de la validation au niveau
schema (CHECK constraints, JSONB, etc.). Bénéfice : douteux — ce qu'on
testerait serait du code adapté, pas du code prod.

Cf. ADR-21.

### 2.3 Stratégie retenue : `_fake_pool` + side_effects séquencés

```python
def _fake_pool(side_effects):
    pool = MagicMock()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=side_effects)
    ...
    return pool, conn
```

Chaque test E2E pré-programme la séquence exacte de retours `fetchrow`
attendue par le pipeline (INSERT RETURNING / SELECT WHERE / UPDATE
RETURNING). La 1ère erreur fait planter le test → on identifie où le
contract est cassé.

**Limitation acceptée** : ces tests vérifient la séquence d'appels DB, pas
la sémantique réelle de la DB. Un changement de SQL silencieux pourrait
passer. À couvrir par les tests `production_readiness` existants.

---

## 3. Scénarios livrés

### E2E-1 — Onboarding (9F) → Project → QualificationTrigger

```
OnboardingEngine.start()
  → save_step × 6 (Identity, Brief, Pack, Branding, Technical, Review)
  → ProjectFactory.create_from_session()
       → INSERT projects
       → mark_submitted
       → trigger(project_id, cdc_text, owner_email, metadata)
```

Vérifie que le `cdc_text` passé au trigger = la `description` du
`ProjectBriefStep`, et que `metadata` contient `pack_id_hint`, `country`,
`locale` extraits des bonnes étapes.

### E2E-2 — Qualification via RouterBackedClaudeProvider (9C + 9D)

```
StubAIProvider (canned JSON Claude-shaped)
  → AIRouter.route() (pondération + cost_guard + loop_detector)
  → RouterBackedClaudeProvider.analyze_cdc() (parse markdown ```json```)
  → QualificationEngine.qualify() (Pydantic validation + persist)
```

Vérifie : 1 appel router, decisions_logger.log status=ok, qualification
persistée avec `pack_hint=saas_small`, `confidence=high`.

### E2E-3 — Pricing → Assembly → Progression (chaîne 9C interne)

```
PricingEngine.quote(facets, coefficients)
  → AssemblyEngine.assemble(qualification, pricing)
  → ProgressionEngine.initialize(phase_weights)
```

Vérifie que `assembly.phase_weights` somme à 100, et que
`ProgressionEngine.initialize` insère 6 lignes (1 par phase canonique).
Contrat critique : `Pack.phases` (9C) → `assembly.phase_weights` (9C) →
`project_progression` rows (9C).

### E2E-3bis — Paywall → Checkout (9C → 9H)

```
project_progression.paywall_triggered_at IS NOT NULL
  → PaywallTrigger.maybe_trigger(project_id)
       → lit pricing 9C, project 9F, vérifie pas de payment existant
       → CheckoutManager.create_session()
            → INSERT payments status=pending
            → Stripe POST /checkout/sessions (Stub)
```

Vérifie que le montant TTC = `gross_price × 100` cents, et que
`line_items[0].price_data.unit_amount` reçu par Stripe est correct.
Aussi : si `payment` existant, court-circuit (return None).

### E2E-4 — Webhook → Mark paid → Invoice (9H bout-à-bout)

```
WebhookHandler.process(signed_payload)
  → verify_webhook_signature (HMAC)
  → INSERT webhook_events idempotency_key UNIQUE
  → dispatch checkout.session.completed
       → UPDATE payments status=succeeded
       → callback project_resume → InvoiceGenerator.issue_for_payment
            → INSERT invoices RETURNING
  → render_html() : ZÉRO leak terme AI (claude/tokens_in/cost_usd/...)
```

Vérifie le flow complet **paiement → invoice**. Le test no-leak parcourt
8 termes AI interdits dans l'HTML rendu.

### E2E-5 — Service activation (9-BOOT)

```
AccountCreatorOrchestrator.plan_all()
  → ServicePriorityQueue (8 services, tier 1→2→3 strict)
  → MandateEngine.issue() × 8 (chaîne SHA-256)
  → HandoffKycOrchestrator.open_handoff() × 3 (tier 2/3 only)
```

Vérifie : 8 mandats émis, ordre par tier strict, tier 1 = AUTOMATED sans
handoff, tier 2 = REQUIRES_CARD avec handoff, tier 3 (stripe) =
REQUIRES_KYC avec handoff.

### E2E-6 — Direct link → Handoff resolve flow (9A + 9E)

```
HandoffOrchestrator.request()
  → DirectLinkGenerator.issue() (token urlsafe)
  → INSERT handoff_requests
HandoffOrchestrator.acknowledge(token) (idempotent silent noop si pas
                                         encore notified)
HandoffOrchestrator.resolve(token, payload)
  → ValidationEngine.consume() (atomique)
  → UPDATE handoff_requests state=resolved
  → ResolutionCallback fires avec (handoff_id, action_type, project_id, payload)
```

**🐛 Bug attrapé** : `HandoffOrchestrator.request` utilisait `card.body`
alors que `ActionCard` expose `description`. Les tests unitaires 9E
mockaient `cards.render` avec `MagicMock` qui acceptait n'importe quel
attribut. L'E2E avec le **vrai** `ActionCardGenerator` a planté à la
ligne du SQL INSERT. **Fix** : 2 occurrences corrigées dans
`orchestrator.py:159` et `orchestrator.py:186`. Tous les tests unitaires
9E continuent de passer (ils mockent toujours, mais le code prod est
maintenant correct).

### Smoke test — `hash_token` contract stability

Vérifie que `hash_token("known")` produit toujours le même `sha256`. Si
quelqu'un change l'algo, **tous les tokens existants en DB deviennent
unreachable** — ce smoke test bloquerait le PR.

---

## 4. Conformité aux contraintes

| Contrainte | Respect |
|---|---|
| Master plan #49 (coverage 99% critique / 90% reste) | ✅ (98% cumulé, modules critiques 100%) |
| Phase 9R (5h estimé) | ✅ |
| Aucun appel externe payant | ✅ (Stub Claude/Stripe/Hostinger partout) |
| Pas de tag autonome | ✅ |
| Aucune régression (500/500) | ✅ + 1 bug réel corrigé |
| Conventional commit | ✅ |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (500 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (8 autofix + 1 RUF013 manuel) |
| bandit -ll | ✅ PASS (0 issue Medium+) |
| coverage globale ≥ 90% | ✅ PASS (98% cumulé) |
| Bug regression | ✅ 1 bug attrapé + corrigé |

---

## 6. Limitations

- **Pas de DB réelle** : les tests E2E vérifient la séquence d'appels
  asyncpg, pas la sémantique SQL. Un changement de SQL non détecté par
  Pydantic pourrait passer. La suite `production_readiness` existante
  (`backend/tests/production_readiness/`) couvre les tests contre une DB
  réelle Postgres au démarrage.
- **Pas de tests E2E pour l'admin** : les routers `/admin/*` (Phase 9N)
  sont déjà testés par `test_admin_router.py` avec FastAPI TestClient.
  Pas de duplication.
- **Pas de scénario refund E2E** : `RefundManager` est testé en isolation
  (Phase 9H). Un E2E refund nécessiterait un payment paid + une SLA
  violation simulée — peu utile sans déclencheur SLA réel (Phase 9Q
  futur).
- **Pas de scénario admin override → audit** : couvert indirectement par
  `test_admin_router.py::TestAdminAuditLogger`.

---

## 7. Apport de Phase 9R au-delà des tests unitaires

| Type de bug détecté | Tests unitaires | Tests E2E |
|---|---|---|
| Logique interne d'un module | ✅ | — |
| Validation Pydantic | ✅ | — |
| Contrat entre 2 modules (signature, DTO names) | partiel (mocks) | ✅ **catched bug** |
| Ordre des appels DB sur un pipeline complet | — | ✅ |
| Propagation d'IDs (project_id, payment_id, ...) | — | ✅ |
| Idempotency cross-module | — | ✅ |
| Garanties non-fonctionnelles (no AI leak) | partiel | ✅ |

**Conclusion** : Phase 9R justifie son existence — 1 bug réel attrapé
qui aurait causé un crash en production sur le **chemin critique du
paiement** (handoff "payment_confirm" pour le paywall 20%).

---

## 8. État cumulé V9 sur la branche

| Phase | Commit | Tests | Coverage | LoC |
|---|---|---|---|---|
| 9-BOOT | `bba1fa1` | 58 | 97% | +2 970 |
| 9A | `71896b1` | +44 | 98% | +1 809 |
| 9B | `7db1b10` | +39 | 98% | +1 549 |
| 9C | `b668e2f` | +49 | 98% | +2 827 |
| 9D | `9927877` | +66 | 98% | +2 603 |
| 9E | `2c4ef0e` | +29 | 98% | +1 558 |
| 9F | `bcdbdb9` | +48 | 99% | +1 856 |
| 9N | `f227b0b` | +45 | 98% | +2 189 |
| 9G | `8ffc735` | +46 | 98% | +2 315 |
| 9H | `6b83ed7` | +67 | 98% | +2 891 |
| **9R** | `(à venir)` | **+9 (500)** | **98%** | ~+650 + 1 bug fix |

**Total V9 cumulé** : 11 phases, 11 commits, ~23 200 lignes,
**500 tests verts**, 15 ADR (07–21), **1 bug production évité**.

---

## 9. Statut & next-step

```
PHASE 9R : PASS ✅ + bug HandoffOrchestrator.body corrigé
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**Suite logique** :
- **Phase 9J** : Sécurité Enterprise (5h) — RBAC, audit triggers,
  RLS, rate limiting. Permet de wirer 9N en prod.
- **Phase 9P** : Consolidation (FK rétroactives, fusion handoffs).
- **STOP + tag** : la branche est stable, 500 tests verts. Bon moment
  pour mergerver.

**Décision attendue** : poursuivre / changer / STOP.
