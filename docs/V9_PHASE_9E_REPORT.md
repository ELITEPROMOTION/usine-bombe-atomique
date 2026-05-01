# V9 Phase 9E — Handoff Orchestrator unifié — Final Report

**Date** : 2026-04-30
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9D)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9E livre un orchestrateur de handoffs **transverse**, au-dessus du
framework `direct_links` (9A). Couvre tous les types d'interventions humaines
hors service activation (review livrable, paiement, validation domaine,
escalation custom). State machine stricte, callbacks de résolution, bridge
inbox (stub) — le `handoff_kyc_orchestrator` 9-BOOT reste en place pour
service activation (legacy).

| Indicateur | Valeur | Cible |
|---|---|---|
| Modules livrés | 4 (orchestrator, state_machine, inbox_bridge, types) | 4 |
| Migration | 046_handoff_orchestrator.sql + view v_handoff_open | 1 |
| Tests Phase 9E | 29 / 29 ✅ | toutes passent |
| Tests cumulés (9-BOOT + 9A + 9B + 9C + 9D + 9E) | **285 / 285** ✅ | toutes |
| Coverage Phase 9E | **100%** sur tous les modules | ≥ 90% |
| Coverage critique (orchestrator + state_machine) | **100% / 100%** | ≥ 99% |
| Coverage cumulée | **98%** | ≥ 90% |
| Ruff | 0 erreur (3 autofix imports) | 0 |
| Bandit (≥ Medium) | 0 issue | 0 |
| Auto-fix loop | 0 itération | ≤ 3 |
| Appels externes payants | 0 | 0 |

---

## 2. Livrables

### 2.1 Modules (`backend/app/saas_factory/handoff/`)

| Fichier | LOC | Coverage |
|---|---|---|
| `__init__.py` | 35 | **100%** |
| `state_machine.py` | 75 | **100%** |
| `inbox_bridge.py` | 50 | **100%** |
| `orchestrator.py` | 290 | **100%** |

### 2.2 Migration

**046_handoff_orchestrator.sql** — table `handoff_requests` (UUID, project_id,
action_type, state, target_email, locale, **direct_link_id FK→direct_links**,
payload_json, title, body, cta_url, expires_at, reminders_sent, resolved_at,
resolution_payload_json, created_at, updated_at) + 5 indexes + view
`v_handoff_open` (handoffs ouverts par projet) + seal evidence_ledger.

### 2.3 Tests (`backend/tests/saas_factory/test_handoff.py`)

29 tests :

- **State machine (4)** : terminal states no transitions, valid transitions,
  invalid transitions, is_terminal helper
- **Inbox bridge (1)** : LoggingInboxBridge records posts
- **Orchestrator request (2)** : creates handoff with link, unknown
  action_type rejected
- **Orchestrator transitions (8)** : notify sets state + posts inbox,
  notify unknown handoff raises, invalid transition raises, idempotent
  noop, acknowledge invalid link, link without target, invalid UUID target,
  notify already-notified raises
- **Orchestrator resolve (5)** : consume + callback, callback exception
  doesn't break resolve, link not consumed, unknown handoff, register
  callback unknown action_type
- **Orchestrator ops (5)** : escalate, cancel with reason, tick counts,
  get unknown raises, get parses string payloads
- **Edge cases (3)** : acknowledge handoff-not-found, resolve invalid UUID,
  transition idempotent silent noop on advanced state
- **Helper (1)** : `_row_to_request` with dict payloads

### 2.4 Docs

- `docs/V9_PHASE_9E_REPORT.md` (ce fichier)
- `docs/V9_ARCHITECTURE_DECISIONS.md` — ADR-14 nouvelle

---

## 3. Architecture

### 3.1 State machine

```
    REQUESTED ──► NOTIFIED ──► ACKNOWLEDGED ──► RESOLVED
        │            │              │
        │            └──► EXPIRED ◄─┘
        │            │
        │            └──► ESCALATED ──► RESOLVED
        │            │
        ▼            ▼
                CANCELLED
```

- États terminaux : RESOLVED, EXPIRED, CANCELLED (aucune transition sortante)
- Transitions strictement validées au niveau `_transition()`
- `allow_idempotent=True` (utilisé par `acknowledge()`) → silent noop
  si état déjà avancé, plutôt que `InvalidTransitionError`

### 3.2 Pipeline de bout en bout

```
1. orchestrator.request()
       └─► DirectLinkGenerator.issue() (9A)
       └─► INSERT handoff_requests (state=REQUESTED)
       └─► UPDATE direct_links.target_id = handoff_id
       └─► retourne HandoffRequest avec issued_token (1-shot)

2. orchestrator.notify(handoff_id)
       └─► state -> NOTIFIED
       └─► InboxBridge.post(InboxItem) si configuré

3. user clique sur le magic link → handler /handoff/<token>
       └─► orchestrator.acknowledge(token)
              └─► ValidationEngine.validate (9A)
              └─► state -> ACKNOWLEDGED (idempotent)

4. user complete l'action → handler POST /handoff/<token>/resolve
       └─► orchestrator.resolve(token, payload)
              └─► ValidationEngine.consume (9A, atomique)
              └─► state -> RESOLVED + UPDATE resolved_at
              └─► ResolutionCallback enregistre est appele
              └─► Exception du callback ne casse pas le resolve

5. orchestrator.tick() (job Arq periodique)
       └─► escalate les handoffs > escalation_after sans resolution
       └─► expire ceux dont expires_at est passe
```

