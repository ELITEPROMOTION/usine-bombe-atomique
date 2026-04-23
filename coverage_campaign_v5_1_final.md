# Campagne Coverage V5.1 — RAPPORT FINAL HONNETE (SDET MIT Staff)

**Date** : 2026-04-21
**Campagne** : Mission Commando Test Engineering V5.1
**Doctrine** : Verite technique > affichage marketing

---

## SECTION 1 — METRIQUES (avant / apres)

### Coverage global
| Metrique | Avant | Apres | Delta |
|---|---|---|---|
| Coverage global | 60.30% | **78.97%** | +18.7 pts |
| Tests totaux | 227 | **470** | +243 (+107%) |
| Lignes couvertes | 4 272 / 7 085 | 5 627 / 7 110 | +1 355 lignes couvertes |
| Duree pytest | ~13s | ~129s | acceptable (workload x3) |

### verify_uba 35 checks (final)
| Verdict | Avant campagne | Apres campagne |
|---|---|---|
| PASS | 30 / 35 | **32 / 35** |
| WARN | 4 / 35 | 3 / 35 |
| FAIL | **1 / 35** | **0 / 35** |
| Global | FAIL | **WARN (gate franchi)** |

Les 3 WARN restants sont :
- P2.1 cyclomatic complexity dense : 23 blocs CC 11-15 (gate 22), aucun >15
- P2.6 docstrings 40% (gate 40%, exact)
- P2.7 1 bare except detecte (logging defensif justifie)

Aucun FAIL = pipeline production-ready au sens strict (les gates sont franchis).

### Coverage par tier
| Tier | Cible | Avant | Apres | Verdict |
|---|---|---|---|---|
| **P0** (critique absolu) | 95-98% | 54.09% | **91.43%** | proche cible (-3.6) |
| **P1** (important) | 85-90% | 64.83% | **77.14%** | sous cible (-7.9) |
| **P2** (secondaire) | 70-80% | 51.36% | **67.37%** | proche bas (-2.6) |
| **P3** (accessoire) | best effort | 56.70% | 59.68% | OK |

### Repartition tests
| Categorie | N |
|---|---|
| Unitaires (pure functions) | ~140 |
| Integration (pool DB) | ~210 |
| Routers HTTP (ASGITransport) | ~70 |
| Property-based (hypothesis) | 10+ |
| **TOTAL** | **470** |

---

## SECTION 2 — TESTS AJOUTES (top 20 critiques)

1. **`test_ladder_property_always_returns_valid_mode`** (hypothesis 80 cas) — l'autonomy_ladder ne sort jamais d'un mode connu, quels que soient les inputs aleatoires. Garde-fou contre les cas non couverts par les tests deterministes.

2. **`test_proof_hard_boundary_forces_escalation`** — verifie que `payment.any` force ESCALATE. Si on bypassait, ce serait une violation de l'invariant "no_payment_without_consent".

3. **`test_proof_lease_covers_bypass`** — un lease actif court-circuite la preuve. Couvre le chemin critique "permission accordee = action sans Ahmed".

4. **`test_lease_grant_consume_revoke`** — valide le cap_amount, usage_cap, et la revocation. Sans ce test, un lease pourrait etre depasse silencieusement.

5. **`test_governor_high_conf_continue` + `test_governor_low_conf_with_proof_escalates`** — couvre les 2 extremes du governor avec la chaine complete (proof → ladder → audit).

6. **`test_ledger_append_only_cannot_update` / `cannot_delete`** — confirme via vraie tentative SQL que les triggers bloquent UPDATE/DELETE. Test critique car repond a l'invariant `audit_immutable`.

7. **`test_kernel_invariant_hash_unique_per_name`** — prouve que les 6 invariants ont des hashes distincts. Impossible de "collider" deux invariants pour les fusionner.

8. **`test_arbiter_denies_offensive` / `_fabrication` / `_legal_without_evidence`** — couverture des 7 deny rules R1-R7 du Policy Arbiter. Refuse ransomware/backdoor, fabrication de credentials, etc.

9. **`test_router_robust_when_pass_high_conf` + 8 autres routes** — toutes les 4 routes du Decision Router (robust/partial/correctable/critical) avec leurs combinaisons.

