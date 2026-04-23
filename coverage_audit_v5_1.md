# Coverage Audit V5.1 — Campagne SDET
**Global** : 79.0% (5615/7110 lignes)
**Branches** : 79
**Tests** : 227 existants


## P0 — 32 fichiers — 91.4% couvert (1867/2042)

### Gaps P0 (N=15)
| Fichier | % | Lignes manquantes | Branches manquantes |
|---|---|---|---|
| app/orchestration/audit_events.py | 57.6% | 56,57,58,67,74,90,91,92,93,94 (+4) | 0 |
| app/middleware/tenant.py | 70.0% | 51,52,53,54,61,62,63,64,65,66 (+5) | 0 |
| app/integrations/vault_client.py | 71.6% | 52,53,58,59,71,72,73,85,90,97 (+9) | 0 |
| app/autonomy/autonomy_explainability_api.py | 81.6% | 44,45,65,72,73,74,75,98,99 | 0 |
| app/autonomy/intervention_learner.py | 82.4% | 39,64,65,66,67,69,78,142,143,166 (+6) | 0 |
| app/autonomy/ambiguity_resolver.py | 83.9% | 90,106,117,118,119,120,128,129,158,191 (+5) | 0 |
| app/orchestration/tri_brain.py | 84.2% | 119,156,179,185,198,231,232,233,234,235 (+14) | 0 |
| app/inbox/user_interaction_router.py | 85.1% | 92,101,105,108,125,126,173,229,230,231 (+7) | 0 |
| app/autonomy/credential_vault_universal.py | 89.8% | 37,38,39,78,79 | 0 |
| app/autonomy/auth_prefetcher.py | 92.0% | 36,49 | 0 |
| app/autonomy/autonomy_auditor.py | 92.8% | 150,157,158,178,179,183,190,297,306,307 | 0 |
| app/orchestration/confidence_scorer.py | 92.9% | 47,101,189,190,191,192,194 | 0 |
| app/orchestration/quorum_judge.py | 93.2% | 58,99,100 | 0 |
| app/autonomy/human_necessity_proof.py | 94.1% | 67,68,74,122 | 0 |
| app/autonomy/autonomy_governor.py | 94.8% | 69,154,155 | 0 |

## P1 — 74 fichiers — 77.1% couvert (3084/3998)

