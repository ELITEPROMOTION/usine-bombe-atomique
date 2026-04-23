# V5.2 - Rules Classification Report
**Total constantes detectees** : 105

## Distribution
- **HARDCODED_FROZEN** : 4 (3.8%)
- **PARAMETRIZABLE** : 43 (41.0%)
- **LEARNABLE** : 1 (1.0%)
- **REASONABLE** : 57 (54.3%)

## HARDCODED_FROZEN (4 items)
| File | Line | Constant | Value | Justification |
|---|---|---|---|---|
| /app/app/governance/invariants_runtime.py | 42 | `FISCAL_DZ_CONSTANTS` | `{'tva_rate': 0.19, 'tap_rate': 0.02, 'ibs_low_rate': 0.19, '` | token 'fiscal' (regle fiscale/legale) |
| /app/app/governance/invariants_runtime.py | 275 | `EXPECTED_FISCAL_DZ_SIG` | `<unparsed>` | token 'fiscal' (regle fiscale/legale) |
| /app/app/governance/reasoning_canary.py | 46 | `MAX_INVARIANTS_VIOLATED` | `0` | token 'invariant' (regle fiscale/legale) |
| /app/app/intake/requirement_extractor.py | 57 | `COMPLIANCE_HINTS` | `('tva', 'tap', 'cnas', 'irg', 'nin', 'rgpd', 'gdpr', 'hipaa'` | token 'compliance' (regle fiscale/legale) |