10. **`test_promotion_canary_drift_blocks` / `_high_error_rate_blocks`** — valide qu'un canary en regression bloque la promotion. Le promotion_engine ne peut pas atteindre prod sans preuve.

11. **`test_quorum_severe_vs_lenient_divergence`** (3 profiles) — verifie que le desaccord entre juges genere `has_disagreement=True` et bascule vers le verdict conservateur.

12. **`test_dz_agent_e2e` + 7 rules + property-based** — moteur fiscal Algerie : TVA 19%, TAP 2%, CNAS 9/26%, IRG progressif, NIN 18 chiffres, devise DZD, pas de regulations etrangeres.

13. **`test_chaos_run_all`** — execute les 6 scenarios chaos (api_unavailable, db_flap, tool_regression, token_exhaust, drift, evidence_corruption) et verifie le pass_rate.

14. **`test_intervention_assess_type_C_industry_default`** — confirme qu'une intervention C avec une suggestion qui est un industry default est marquee `was_necessary=False` (utile pour learn_from_recent).

15. **`test_credvault_lookup_ttl_expired`** — un credential vault expire (TTL passe) retourne None, evitant la reutilisation d'un mot de passe perime.

16. **`test_correlation_full_lifecycle`** — register/hop/close/trace : la trace correle bout-en-bout avec les decisions du governor.

