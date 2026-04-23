# Coverage Gap Analysis - UBA (2026-04-23)

**Etat courant** : 80.6% (9191 / 11403 statements, 2212 manquants)
**Objectif** : 95%+ (besoin de +1628 statements couverts)

Tests : 807 PASS + 3 FAIL pre-existants (2 tri_brain LLM flakes, 1 test_e2e_crud_product_api flake)

## Top 20 modules par impact (statements non couverts)

| Impact | % | Lines | Fichier | Priorite |
|---:|---:|---:|---|---|
| **238** | 32.5% | 354 | `app/workers/tasks.py` | **P1** |
| 117 | 34.3% | 178 | `app/worker.py` | P1 |
| 77 | 54.4% | 169 | `app/routers/analytics.py` | P1 |
| 73 | 50.3% | 149 | `app/routers/tasks.py` | P1 |
| 62 | 54.7% | 137 | `app/orchestration/runtime_mesh.py` | P2 |
| 61 | 54.5% | 134 | `app/provisioning/browser_ops_agent.py` | P2 |
| 55 | 28.6% | 77 | `app/provisioning/tool_integrator.py` | P1 |
| 50 | 56.5% | 115 | `app/workers/event_workflows.py` | P1 |
| 46 | 54.9% | 102 | `app/orchestration/ephemeral_agent.py` | P2 |
| 44 | 55.6% | 99 | `app/orchestration/semantic_cache.py` | P2 |
| 43 | 46.2% | 80 | `app/routers/provisioning.py` | P2 |
| 42 | 68.6% | 137 | `app/intake/universal_intake.py` | P2 |
| 42 | 27.6% | 58 | `app/routers/websocket.py` | P2 |
| 37 | 60.6% | 94 | `app/orchestration/memory_engine.py` | P2 |
| 33 | 51.5% | 68 | `app/ctc/truth_explainability_api.py` | P3 |
| 33 | 52.2% | 69 | `app/integrations/sonarqube_client.py` | P3 |
| 30 | 76.4% | 127 | `app/governance/drift_detector.py` | P3 |
| 29 | 82.0% | 167 | `app/routers/cognition.py` | P3 |
| 29 | 35.6% | 45 | `app/orchestration/tool_health.py` | P3 |
| 28 | 73.1% | 108 | `app/agents/claude_code_agent.py` | P3 |

**Somme top 20 = 1,149 statements recuperables** (~10% de coverage gain).

## Plan de rattrapage

### Phase 2 - Unit tests P1 (~560 statements)
- `tests/test_workers_tasks_unit.py` : couvrir les 26 tasks de V5.5 (happy path + error path + audit)
- `tests/test_worker_unit.py` : pipeline run_task, persist, auto_optim, router
- `tests/test_routers_coverage_boost.py` : analytics + tasks + provisioning endpoints
- `tests/test_tool_integrator_unit.py` : provisioning tool_integrator

### Phase 3 - Integration tests
- `tests/test_integration_autonomy_flow.py`
- `tests/test_integration_truth_chain.py`
- `tests/test_integration_cognitive_reasoning.py`
- `tests/test_integration_automation_workflows.py`

### Phase 4 - Edge cases endpoints
- Auth failure, rate limiting, invalid payload, timeout, rollback sur endpoints principaux

### Phase 5 - Migrations
- `tests/test_migrations_integrity.py` : schema + consistency post-migration

### Phase 6 - Property tests (hypothesis)
- `tests/test_properties.py` : invariants DZ, consent, parsers

### Phase 7 - Dead code
- Ciblage via vulture + rapports coverage branches 0

### Estimation gains

| Phase | Nouveaux tests | Statements | Nouveau coverage |
|---|---:|---:|---:|
| Baseline | 807 | - | 80.6% |
| +P2 | +150 | +560 | ~85.5% |
| +P3 | +50 | +250 | ~87.7% |
| +P4 | +80 | +300 | ~90.4% |
| +P5 | +30 | +100 | ~91.2% |
| +P6 | +40 | +200 | ~93.0% |
| +P7 (remove) | - | -200 stmts | reduit denominateur |
| **Final estime** | **~1,150** | **+1,410** | **~93-95%** |

Le chemin realiste vers 95% passe par les 20 top modules + nettoyage du dead code.