## PARAMETRIZABLE (43 items)
| File | Line | Constant | Value | Justification |
|---|---|---|---|---|
| /app/app/autonomy/ambiguity_resolver.py | 62 | `FALSE_AMBIGUITY_CUES` | `['je ne sais pas quoi faire', 'incertain', 'cela depend', 's` | collection numerique -> parametrizable |
| /app/app/autonomy/autonomy_auditor.py | 36 | `HUMAN_LOAD_BUDGET_WEEKLY` | `20` | token 'budget' (seuil/limite) |
| /app/app/autonomy/autonomy_chaos_engine.py | 51 | `SCENARIOS` | `['api_unavailable', 'db_connection_flap', 'tool_regression',` | collection numerique -> parametrizable |
| /app/app/autonomy/autonomy_cost_model.py | 19 | `HOURLY_RATE_USD` | `120.0` | numerique sans mot-cle fiscal -> seuil |
| /app/app/autonomy/autonomy_cost_model.py | 20 | `VALUE_PER_MS` | `0.0001` | numerique sans mot-cle fiscal -> seuil |
| /app/app/governance/drift_detector.py | 29 | `WARNING_THRESHOLD` | `0.15` | token 'threshold' (seuil/limite) |
| /app/app/governance/drift_detector.py | 30 | `WARNING_STRONG_THRESHOLD` | `0.3` | token 'threshold' (seuil/limite) |
| /app/app/governance/drift_detector.py | 31 | `CRITICAL_THRESHOLD` | `0.5` | token 'threshold' (seuil/limite) |
| /app/app/governance/reasoning_canary.py | 43 | `MAX_DIVERGENCE_SHADOW` | `0.3` | numerique sans mot-cle fiscal -> seuil |
| /app/app/governance/reasoning_canary.py | 44 | `MAX_DIVERGENCE_LIMITED` | `0.15` | token 'limit' (seuil/limite) |
| /app/app/governance/reasoning_canary.py | 45 | `MIN_QUALITY_DELTA` | `-0.01` | numerique sans mot-cle fiscal -> seuil |
| /app/app/governance/rules_classifier.py | 33 | `HARDCODED_KEYWORDS` | `['tva', 'tap', 'cnas', 'irg', 'ibs', 'vefa', 'nin', 'dzd', '` | collection numerique -> parametrizable |
| /app/app/governance/rules_classifier.py | 44 | `PARAMETRIZABLE_KEYWORDS` | `['threshold', 'timeout', 'budget', 'ttl', 'max_iteration', '` | collection numerique -> parametrizable |
| /app/app/governance/rules_classifier.py | 50 | `LEARNABLE_KEYWORDS` | `['weight_', 'score_weight', 'coeff', 'prior', 'pass_min', 'c` | collection numerique -> parametrizable |
| /app/app/governance/rules_classifier.py | 56 | `REASONABLE_KEYWORDS` | `['template', 'prompt_variant', 'naming', 'pattern', 'layout'` | collection numerique -> parametrizable |
| /app/app/inbox/meta_optimizer.py | 26 | `DEGRADATION_THRESHOLDS` | `{'avg_duration_ms': 1.3, 'rework_rate': 1.25, 'avg_cost_usd'` | token 'threshold' (seuil/limite) |
| /app/app/intake/ambiguity_detector.py | 18 | `VAGUE_HINTS` | `('\\b(idealement|si possible|plus tard|a voir|tbd|to[- ]be[-` | collection numerique -> parametrizable |
| /app/app/intake/requirement_extractor.py | 54 | `FUNC_HINTS` | `('crud', 'endpoint', 'api', 'cree', 'liste', 'modifie', 'sup` | collection numerique -> parametrizable |
| /app/app/intake/requirement_extractor.py | 56 | `NON_FUNC_HINTS` | `('latence', 'performance', 'uptime', 'sla', 'scalab', 'dispo` | collection numerique -> parametrizable |
| /app/app/intake/requirement_extractor.py | 59 | `SECURITY_HINTS` | `('jwt', 'oauth', 'authentif', 'autorisation', 'rbac', 'mfa',` | collection numerique -> parametrizable |
| /app/app/intake/requirement_extractor.py | 61 | `PERF_HINTS` | `('rps', 'qps', 'debit', 'throughput', 'millisec', 'p95', 'p9` | collection numerique -> parametrizable |
| /app/app/intake/universal_intake.py | 22 | `SUPPORTED_FORMATS` | `('text', 'json', 'yaml', 'csv', 'markdown', 'html', 'pdf', '` | collection numerique -> parametrizable |
| /app/app/orchestration/auto_tuner.py | 26 | `DEFAULT_PASS_MIN` | `0.85` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/auto_tuner.py | 27 | `DEFAULT_CPASS_MIN` | `0.7` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/auto_tuner.py | 28 | `DEFAULT_SOFT_FAIL_MIN` | `0.5` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/auto_tuner.py | 30 | `PASS_BOUNDS` | `(0.8, 0.92)` | collection numerique -> parametrizable |
| /app/app/orchestration/auto_tuner.py | 31 | `CPASS_BOUNDS` | `(0.65, 0.8)` | collection numerique -> parametrizable |
| /app/app/orchestration/auto_tuner.py | 32 | `MIN_SAMPLES` | `5` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/confidence_rollback.py | 27 | `ABSOLUTE_FLOOR` | `0.7` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/confidence_rollback.py | 28 | `RELATIVE_DROP` | `0.15` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/defect_taxonomy.py | 30 | `GRAVITY_LEVELS` | `('info', 'mineure', 'bloquante', 'vitale')` | collection numerique -> parametrizable |
| /app/app/orchestration/impact_analyzer.py | 11 | `DIMENSIONS` | `('structure', 'metier', 'securite', 'runtime', 'conformite',` | collection numerique -> parametrizable |
| /app/app/orchestration/innovation_scout.py | 22 | `STAGES` | `('scout', 'qualification', 'benchmark', 'risk_review', 'pend` | collection numerique -> parametrizable |
| /app/app/orchestration/marketplace.py | 21 | `HEALTHY_MIN_RATE` | `0.9` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/marketplace.py | 22 | `HEALTHY_MIN_SCORE` | `0.75` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/marketplace.py | 23 | `AT_RISK_MIN_RATE` | `0.7` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/marketplace.py | 24 | `AT_RISK_MIN_SCORE` | `0.5` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/marketplace.py | 25 | `NEW_MAX_EXEC` | `2` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/runtime_mesh.py | 31 | `DEFAULT_TOLERANCE` | `0.25` | numerique sans mot-cle fiscal -> seuil |
| /app/app/orchestration/runtime_network_audit.py | 21 | `SUSPECT_IMPORTS` | `('urllib.request', 'httpx', 'requests', 'aiohttp', 'socket',` | collection numerique -> parametrizable |
| /app/app/orchestration/runtime_network_audit.py | 32 | `ALLOWLIST_HOSTS` | `('postgres', 'redis', 'localhost', '127.0.0.1', 'backend', '` | collection numerique -> parametrizable |
| /app/app/orchestration/verification_bundle.py | 24 | `REQUIRED_PROOFS` | `('spec_hash', 'test_proofs', 'security_proofs', 'domain_proo` | collection numerique -> parametrizable |
| /app/app/provisioning/tool_integrator.py | 25 | `OPENAPI_PATHS` | `('/openapi.json', '/swagger.json', '/api-docs', '/v3/api-doc` | collection numerique -> parametrizable |