### Gaps P1 (N=36)
| Fichier | % | Lignes manquantes | Branches manquantes |
|---|---|---|---|
| app/routers/websocket.py | 27.6% | 27,28,29,37,38,39,46,53,56,88 (+32) | 0 |
| app/orchestration/tool_health.py | 35.6% | 30,31,32,33,34,35,36,37,38,42 (+19) | 0 |
| app/routers/provisioning.py | 46.2% | 23,24,29,30,31,32,33,38,39,40 (+33) | 0 |
| app/routers/tasks.py | 50.3% | 62,70,103,111,112,117,118,124,129,130 (+64) | 0 |
| app/orchestration/marketplace.py | 52.7% | 41,42,47,48,49,50,51,52,53,54 (+16) | 0 |
| app/routers/analytics.py | 54.4% | 41,42,47,48,53,54,59,60,65,66 (+67) | 0 |
| app/orchestration/ephemeral_agent.py | 54.9% | 55,56,57,58,59,60,61,73,74,78 (+36) | 0 |
| app/orchestration/semantic_cache.py | 55.6% | 27,72,89,90,91,92,93,95,96,110 (+34) | 0 |
| app/orchestration/confidence_rollback.py | 58.1% | 44,45,46,47,54,55,56,67,77,83 (+3) | 0 |
| app/orchestration/compliance_matrix.py | 58.3% | 33,34,52,59,60,69,97,98,106,107 (+5) | 0 |
| app/orchestration/memory_engine.py | 60.6% | 96,119,125,126,146,147,148,152,153,154 (+27) | 0 |
| app/orchestration/escalator.py | 64.0% | 38,39,63,104,119,120,121,137,141,146 (+8) | 0 |
| app/orchestration/prompt_cache.py | 65.0% | 31,42,48,49,50,51,52 | 0 |
| app/orchestration/tool_registry.py | 65.4% | 30,31,45,49,50,57,62,63,68,74 (+8) | 0 |
| app/routers/auth.py | 65.6% | 19,20,25,30,31,32,33,34,35,43 (+1) | 0 |
| app/orchestration/hypotheses_registry.py | 65.7% | 36,37,48,58,59,60,61,72,80,115 (+2) | 0 |
| app/orchestration/delivery_package.py | 66.0% | 46,47,48,65,66,67,68,69,70,71 (+8) | 0 |
| app/inbox/autonomous_executor.py | 66.7% | 39,78,79,80,81,82,84,85,86,87 (+16) | 0 |
| app/orchestration/contracts.py | 67.1% | 44,48,49,50,69,74,75,76,77,78 (+15) | 0 |
| app/validation/level_zero.py | 68.6% | 35,58,60,62,69,80,81,82,83,84 (+17) | 0 |
| app/intake/universal_intake.py | 68.6% | 37,52,53,54,55,56,57,58,59,68 (+33) | 0 |
| app/agents/claude_code_agent.py | 73.1% | 63,64,67,68,77,81,86,104,105,106 (+19) | 0 |
| app/orchestration/prompt_ab.py | 73.7% | 59,60,61,71,72,76,77,78,79,80 | 0 |
| app/inbox/continuous_improvement.py | 80.0% | 78,79,80,81,84,85,86,89,90,91 (+1) | 0 |
| app/agents/security_agent.py | 80.7% | 103,104,111,112,122,123,126,127,128,129 (+6) | 0 |
| app/agents/linter_agent.py | 82.4% | 32,33,51,52,53,55 | 0 |
| app/inbox/forms_generator.py | 82.4% | 90,92,94 | 0 |
| app/orchestration/sensitive_collector.py | 82.4% | 48,69,70,81,87,88,98,110,111 | 0 |
| app/orchestration/test_manifests.py | 82.8% | 30,42,53,55,58,59,60,68,75,103 | 0 |
| app/orchestration/innovation_scout.py | 82.8% | 49,61,97,98,100,101,103,104,105,107 (+1) | 0 |
| app/intake/requirement_extractor.py | 84.0% | 28,44,69,71,73,89,91,110,119,120 (+2) | 0 |
| app/agents/sonarqube_agent.py | 85.1% | 39,40,47,60,61,91,92,93,105,106 | 0 |
| app/orchestration/defect_taxonomy.py | 86.0% | 51,57,71,72,73,86,119 | 0 |
| app/agents/pytest_agent.py | 86.0% | 40,41,79,82,83,84 | 0 |
| app/orchestration/confidence_report.py | 86.8% | 67,68,102,115,116,117,143,144,149,150 (+2) | 0 |
| app/agents/bootstrap_agent.py | 87.5% | 24 | 0 |

## P2 — 4 fichiers — 67.4% couvert (223/331)

### Gaps P2 (N=2)
| Fichier | % | Lignes manquantes | Branches manquantes |
|---|---|---|---|
| app/orchestration/runtime_mesh.py | 54.7% | 44,65,66,67,68,69,70,72,73,81 (+52) | 0 |
| app/orchestration/auto_tuner.py | 64.9% | 44,63,64,80,81,88,89,91,102,103 (+10) | 0 |

## P3 — 15 fichiers — 59.7% couvert (441/739)

### Gaps P3 (N=3)
| Fichier | % | Lignes manquantes | Branches manquantes |
|---|---|---|---|
| app/provisioning/tool_integrator.py | 28.6% | 37,46,47,48,49,50,51,52,53,60 (+45) | 0 |
| app/worker.py | 34.3% | 50,51,54,55,56,60,73,74,75,85 (+107) | 0 |
| app/provisioning/tool_provisioner.py | 43.2% | 45,46,47,51,58,59,61,62,65,70 (+11) | 0 |