### 3.3 Resolution callback registry

`register_resolution_callback(action_type, async_callable)` permet à
l'orchestrateur **upstream** de Phase 9C/9D de réagir à la résolution
d'un handoff. Exemple : quand `payment_confirm` est résolu, déclencher
le provisioning Hostinger (Phase 9G).

L'orchestrateur garantit :
- Le callback est appelé **après** la transition DB → RESOLVED (atomique)
- Une exception du callback est loggée mais ne fait pas échouer `resolve()`
- L'`action_type` doit exister dans le `Catalog` 9A (validation au register)

### 3.4 Coexistence avec `handoff_kyc_orchestrator` (9-BOOT)

**Pas de fusion** dans cette phase. Les deux coexistent :

| | Phase 9-BOOT (`handoff_kyc_orchestrator`) | Phase 9E (`HandoffOrchestrator`) |
|---|---|---|
| Table | `handoff_pending` (magic_link_token inline) | `handoff_requests` (FK direct_link_id) |
| Scope | Service activation (Cloudflare, Stripe, ...) | Tout le reste (review, paiement, domaine, custom) |
| State machine | Implicite (status enum) | Explicite (`HandoffState` + transitions validées) |
| Tokens | `secrets.token_urlsafe(32)` direct | Via `DirectLinkGenerator` (9A) |
| Callbacks | Aucun | Registry `register_resolution_callback` |
| Inbox | Logging info logger | `InboxBridge` Protocol injectable |

ADR-14 documente le choix de coexistence + plan de migration unifiée en
Phase 9P.

---

## 4. Conformité aux contraintes

| Contrainte | Respect |
|---|---|
| Master plan #5 (Handoff KYC orchestrator) | ✅ couvert par 9-BOOT (legacy) |
| Phase 9E (Handoff Orchestrator transverse) | ✅ livré |
| Couverture critique ≥ 99% | ✅ 100% partout |
| Couverture globale ≥ 90% | ✅ 100% Phase 9E, 98% cumulé |
| Aucun appel externe payant | ✅ Inbox bridge stub |
| Pas de tag autonome | ✅ |
| Aucune régression | ✅ 285/285 cumulés |
| Conventional commit | ✅ |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (285 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (0 erreur, 3 autofix) |
| bandit -ll | ✅ PASS (0 issue Medium+) |
| coverage critique ≥ 99% | ✅ PASS (100%) |
| coverage globale ≥ 90% | ✅ PASS (98%) |
| Aucun appel externe payant | ✅ |
| Aucun secret en clair | ✅ |

---

## 6. Limitations & dette technique

- **InboxBridge stub** : la `LoggingInboxBridge` ne fait que logger.
  L'intégration réelle avec `app/inbox/` (V4.8 BLOC 1, table `ahmed_inbox`)
  ou Slack arrivera quand on câblera l'admin dashboard (Phase 9N).
- **Pas de retry sur les callbacks** : si le `ResolutionCallback` échoue,
  on log et on continue. Pour une exécution garantie (e.g. déclencher
  provisioning), il faudra wrapper le callback dans un job Arq idempotent
  (Phase 9Q).
- **Reminders programmés mais pas implémentés** : `tick()` gère
  escalation et expiration mais pas les rappels intermédiaires (1h/12h).
  Le compteur `reminders_sent` est incrémenté lors d'escalation seulement.
  Le `handoff_kyc_orchestrator` 9-BOOT a ces rappels — peut être étendu
  ici en Phase 9P.
- **Pas d'enforcement réel des transitions** : la validation est cliente
  (Python) ; un trigger Postgres BEFORE UPDATE bloquerait les transitions
  invalides en cas de bug. À ajouter en Phase 9J (Sécurité Enterprise).
- **handoff_requests n'a pas de RLS** : multi-tenant strict viendra en
  Phase 9J.
- **Pas d'endpoint FastAPI** : le router HTTP est en Phase 9N (admin).

---

## 7. État cumulé V9 sur la branche

| Phase | Commit | Tests | Coverage | LoC |
|---|---|---|---|---|
| 9-BOOT | `bba1fa1` | 58 | 97% | +2 970 |
| 9A | `71896b1` | +44 (102) | 98% | +1 809 |
| 9B | `7db1b10` | +39 (141) | 98% | +1 549 |
| 9C | `b668e2f` | +49 (190) | 98% | +2 827 |
| 9D | `9927877` | +66 (256) | 98% | +2 603 |
| **9E** | `(à venir)` | **+29 (285)** | **98%** | ~+1 200 |

**Total V9 cumulé estimé** : 6 phases, 6 commits, ~13 000 lignes ajoutées,
**285 tests verts**, 8 ADR (07–14), critique 100% partout.

---

## 8. Statut & next-step

```
PHASE 9E : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**Suite logique** :
- **Phase 9F** : Client Onboarding 6 étapes (5h) — pendant client du
  `setup_wizard` 9B. Créera **enfin** la table `projects` et permettra
  d'ajouter les FK rétroactives sur intelligence_qualifications/pricings/
  assemblies + project_progression + handoff_requests.
- **Phase 9R** : Tests E2E (5h) — câble bout-en-bout 9C+9D+9E avec mocks.
- **Phase 9N** : Dashboard Admin Ahmed (4h) — endpoints FastAPI pour
  setup wizard + handoffs + AI cost dashboard + intelligence engine.

**Décision attendue** : poursuivre 9F / 9N / 9R, ou STOP.