## LEARNABLE (1 items)
| File | Line | Constant | Value | Justification |
|---|---|---|---|---|
| /app/app/autonomy/autonomy_auditor.py | 33 | `CRITICITY_WEIGHT` | `{'low': 0.5, 'medium': 1.0, 'high': 2.0, 'critical': 4.0}` | token 'weight_' (ajustable par auto-tuner) |

## REASONABLE (57 items)
| File | Line | Constant | Value | Justification |
|---|---|---|---|---|
| /app/app/agents/claude_code_agent.py | 31 | `SYSTEM_PROMPT` | `'Tu es un generateur de code senior. A partir d\'une specifi` | chaine libre (probablement texte/template) |
| /app/app/agents/claude_code_agent.py | 36 | `REFINE_HINT` | `'On te repasse la tache car le reviewer a releve des defauts` | chaine libre (probablement texte/template) |
| /app/app/agents/datadog_agent.py | 56 | `ENDPOINT_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/agents/security_agent.py | 48 | `SECRET_WHITELIST` | `{'example', 'changeme', '<password>', 'password123'}` | type ambigu, decidable plus tard |
| /app/app/agents/security_agent.py | 137 | `DEP_LINE_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/agents/sonarqube_agent.py | 21 | `PENALTY` | `{'HIGH': 0.3, 'MEDIUM': 0.05, 'LOW': 0.005}` | type ambigu, decidable plus tard |
| /app/app/agents/terraform_agent.py | 151 | `RES_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/agents/terraform_agent.py | 152 | `VAR_REF_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/agents/terraform_agent.py | 153 | `VAR_DEF_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/agents/workspace.py | 15 | `DEFAULT_ROOT` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/autonomy/autonomy_cost_model.py | 21 | `CONFIDENCE_TO_RISK` | `{1.0: 0.01, 0.9: 0.05, 0.8: 0.1, 0.7: 0.18, 0.6: 0.28, 0.5: ` | type ambigu, decidable plus tard |
| /app/app/governance/invariants_runtime.py | 95 | `_SECRET_PATTERNS` | `<unparsed>` | token 'pattern' (decidable LLM) |
| /app/app/governance/invariants_runtime.py | 153 | `IRREVERSIBLE_ACTIONS` | `{'schema.drop_table', 'payment.execute', 'prod.rollback', 'a` | type ambigu, decidable plus tard |
| /app/app/governance/parameter_manager.py | 31 | `ALLOWED_ACTORS` | `{'PARAMETRIZABLE': {'ahmed', 'super_admin'}, 'LEARNABLE': {'` | type ambigu, decidable plus tard |
| /app/app/governance/reasoning_boundaries.py | 22 | `REASONING_WHITELIST` | `{'non_critical_ordering', 'response_format', 'ux_copywriting` | type ambigu, decidable plus tard |
| /app/app/governance/reasoning_boundaries.py | 38 | `REASONING_BLACKLIST` | `{'rollback_production', 'schema_modification', 'financial_am` | type ambigu, decidable plus tard |
| /app/app/governance/rules_classifier.py | 26 | `CAT_HARDCODED` | `'HARDCODED_FROZEN'` | chaine libre (probablement texte/template) |
| /app/app/governance/rules_classifier.py | 27 | `CAT_PARAMETRIZABLE` | `'PARAMETRIZABLE'` | chaine libre (probablement texte/template) |
| /app/app/governance/rules_classifier.py | 28 | `CAT_LEARNABLE` | `'LEARNABLE'` | chaine libre (probablement texte/template) |
| /app/app/governance/rules_classifier.py | 29 | `CAT_REASONABLE` | `'REASONABLE'` | chaine libre (probablement texte/template) |
| /app/app/inbox/autonomous_executor.py | 117 | `_ALLOWED_BINARIES` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/intake/ambiguity_detector.py | 24 | `MISSING_ASPECTS` | `{'target_platform': '\\b(linux|windows|docker|kubernetes|aws` | type ambigu, decidable plus tard |
| /app/app/intake/requirement_extractor.py | 95 | `_BULLET_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/intake/requirement_extractor.py | 96 | `_SECTION_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/intake/smart_questionnaire.py | 38 | `_ASPECT_QUESTIONS` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/intake/tool_selector.py | 95 | `_INTEGRATION_RANK` | `{'api': 0, 'sdk': 1, 'cli': 2, 'mcp': 3, 'browser': 4}` | type ambigu, decidable plus tard |
| /app/app/integrations/sonarqube_client.py | 16 | `DEFAULT_URL` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/integrations/vault_client.py | 17 | `_DEFAULT_MOUNT` | `'secret'` | chaine libre (probablement texte/template) |
| /app/app/integrations/vault_client.py | 18 | `_PREFIX` | `'uba'` | chaine libre (probablement texte/template) |
| /app/app/middleware/tenant.py | 27 | `DEFAULT_TENANT` | `'00000000-0000-0000-0000-000000000000'` | chaine libre (probablement texte/template) |
| /app/app/orchestration/confidence_report.py | 56 | `_SECRET_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/confidence_report.py | 59 | `_ENDPOINT_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/contracts.py | 21 | `CONTRACTS_DIR` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/decision_router.py | 37 | `CORRECTABLE_CLASSES` | `{'contract_fix', 'behavior_fix', 'local_fix'}` | type ambigu, decidable plus tard |
| /app/app/orchestration/decision_router.py | 38 | `CRITICAL_CLASSES` | `{'schema_fix', 'security_fix', 'vitale'}` | type ambigu, decidable plus tard |
| /app/app/orchestration/ephemeral_agent.py | 29 | `ALLOWED_TEMPLATES` | `<unparsed>` | token 'template' (decidable LLM) |
| /app/app/orchestration/evidence_ledger.py | 25 | `GENESIS_HASH` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/parallel_critic.py | 23 | `_SECRET_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/parallel_critic.py | 26 | `_ENDPOINT_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/policy_arbiter.py | 43 | `DENY_PATTERNS` | `<unparsed>` | token 'pattern' (decidable LLM) |
| /app/app/orchestration/policy_arbiter.py | 50 | `FOREIGN_ONLY_PATTERNS` | `<unparsed>` | token 'pattern' (decidable LLM) |
| /app/app/orchestration/policy_arbiter.py | 120 | `FABRICATED_FIELD_HINTS` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/policy_arbiter.py | 126 | `LEGAL_HINTS` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/policy_arbiter.py | 161 | `_RULES` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/runtime_network_audit.py | 26 | `SUSPECT_CALLS_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/sensitive_collector.py | 22 | `CATEGORY_AUTO` | `'auto'` | chaine libre (probablement texte/template) |
| /app/app/orchestration/sensitive_collector.py | 23 | `CATEGORY_TOOLS` | `'tools'` | chaine libre (probablement texte/template) |
| /app/app/orchestration/sensitive_collector.py | 24 | `CATEGORY_USER` | `'user_required'` | chaine libre (probablement texte/template) |
| /app/app/orchestration/sensitive_collector.py | 27 | `USER_REQUIRED_PATTERNS` | `('carte bancaire', 'credit card', 'numero de carte', 'cvv', ` | token 'pattern' (decidable LLM) |
| /app/app/orchestration/sensitive_collector.py | 34 | `TOOLS_PATTERNS` | `('cle api', 'api key', 'token', 'secret', 'bearer', 'access_` | token 'pattern' (decidable LLM) |
| /app/app/orchestration/test_manifests.py | 18 | `MANIFESTS_DIR` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/tri_brain.py | 128 | `CRITIC_SYSTEM` | `'Tu es un reviewer senior. On te donne une liste de fichiers` | chaine libre (probablement texte/template) |
| /app/app/orchestration/tri_brain.py | 162 | `_HARDCODED_CRED_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/tri_brain.py | 165 | `_PRINT_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/orchestration/tri_brain.py | 166 | `_ENDPOINT_RE` | `<unparsed>` | type ambigu, decidable plus tard |
| /app/app/routers/websocket.py | 23 | `TERMINAL` | `{'completed', 'cancelled', 'failed'}` | type ambigu, decidable plus tard |
| /app/app/validation/pipeline.py | 51 | `REQUIRED_PATTERNS` | `<unparsed>` | token 'pattern' (decidable LLM) |
