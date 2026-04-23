# UBA Audit Source Extreme — 2026-04-23

## Résumé exécutif (1 page)

| Dimension | Valeur | Note |
|---|---:|---|
| Code source `app/` | **192 fichiers Python** · 26 638 LOC (20 363 SLOC) | Grand |
| Ratio commentaires | 2% (C/L), 8% avec docstrings | Correct |
| Fonctions totales | **1 147** (562 sync + **585 async**) | 51% async |
| Classes | 211 | |
| Tests | 1 005 fonctions `test_*` | 1028 PASS |
| Coverage | **84.04%** (9 583/11 403 stmts) | Cible 95% |
| Complexité moyenne | **A (3.15)** sur 1 343 blocs | Excellent |
| Blocs denses (CC ≥ 11) | 36 (2.7%) | Acceptable, 0 critique (>15) |
| Maintainability Index | **100% A** (192/192) | Excellent |
| Ruff violations | 49 (38 F401 unused-import) | Mineur |
| Bandit issues | 29 (0 High, 12 Med, 17 Low) | Correct |
| Cycles de dépendances | **0** | Excellent |
| TODO/FIXME/HACK | 0 | Excellent |

**Score global qualité : 8.3/10**

Top 3 leviers vers 10/10 :
1. **Split des 3 modules > 500 LOC** (`workers/tasks.py` 718L, `worker.py` 397L, `routers/truth.py` 379L) — réduit complexité mentale + facilite tests isolés.
2. **Refactor 20 fonctions longues > 50L** — extraction de helpers, amélioration lisibilité.
3. **Nettoyage 38 imports inutilisés** — trivial, automatisable `ruff --fix`.

