# Test Plan V5.1 — Campagne SDET

## Etat actuel
- 227 tests / 60.3% global / 54.1% P0 / 64.8% P1

## Objectifs cibles
- 95%+ P0 sur autonomy + orchestration critique + security
- 85%+ P1 sur agents + routers + memory
- 75%+ P2 sur self_improver, auto_tuner, cost_optimizer, runtime_mesh
- Global 85%+

## Fixtures requises (nouveau conftest)
- `pool` : asyncpg pool partage (init via init_pool, teardown via close)
- `seeded_task` : cree un task + tenant pour tests RLS
- `vault_stub` : stub in-process VaultClient

## Vague 1 — P0 Autonomy (17 modules, 27 gaps)
**Fichier** : `tests/test_autonomy_v5_1_integration.py`

- autonomy_governor.decide_next : ladder+proof+lease happy path + hard_boundary + low conf
- human_necessity_proof.prove : ambiguity L1/L2/L3 resolve + lease covers + counterfactual + hard
- autonomy_auditor.compute/persist/latest : load_raw empty, full, action_rates, outcomes, patches, chaos, leases
- autonomy_chaos_engine.run_scenario all 6 + run_all
- correlation_id_universal.new_id/register/hop/close/trace
- permission_lease_manager.grant/find_active/consume (cap_exceeded)/revoke/list_active
- hard_boundary_registry.is_hard/check/register/list_all
- intervention_learner.assess (A/B/C paths) + matches_negative + learn_from_recent
- ambiguity_resolver.resolve (L1/L2/L3/L4) + false + self_induced
- credential_vault_universal.lookup (with/without vault) + store + mark_used + TTL expired
- auth_prefetcher.prefetch (vault hit, lease hit, fallback hit, ask)
- autonomy_simulation_lab.replay + grid_search
- calibration_engine.compute + calibrate (with buckets)
- autonomy_cost_model.estimate + best_mode coverage all modes
- autonomy_explainability_api.explain + recent_avoided_escalations

## Vague 2 — P0 Security + DZ
**Fichier** : `tests/test_security_dz_v5_1.py`

- middleware/tenant.py : RLS set current_tenant, fallback anon, reject mismatch
- vault_client.py : is_available, put/get roundtrip, fallback env
- agents/conformite_dz_agent.py : property-based TVA/TAP/CNAS/IRG/NIN/VEFA all 5 tiers
- orchestration/dz_rules.py : seed verify, rule_by_key
- orchestration/evidence_ledger.py : append-only, chain hash, tamper detection
- orchestration/quality_kernel.py : invariants signature SHA-256, no silent override

## Vague 3 — P0 Tri-brain + Routing
**Fichier** : `tests/test_tri_decision_promotion.py`

- tri_brain : Builder/Critic/Judge separation (existing + edge)
- decision_router : 4 branches robust/partial/correctable/critical_fail
- promotion_engine : staging→canary→prod + rollback + freeze
- quorum_judge : 3 instances vote majoritaire + tie_breaker
- policy_arbiter : R1-R7 deny rules

## Vague 4 — P1 Orchestration + Pipeline + Routers
**Fichier** : `tests/test_orchestration_p1.py`

- dag_checkpoint : save/load/resume
- delivery_package : build artifact manifest
- tool_health : probe, mark_unhealthy
- routers/tasks : POST + GET + status transitions
- routers/ahmed_inbox : GET /inbox + /inbox/account + /inbox/blocked
- routers/autonomy : endpoints smoke
- routers/analytics : overview + marketplace
- routers/websocket : connect + disconnect
- inbox/autonomous_executor : write_config, http_call stub, run_shell whitelist
- inbox/meta_optimizer : capture_and_analyze, _detect_degradation
- inbox/continuous_improvement : run_retrospective, pattern_signature

## Vague 5 — P1 Agents + Memory
**Fichier** : `tests/test_agents_memory_p1.py`

- agents individuels : claude_code, linter, pytest, security, readme, docker, terraform, datadog, bootstrap
- memory/memory_engine : recall_similar, store, embeddings
- orchestration/impact_analyzer : rank_by_impact
- orchestration/cost_optimizer : pick tier
- orchestration/auto_tuner : recalibrate quantiles

## Vague 6 — P2 Observability + FinOps
**Fichier** : `tests/test_p2_observability.py`

- runtime_mesh : probe, detect_drift, alert_if_drift (with pool)
- cost_optimizer : suggest_downgrade, budget logic
- auto_tuner : quantile update
- self_improver : propose_patch, risk_score

## Estimation tests a ecrire
- Vague 1: ~60 tests
- Vague 2: ~40 tests (dont property-based hypothesis)
- Vague 3: ~30 tests
- Vague 4: ~40 tests
- Vague 5: ~25 tests
- Vague 6: ~15 tests

**Total attendu** : 227 + ~210 = ~437 tests

## Execution
1. Ajouter fixtures `pool`, `seeded_task`, `vault_stub` dans conftest
2. Ecrire vagues 1-3 en priorite (P0)
3. pytest --cov each wave, verifier gains
4. Vague 4-6 en P1/P2
5. verify_uba 35/35 final
6. Generer coverage_campaign_v5_1_final.md