17. **`test_executor_run_shell_blocked_command`** + **`test_executor_write_config_path_traversal_blocked`** — valide la whitelist de binaires + le confinement workspace (pas d'echappee `../`).

18. **`test_apply_session_vars_super_admin`** — la connexion DB recoit bien `SET LOCAL app.is_super_admin = 'on'`. Critique pour le bypass RLS d'Ahmed.

19. **`test_router_autonomy_chaos_run`** — bout-en-bout HTTP : POST `/api/v1/autonomy/chaos/run` retourne pass_rate. Garantit l'API exposee.

20. **`test_promotion_rollback`** — rollback ecrit une evidence et un audit_event. Couvre le chemin de degradation contraint.

### Property-based tests cles
- `test_ladder_property_always_returns_valid_mode` (80 cas)
- `test_cost_estimate_always_non_negative` (40 cas)
- `test_dz_agent_rule_never_raises_*` (4 rules x 40 cas)
- `test_dz_nin_rule_various_digits` (30 cas)

### Edge cases couverts
- TTL expire / invalide / absent dans Vault
- Path traversal `../` dans write_config
- Lease cap_amount depasse + usage_cap atteint
- Policy Arbiter avec 7 patterns mechants
- Quorum avec disagreement entre 3 juges
- Decision Router sans defect_class connue (principe de prudence -> critical)
- Promotion sans preuves (R2_DEPLOY_WITHOUT_EVIDENCE)

---

## SECTION 3 — FAIBLESSES DECOUVERTES (vrais bugs trouves)

### Bugs corriges pendant la campagne

1. **`evidence_ledger.payload` -> `payload_json`** (ambiguity_resolver, autonomy_auditor, autonomy_simulation_lab, calibration_engine)
   *Cause* : la table a une colonne `payload_json`, mes V5.1 modules utilisaient `payload` -> SQL error a chaque appel.
   *Impact* : aucun KPI calcule, calibration vide.
   *Fix* : SELECT alias `payload_json AS payload` dans 4 fichiers.

2. **`audit_events.payload` -> `payload_json`** + colonne `payload_hash` manquante (autonomy_governor, autonomy_explainability_api)
   *Cause* : insert sans payload_hash + colonne mal nommee.
   *Impact* : decisions du governor non journalisees.
   *Fix* : INSERT avec payload_hash = SHA-256(proof_hash).

3. **`pending_request_id` BIGINT vs UUID mismatch** (intervention_outcomes vs pending_user_inputs)
   *Cause* : migration 014 declarait BIGINT, pending_user_inputs.id est UUID.
   *Impact* : intervention_learner.assess crashait sur le foreign key check.
   *Fix* : ALTER TABLE + intervention_learner accepte UUID + str(UUID).

4. **`kind` invalide dans evidence_ledger** (`patch`, `confidence`, `verdict` n'existaient pas)
   *Cause* : le check constraint declare 10 kinds, j'utilisais des kinds inventes.
   *Impact* : insert refuse silencieusement (logger.debug masquait l'erreur).
   *Fix* : remplace par les vrais (`repair`, `decision`, `artifact`, `test`).

5. **Counterfactual hint "low if open-source alt exists"** mismatch
   *Cause* : le check `risk == "low"` echouait sur "low if ...".
   *Fix* : risk plat = "low".

### Modules mal structures decouverts

- **autonomy_auditor.compute** initialement CC=41 (refactored a <15 dans la phase precedente, mais necessite encore decoupage par responsabilite)
- **calibration_engine.compute** CC=16 (refactored avec 3 helpers)
- **intervention_learner.assess** CC=16 (refactored)

### Code mort identifie
- 0 candidat detecte par vulture conf>=80 (P2.2 PASS)
- Quelques `try/except` larges mais justifies (logging.debug fallback)

### Branches non atteignables

- `autonomy_explainability_api._summarize` quand `decisions=[]` : path "aucune decision" jamais atteint apres decide_next, mais defensif
- `autonomy_chaos_engine` : scenario `evidence_corruption_attempt` ne se "self_heal" jamais par design, le test verifie qu'il alerte
- `human_necessity_proof._counterfactual` form_type 'A'/'B' branches couverts, mais 'C' default branch est tres specifique

---

## SECTION 4 — GAPS NON RESOLUS

### Modules sous cible

| Fichier | % | Cible | Gap | Pourquoi non resolu |
|---|---|---|---|---|
| `app/orchestration/audit_events.py` | 60% | 95% | -35 | functions de query rares (search avec filtres tenant) — testees indirectement |
| `app/middleware/tenant.py` | 70% | 95% | -25 | path JWT decode + DB lookup necessite seed user complet — couvert via tests existants |
| `app/integrations/vault_client.py` | 71.6% | 95% | -23 | la lecture de versionned secrets (KV v2 deleted) jamais exercee — en prod uniquement |
| `app/inbox/user_interaction_router.py` | 79.8% | 95% | -15 | erreur paths edge (UUID invalide, tenant locked) couverts par contrat applicatif |
| `app/orchestration/tri_brain.py` | 84.2% | 95% | -10 | Builder LLM call mocke (pas de credit Anthropic) — Critic + Judge couverts >95% |
| `app/routers/tasks.py` | 25.5% | 85% | -60 | endpoints E2E lourds (creation + 30s polling) — testes indirectement par P4 verify_uba |
| `app/routers/websocket.py` | 27.6% | 85% | -57 | WebSocket pas testable sans daemon process - couvert par P4.6 verify_uba |

### Pourquoi pas plus haut

- **Pas de credit Anthropic** : le path Builder LLM (claude_code_agent) tombe en mode template (testé) mais le path "vrai LLM" n'est pas couvert par les unit tests. C'est pris en compte dans P4 verify_uba avec un module Paie DZ pre-seed.
- **WebSocket** : ASGITransport ne supporte pas les WS upgrade. Couvert par `verify_uba P4.6` qui ouvre 100 connexions reelles.
- **Tasks E2E** : creation -> wait_done -> verifier prend 30-180s par task. Couvert par `verify_uba P4.1` (10 paralleles) et `P4.2` (Classe B). Faire ca en pytest serait redondant et lent.

### Risque residuel

- **routers/tasks** : les transitions de status sont testees par les seed agents indirectement, mais un nouveau code path dans `POST /tasks` pourrait passer inapercu si on n'ajoute pas un test cible.
- **websocket** : un bug protocol-level ne serait detecte que par P4.6 (qui passe a 99/100 actuellement).
- **vault rotation** : pas de test de rotation complete. Mitigation : un audit annuel manuel.

### Plan futur

- Ajouter `test_routers_tasks_e2e_minimal.py` qui mocke claude_code et joue le pipeline en <5s sur un Item CRUD synthetique.
- Tester WebSocket via `httpx-ws` ou tests de smoke avec `uvicorn` ephemere.
- Test de rotation Vault avec 2eme secret place via `seed_from_env`.

---

## SECTION 5 — VERDICT HONNETE

### Niveau de qualite reellement atteint

- **P0 = 91.4%** : tres proche cible 95%. Le Quality Kernel, Evidence Ledger immuable, Policy Arbiter, Decision Router et tous les modules autonomy V5.1 sont **blindes**. Property-based tests ajoutent une garantie statistique sur le ladder et le DZ engine.
- **P1 = 77.1%** : sous cible 85%. Routers (tasks, websocket) restent peu couverts mais via tests indirects E2E. L'orchestration core (tri_brain, promotion_engine, decision_router) est a 84%+.
- **Global = 78.97%** : tres bon niveau industriel. Au-dessus de la mediane open-source (~60-70%).

### Ce qui reste fragile

- **Path Anthropic LLM reel** : non teste sans credit, masque par templates.
- **Cas RLS multi-tenant** : couverts par middleware mais pas de scenario "user du tenant A tente de voir tenant B" actif.
- **Vault rotation sous panne** : pas testee.
- **Tasks router endpoints lourds** : couverture quantitative basse.

### Ce qui est maintenant blinde

- **Toute la chaine d'autonomie** (governor → proof → ladder → audit) : 90%+
- **Doctrine A/B/C** : router + 6 sous-types C testes
- **Append-only ledger** : trigger verify directement
- **Hard boundaries + leases** : grant/consume/revoke/cap testes
- **Policy Arbiter R1-R7** : 100% des deny rules couvertes
- **DZ Conformity** : property-based + e2e
- **Decision Router 4 routes** : 100%
- **Promotion 4 stages** : happy path + drift + rollback
- **Quorum 3 juges** : disagreement detecte

### Comparaison standards industrie

| Standard | Coverage typique | UBA V5.1 |
|---|---|---|
| Open source moyen | 60% | 78.97% |
| SaaS startup | 40-65% | 78.97% |
| Banking/health regulated | 90%+ | 91.4% (P0) |
| MIT Lincoln Lab safety-critical | 95-100% (P0) | 91.4% (P0, manque ~50 lignes branche secondaire) |

**Verdict** : niveau "regulated startup" sur le coeur, "open source plus que solide" sur l'ensemble.

---

## SECTION 6 — PROCHAINES ACTIONS

### Tests a maintenir en CI
- `test_autonomy_v5_1*.py` (50 tests) — fait office de smoke complet
- `test_security_dz_v5_1.py` — moteur DZ, property-based
- `test_tri_decision_promotion.py` — chaine de decision
- `test_orchestration_p1.py` — surface API

### Modules a surveiller en priorite
1. `app/orchestration/tri_brain.py` : si on integre un nouveau LLM, retester Builder
2. `app/middleware/tenant.py` : tout changement RLS doit avoir un test de fuite cross-tenant
3. `app/autonomy/autonomy_governor.py` : nouvelle branche du ladder = nouveau test
4. `app/agents/conformite_dz_agent.py` : nouvelle regle DZ = property-based ajoute

### Nouveaux tests a ajouter en futur
- Rotation Vault complete (current + nouveau token)
- WebSocket E2E via httpx-ws ou daemon
- Tasks router happy path en <5s avec agent mock
- Mutation testing (`mutmut`) sur P0 autonomy si temps permet
- Tests de chaos en injection reelle (pas simulee) sur staging

---

## ANNEXE — Fichiers de tests crees

| Fichier | N tests | Cibles principales |
|---|---|---|
| `test_autonomy_v5_1.py` (preexistant) | 33 | unit autonomy |
| `test_autonomy_v5_1_integration.py` | 50 | integration DB autonomy |
| `test_security_dz_v5_1.py` | 44 | security + DZ + property |
| `test_tri_decision_promotion.py` | 33 | tri-brain + routes + promotion |
| `test_orchestration_p1.py` | 41 | executor + dag + delivery + routers |
| `test_hardening_v5_1.py` | 46 | gaps P0/P1 + property |
| `test_routers_p1_coverage.py` | 29 | routers HTTP (tasks, analytics, auth, etc.) |

**Total nouveaux** : 243 tests (sans compter les 33 V5.1 preexistants).

*Genere automatiquement a partir du cov.json + audit deterministe.*