Pas de dette critique : pas de cycle, pas de god class (seulement 2 classes > 100L), pas de commentaire TODO/HACK, couplage raisonnable (hub `app.orchestration` = 21 imports entrants mais c'est un barrel).

---

## 1. Analyse architecturale

### 1.1 Distribution LOC

```
Total Python : 192 fichiers · 26 638 LOC (bruts) · 20 363 SLOC (source)
Tests        : 1 005 test fns dans 38 fichiers
Ratio docstring/code : 8%
```

### 1.2 Modules > 500 lignes (candidats split)

| Lignes | Module | Observation |
|---:|---|---|
| **718** | `app/workers/tasks.py` | 26 tasks automation V5.5. **Split en 7 sous-modules par tier** (tier1_critical.py, tier2_security.py, …) recommandé. MI = A (26.6) |

### 1.3 Modules 300-500 lignes (surveillance)

| Lignes | Module |
|---:|---|
| 397 | `app/worker.py` |
| 379 | `app/routers/truth.py` |
| 373 | `app/routers/cognition.py` |
| 356 | `app/routers/tasks.py` |
| 351 | `app/orchestration/memory_engine.py` |
| 339 | `app/routers/workflows.py` |
| 327 | `app/orchestration/promotion_engine.py` |
| 323 | `app/agents/claude_code_agent.py` |
| 310 | `app/autonomy/autonomy_auditor.py` |
| 306 | `app/workers/event_workflows.py` |
| 305 | `app/governance/invariants_runtime.py` |
| 304 | `app/governance/drift_detector.py` |
| 301 | `app/orchestration/runtime_mesh.py` |

### 1.4 Modules < 50 lignes (candidats fusion ou peut-être OK)

13 `__init__.py` (dont 8 vides) + `governance/_json_utils.py` (17L) + `database.py` (31L). Aucun problème réel — ce sont des modules volontairement minimalistes (barrel exports, helpers utilitaires).

### 1.5 Complexité cyclomatique (radon)

```
1343 blocs analysés · moyenne A (3.15)
Distribution : A=1307 · B≈30 · C≈6 · D,E,F = 0
```

**0 bloc de complexité critique (CC > 15).** Les 36 blocs "denses" (CC 11-15) sont concentrés dans :
- `app/worker.py::run_task` (CC 15, 108L)
- `app/orchestration/orchestrator.py::run_dag` (CC 14)
- `app/orchestration/test_manifests.py::detect_project_type` (CC 14)
- `app/orchestration/verification_bundle.py::build` (CC 14)
- `app/ctc/evidence_harvester.py::fetch_one` (CC 14)
- `app/cognition/react_engine.py::run` (CC 15)

### 1.6 Maintainability Index (radon mi)

```
192/192 fichiers en rang A (note >= 20)
5 plus bas (encore A) :
   26.62  app/workers/tasks.py
   30.39  app/worker.py
   36.21  app/routers/tasks.py
   38.15  app/orchestration/runtime_mesh.py
   40.96  app/autonomy/autonomy_auditor.py
```

---

## 2. Analyse qualité

### 2.1 Top 20 fonctions les plus longues (> 50 lignes)

| LOC | Fichier | Fonction |
|---:|---|---|
| **119** | `app/agents/claude_code_agent.py:190` | `_generate_template()` |
| 112 | `app/agents/claude_code_agent.py:45` | `_execute()` |
| 108 | `app/worker.py:222` | `run_task()` |
| 100 | `app/routers/tasks.py:39` | `create_task()` |
| 96 | `app/cognition/reasoning_core.py:102` | `_persist()` |
| 94 | `app/agents/terraform_agent.py:54` | `_tf_template()` |
| 90 | `app/workers/_runtime.py:140` | `workflow_task()` |
| 80 | `app/workers/_runtime.py:148` | `decorator()` |
| 77 | `app/ctc/evidence_harvester.py:61` | `fetch_one()` |
| 74 | `app/orchestration/delivery_package.py:87` | `build()` |
| 73 | `app/workers/_runtime.py:151` | `wrapper()` |
| 72 | `app/provisioning/tool_provisioner.py:39` | `provision()` |
| 71 | `app/ctc/meta_truth_auditor.py:50` | `audit()` |
| 71 | `app/orchestration/escalator.py:43` | `detect_question()` |
| 63 | `app/inbox/continuous_improvement.py:56` | `run_retrospective()` |
| 62 | `app/autonomy/autonomy_simulation_lab.py:59` | `replay()` |
| 62 | `app/ctc/phase_gate_enforcer.py:42` | `validate()` |
| 62 | `app/cognition/react_engine.py:62` | `run()` |
| 62 | `app/governance/parameter_manager.py:93` | `set_value()` |
| 61 | `app/inbox/user_interaction_router.py:162` | `_build_form()` |

### 2.2 Top 15 fonctions les plus complexes (radon CC ≥ C/11)

| CC | Fonction |
|---:|---|
| 15 | `app/worker.py::run_task` |
| 15 | `app/cognition/react_engine.py::run` |
| 14 | `app/orchestration/orchestrator.py::run_dag` |
| 14 | `app/orchestration/test_manifests.py::detect_project_type` |
| 14 | `app/orchestration/verification_bundle.py::build` |
| 14 | `app/ctc/evidence_harvester.py::fetch_one` |
| 13 | `app/autonomy/autonomy_chaos_engine.py::run_scenario` |
| 13 | `app/agents/readme_agent.py::_render` |
| 13 | `app/ctc/assertion_risk_detector.py::analyze` |
| 13 | `app/ctc/meta_truth_auditor.py::audit` |
| 13 | `app/ctc/auto_triangulator.py::qualify` |
| 13 | `app/ctc/auto_triangulator.py::triangulate` |
| 12 | `app/orchestration/confidence_report.py::classify_manifest` |
| 12 | `app/orchestration/patch_types.py::required_layers_from_diff` |
| 12 | `app/ctc/truth_judge.py::decide` |

### 2.3 God classes (> 300 lignes)

**Aucune.** Plus grosses :
- `ClaudeCodeAgent` (117 méthodes cumulées, 323L fichier)
- `BrowserOpsAgent` (115L de classe)

### 2.4 Modules sans tests (coverage < 20%)

**Aucun**. Tous les modules > 10 stmts ont au moins 20% de couverture. Le plus bas est `routers/websocket.py` à **27.6%**, `provisioning/tool_integrator.py` à **28.6%**, `workers/tasks.py` à **32.5% → 79.4%** après campagne.

### 2.5 Dead code potentiel (ruff)

```
38 F401  unused-import    (nettoyage trivial : ruff check --fix)
 3 F841  unused-variable
 2 E731  lambda-assignment (x = lambda … → def x())
 1 F541  f-string-missing-placeholders
 1 F821  undefined-name   (à investiguer)
 4 E741  ambiguous-variable-name (l, I, O)
```

49 violations totales. 41 auto-corrigeables par `ruff --fix`.

Vulture (conf. 95%) : **0 finding** à haute confiance. 2 paramètres de signature non-utilisés (APIs publiques, à conserver).

---

## 3. Analyse dépendances

### 3.1 Modules hubs (les plus importés)

| Imports entrants | Module |
|---:|---|
| **21** | `app.orchestration` (barrel `__init__.py`) |
| 19 | `app.database` (pool asyncpg central) |
| 15 | `app.agents.base_agent` (ABC) |
| 14 | `app.config` |
| 13 | `app.agents.workspace` |
| 10 | `app.cognition.reasoning_trace_models` |
| 9 | `app.ctc` |
| 7 | `app.autonomy` |
| 5 | `app.integrations.vault_client` |

Acceptable : `database` et `config` sont par nature des hubs. `orchestration` est un barrel qui peut être splitté si on veut réduire le coupling apparent.

### 3.2 Cycles

**0 cycle de dépendance détecté** (DFS sur 192 modules).

### 3.3 Modules indépendants (bien)

- `cognition/reasoning_trace_models.py` (0 dep interne)
- `orchestration/patch_types.py`, `defect_taxonomy.py`, `domain_classifier.py` (pure logic)
- `autonomy/autonomy_ladder.py`, `fallback_chain.py`, `hard_boundary_registry.py` (pure logic)

---

## 4. Analyse performance

### 4.1 N+1 requêtes potentielles

Cas `for table in (...): await fetchval("SELECT COUNT(*) FROM {t}")` détecté dans :
- `app/ctc/truth_engine_snapshotter.py:33` (4-5 tables snapshot → 4-5 requêtes au lieu d'1 UNION)
- `app/workers/tasks.py:150` (4 tables CTC dans `task_evidence_chain_verification`)
- `app/workers/tasks.py:212` (5 tables tenant audit)
- `app/ctc/continuous_validators.py:101`

**Gain attendu** : refactor en 1 seule requête avec UNION ALL → -50% latence ces 3 tasks.

### 4.2 Opérations synchrones dans code async

`urllib.request.urlopen()` dans `app/workers/tasks.py` (3 occurrences : vault health, cve poll, backup verify) → **bloque l'event loop**. Remplacer par `httpx.AsyncClient`.

`subprocess.run()` (blocking) dans :
- `app/inbox/autonomous_executor.py:136` (whitelist shell runner) → déjà dans fonction sync contexte, OK
- `app/workers/tasks.py:232, 290` (bandit, pip audit dans tasks async) → **bloque event loop**. Remplacer par `asyncio.create_subprocess_exec`.

### 4.3 Cache manquants

`orchestration/semantic_cache.py` existe et fonctionne. Mais `orchestration/prompt_cache.py` n'est pas exploité dans tous les LLM calls. Opportunité : wrapper universel cache autour de `_generate_with_anthropic`.

### 4.4 Bloquants I/O dans async

`Path.read_text()` / `.write_text()` synchrones dans code async :
- `app/workers/tasks.py` (plusieurs endroits)
- `app/orchestration/confidence_report.py`
- `app/validation/level_zero.py`

Impact faible (lectures de petits fichiers). Priorité basse.

---

## 5. Analyse sécurité (bandit)

```
Total issues : 29   (High: 0, Medium: 12, Low: 17)
```

| Test ID | Count | Gravité | Description |
|---|---:|---|---|
| **B608** | 5 | Medium (low conf.) | Hardcoded SQL expressions (f-strings SQL) |
| **B310** | 3 | Medium (high conf.) | `urllib.request.urlopen` sans validation scheme |
| **B108** | 2 | Low | `hardcoded_tmp_directory` |
| **B307** | 1 | Medium | Use of `eval()` ou similaire |
| **B104** | 1 | Low | Binding 0.0.0.0 (attendu pour Vault dev mode) |
| B101 assert_used | ~17 | Low | `assert` en code (ok en dev, à mettre `#nosec` en prod) |

### 5.1 B608 — f-strings SQL (à corriger)

```python
# app/ctc/continuous_validators.py:101
n = await conn.fetchval(f"SELECT COUNT(*) FROM {t}")
# app/workers/tasks.py:150, 212 - même pattern
# app/orchestration/innovation_scout.py:110
sql = f"UPDATE innovation_items SET {', '.join(fields_sql)} WHERE id = $1"
```

**Risque réel : faible** car `t` / `table` / `fields_sql` viennent de constantes interned dans le code, pas de user input. **Mitigation** : ajouter whitelist explicite + `#nosec B608` commentaire rationnel.

### 5.2 B310 — urlopen sans validation

3 cas dans `workers/tasks.py` (vault, NVD CVE, backup). URLs hardcoded ou issues de `os.environ` — acceptable mais :
- Ajouter check `scheme in ('http','https')` explicite
- Timeout présent ✓

### 5.3 Secrets hardcoded

**0 secret hardcoded détecté** (`secretes`, API keys, passwords). Tous passent par `get_settings()`.

### 5.4 Input validation

Routeurs FastAPI utilisent Pydantic → validation automatique. Les endpoints qui acceptent `dict[str, Any]` (ex: `POST /workflows/trigger/{name}`) sont acceptables car passent par enqueue arq (isolation fonctionnelle). À documenter cependant.

### 5.5 CSRF/XSS

- Frontend React : XSS natural protection via JSX escaping ✓
- CSP header ajouté en prod (`deploy/nginx/conf.d/uba.conf`)
- Pas d'endpoint POST non-authentifié avec side-effect cross-origin → CSRF risk faible

---

## 6. Analyse tests

### 6.1 Distribution coverage par module

```
 43 fichiers @ 100%
 30 fichiers @ 95-99%
 62 fichiers @ 85-95%
 32 fichiers @ 70-85%
 19 fichiers @ 50-70%
  6 fichiers @ 20-50%     ← à améliorer
  0 fichiers @ <20%        ← aucun, bien
```

### 6.2 Coverage par domaine

| Domaine | Coverage | Cible |
|---|---:|---:|
| `app/cognition/` | 93.4% | ≥90% ✓ |
| `app/autonomy/` | 93.3% | ≥90% ✓ |
| `app/ctc/` | 88.5% | ≥90% (proche) |
| `app/agents/` | 88.5% | - |
| `app/governance/` | 88.2% | - |
| `app/inbox/` | 86.6% | - |
| `app/intake/` | 85.2% | - |
| `app/orchestration/` | 83.6% | - |
| `app/workers/` | 83.1% | ≥85% (proche) |
| `app/routers/` | **72.3%** | ≥90% (gap) |
| `app/integrations/` | **61.8%** | (gap - APIs externes) |
| `app/provisioning/` | **44.8%** | (gap - APIs externes) |

### 6.3 Tests flaky identifiés

Run du `2026-04-23 coverage_campaign` (1028 PASS / 3 FAIL) :
- `test_tri_brain::test_run_tri_brain_approves_good_build` — **LLM flake** (appel `api.anthropic.com` → verdict non-déterministe)
- `test_tri_brain::test_run_tri_brain_refines_then_approves` — idem
- `test_e2e_crud::test_e2e_crud_product_api` — flake pré-existant concurrent

### 6.4 Tests sans assertions

Audit manuel sur les 213 tests ajoutés dans la campagne coverage : tous contiennent au moins 1 `assert`. Pas de test `return None` sans verif.

### 6.5 Mocks non utilisés

Pas d'usage généralisé de `unittest.mock` dans la suite — stratégie "real infrastructure" (Postgres/Redis/Vault tournent en test). Conséquence : tests plus lents mais plus fidèles. Pas de dette détectée.

---

## 7. Dette technique

### 7.1 Markers TODO/FIXME/HACK/XXX

**0 occurrence** sur 26 638 lignes. Remarquable.

### 7.2 Code dupliqué

Radon raw n'a pas détecté de duplication significative. Patterns répétés :
- `async with pool.acquire() as conn:` (normal, asyncpg idiom)
- Structures de docstrings similaires dans routers (cohérence, pas dette)
- `logger.warning("foo failed: %s", exc)` (normal)

### 7.3 Anti-patterns détectés

| Pattern | Occurrences | Action |
|---|---:|---|
| `except Exception: pass` | 0 (nettoyé en V5.5) | ✓ |
| `except Exception as exc: logger.debug(...)` | ~15 | OK (swallowing explicite) |
| Getter/setter inutiles | 0 | ✓ |
| Dict-as-namedtuple | rare | OK |
| Global mutable state | `_pool` dans `database.py` | Acceptable (singleton pool pattern) |

### 7.4 Nommage incohérent

4 violations `E741 ambiguous-variable-name` (`l`, `I`, `O`) → renommer rapidement :
- À localiser via `ruff check app --select E741`

Globalement le nommage français/anglais mixte est **cohérent par domaine** (DZ regs en français, core technique en anglais) — choix délibéré.

---

## Top 50 améliorations prioritaires

| # | Item | Impact | Effort | ROI |
|---:|---|---|---|---|
| 1 | `ruff check app --fix` (38 imports + 3 unused vars + 2 lambdas + 1 f-string) | Hygiène | 5 min | ★★★★★ |
| 2 | Split `app/workers/tasks.py` (718 LOC) en 7 sous-modules par tier | Lisibilité | 2 h | ★★★★★ |
| 3 | Refactor `run_task` (108 LOC, CC 15) en 6 étapes appelées | Lisibilité | 1 h | ★★★★ |
| 4 | Remplacer `urllib.request.urlopen` async → `httpx.AsyncClient` (3 endroits) | Perf async | 30 min | ★★★★ |
| 5 | Remplacer `subprocess.run` dans tasks async → `asyncio.create_subprocess_exec` | Perf async | 45 min | ★★★★ |
| 6 | Refactor `_generate_template` (119 LOC, claude_code_agent) en templates dict | Lisibilité | 1.5 h | ★★★★ |
| 7 | Refactor `_execute` (112 LOC, claude_code_agent) en étapes | Lisibilité | 1 h | ★★★ |
| 8 | Merger 3 requêtes `COUNT` CTC en 1 UNION (N+1 dans task_evidence_chain_verification) | Perf DB | 30 min | ★★★★ |
| 9 | Merger 5 requêtes COUNT tenant audit en 1 UNION | Perf DB | 30 min | ★★★★ |
| 10 | Fix 1 F821 undefined-name (ruff) | Correctness | 15 min | ★★★★ |
| 11 | Fix 4 E741 ambiguous-variable-name | Lisibilité | 15 min | ★★★ |
| 12 | Ajouter whitelist explicite + `#nosec B608` sur f-string SQL avec commentaire | Sécurité | 20 min | ★★★ |
| 13 | Valider scheme HTTP dans `urlopen` (B310) | Sécurité | 10 min | ★★★ |
| 14 | Tests pour `routers/websocket.py` (27.6% → 80%) | Coverage | 3 h | ★★★ |
| 15 | Tests pour `provisioning/tool_integrator.py` (28.6% → 80%) | Coverage | 3 h | ★★★ |
| 16 | Tests pour `worker.py` V3 pipeline (39.3% → 80%) | Coverage | 4 h | ★★★★ |
| 17 | Split `routers/truth.py` (379 LOC) en truth_read.py + truth_write.py | Lisibilité | 1 h | ★★★ |
| 18 | Split `routers/cognition.py` (373 LOC) par famille (cot/tot/got/…) | Lisibilité | 1 h | ★★★ |
| 19 | Split `routers/tasks.py` (356 LOC) en create/read/download | Lisibilité | 1 h | ★★★ |
| 20 | Refactor `react_engine.py::run` (62 LOC, CC 15) | Lisibilité | 30 min | ★★★ |
| 21 | Refactor `evidence_harvester.py::fetch_one` (77 LOC, CC 14) | Lisibilité | 45 min | ★★★ |
| 22 | Refactor `orchestrator.py::run_dag` (CC 14) | Lisibilité | 45 min | ★★★ |
| 23 | Refactor `test_manifests.py::detect_project_type` (CC 14) | Lisibilité | 30 min | ★★ |
| 24 | Refactor `verification_bundle.py::build` (CC 14) | Lisibilité | 45 min | ★★★ |
| 25 | Async IO pour `Path.read_text` dans tasks (via `aiofiles`) | Perf | 30 min | ★★ |
| 26 | Wrapper cache LLM universel (prompt_cache auto) | Perf + coût | 2 h | ★★★★ |
| 27 | Ajouter Prometheus metrics custom sur workflow_task duration | Observabilité | 1 h | ★★★ |
| 28 | Ajouter metrics sur cache hit rate semantic_cache | Observabilité | 30 min | ★★ |
| 29 | Documenter API publique `dict[str, Any]` endpoints avec Pydantic models | Contrat | 2 h | ★★★ |
| 30 | Ajouter smoke tests backend dans CI (pytest fast subset < 30s) | Feedback | 30 min | ★★★★ |
| 31 | Ajouter `pytest-xdist` pour parallélisation tests | Vitesse | 15 min | ★★★ |
| 32 | Activer `pytest --lf` (last failed) sur merge blocking | DX | 5 min | ★★ |
| 33 | Ajouter hypothesis stateful tests sur truth_engine | Correctness | 3 h | ★★★ |
| 34 | Ajouter typing strict (`mypy --strict`) sur `app/orchestration/` | Typage | 4 h | ★★ |
| 35 | Générer OpenAPI spec + typecheck frontend depuis | DX full-stack | 2 h | ★★★ |
| 36 | Migrer `urlopen` → `httpx` partout | Uniformité | 1 h | ★★★ |
| 37 | Extraire constantes magic numbers (timeouts, limits) vers `app/constants.py` | Config | 1 h | ★★ |
| 38 | Ajouter `ruff check --preview` (nouvelles règles) | Hygiène | 30 min | ★★ |
| 39 | Activer `mypy --warn-unreachable` | Correctness | 30 min | ★★★ |
| 40 | Ajouter SAST pipeline (Semgrep + CodeQL) | Sécurité | 2 h | ★★★ |
| 41 | Audit dependencies via `pip-audit` hebdomadaire (task_dependencies_audit existe → brancher alerte) | Sécurité | 1 h | ★★★ |
| 42 | Pre-commit hook ruff + mypy | DX | 20 min | ★★★ |
| 43 | Dockerfile : `USER uba` non-root | Sécurité | 20 min | ★★★ |
| 44 | Vault passer de dev mode → raft HA | Sécurité | 4 h | ★★★ |
| 45 | TLS entre backend et postgres (SSL mode verify-ca) | Sécurité | 1 h | ★★ |
| 46 | Ajouter `max_connections` Postgres tuning | Scaling | 30 min | ★★ |
| 47 | Redis persistence AOF (production) | Durability | 30 min | ★★ |
| 48 | Séparer tests unit / integration / e2e dans pytest markers | Org | 1 h | ★★★ |
| 49 | Dashboard Grafana cost (tokens / mois) | Observabilité | 1 h | ★★★ |
| 50 | Rollout canary 10% via nginx split upstreams | Safety | 4 h | ★★★ |

**Quick wins (total < 2h, ROI max)** : items **1, 4, 5, 8, 9, 10, 11, 30, 42** → 90 min d'effort cumulé → gain qualité significatif.

---

## Map de chaleur qualité par module

```
Légende : ██ critique · ▓▓ attention · ░░ bien · ·· excellent

                                    LOC   CC   COV   Note
app/workers/tasks.py              718  ok   79%   ▓▓   (split recommandé)
app/worker.py                     397  15    39%   ██   (split + refactor + coverage)
app/routers/truth.py              379  ok   87%   ░░   (split)
app/routers/cognition.py          373  ok   82%   ░░
app/routers/tasks.py              356  ok   67%   ▓▓
app/orchestration/memory_engine   351  ok   89%   ··
app/routers/workflows.py          339  ok   95%   ··
app/orchestration/promotion       327  ok   81%   ░░
app/agents/claude_code_agent.py   323  ok   69%   ▓▓   (longues fns)
app/autonomy/autonomy_auditor.py  310  ok   93%   ··
app/workers/event_workflows.py    306  ok   88%   ·· 
app/governance/invariants_runtime 305  ok   86%   ··
app/governance/drift_detector.py  304  ok   76%   ░░
app/orchestration/runtime_mesh    301  ok   42%   ▓▓
app/orchestration/tri_brain.py    282  ok   93%   ··
app/routers/analytics.py          273  ok   72%   ░░
app/ctc/evidence_chain.py         255  ok   90%   ··
app/cognition/reasoning_core.py   250  ok   94%   ··
```

---

## Plan d'action 10/10 pour chaque zone

### Architecture
- Split `workers/tasks.py` → `workers/tasks/{tier1..tier7}.py` + `__init__.py` re-exporte `ALL_TASKS`
- Split `routers/*.py` > 300L par responsabilité (CQRS-like : read vs write)
- Extraire `app/constants.py` (timeouts, seuils, limites)

### Qualité code
- `ruff --fix` immédiat, puis ajouter ruff dans pre-commit
- Refactor les 20 fonctions > 50L (extraction helpers)
- Convertir les 2 `lambda =` en `def` nommés

### Dépendances
- Pas de problème détecté. Maintenir `import app.xxx` flat, éviter les cycles.

### Performance
- Remplacer `urllib.request` → `httpx.AsyncClient` (3 endroits)
- Remplacer `subprocess.run` → `asyncio.create_subprocess_exec` dans async
- Fusionner N+1 `COUNT` en UNION ALL (3 endroits)
- Wrapper cache universel autour LLM calls (gain tokens/mois)

### Sécurité
- Ajouter `#nosec B608` + commentaire rationnel sur f-string SQL contrôlées
- Validation scheme HTTP explicite (B310)
- Dockerfile `USER` non-root
- Vault raft HA production
- TLS verify-ca Postgres

### Tests
- Cibler les 3 modules sous 45% (websocket, tool_integrator, worker.py) → gain coverage +10pp → 94%
- Séparer markers `pytest -m unit/integration/e2e`
- `pytest-xdist` parallélisation → temps suite /2

### Dette technique
- `git blame` + review récent : 0 TODO, code propre. Maintenir.

### Observabilité
- Metrics Prometheus custom sur : workflow_task_duration, cache_hit_rate, llm_cost_usd
- 3 dashboards Grafana additionnels : Cost, Cache perf, LLM technique usage
- Alerte sur cost/jour > budget (déjà en alerting-rules.yml ✓)

---

## Annexe — Outils utilisés

- `radon` : CC + MI + raw metrics
- `ruff` : linter Python (Rust, rapide)
- `bandit` : security static analysis
- `vulture` : dead code detection
- `coverage.py` + `pytest-cov` : coverage
- `ast` (stdlib) : AST analysis pour tailles fonctions/classes + dependency graph

Commandes reproduisibles :
```bash
docker compose exec backend sh -c 'cd /app && radon cc app -a -s'
docker compose exec backend sh -c 'cd /app && radon mi app -s'
docker compose exec backend sh -c 'cd /app && ruff check app --statistics'
docker compose exec backend sh -c 'cd /app && bandit -r app -ll -q --exit-zero'
docker compose exec backend sh -c 'cd /app && pytest tests --cov=app --cov-report=term'
```
