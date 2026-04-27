# Audit livrable UBA — V8.5 phase A

Date : 2026-04-27
Sample : `generated/dendani-residences/` (CDC mini-market type Classe A, projet `9d20b484-5089-4366-9d6e-d1f37fa45fc4` mentionné par le run pipeline).
Score validation observé : **67.7%** (PASS minimal mais Tests à 0%).

## 1. Symptôme

Pipeline UBA livre le projet avec `validation_score = 0.677` :

| Niveau | Score | Pondération | Contribution |
|--------|-------|-------------|--------------|
| 1. Cohérence logique (AST parse) | 1.000 | 20% | 0.200 |
| 2. Conformité CDC (4 fichiers) | 1.000 | 20% | 0.200 |
| 3. Qualité (Lint+Sonar) | 0.885 | 20% | 0.177 |
| **4. Tests (Pytest)** | **0.000** | **30%** | **0.000** |
| 5. Production ready | 1.000 | 10% | 0.100 |
| **Total** | | | **0.677** |

`agent-04-pytest` retourne `score=0.0, tests_total=0, tests_passed=0`.
Pourtant : pytest exécuté manuellement dans `generated/dendani-residences/` retourne **46/46 PASS**.

## 2. Reproduction du bug

Commande exacte de l'agent (`backend/app/agents/pytest_agent.py:58-66`) :

```python
env_cmd = ["pytest", str(root), "-q",
           "--json-report", f"--json-report-file={report_path}",
           "--no-header"]
```

Reproduction sans `pytest-json-report` installé :

```
$ python -m pytest -q --json-report --json-report-file=.pytest_report.json
ERROR: usage: __main__.py [options] [file_or_dir] ...
__main__.py: error: unrecognized arguments: --json-report --json-report-file=.pytest_report.json
exit code: 4
```

Conséquence côté agent (`pytest_agent.py:32-44`) :
- `report = _load_report(report_path)` → `None` (fichier non créé)
- `summary = {}` → `total = 0, passed = 0, failed = 0, errors = 0`
- `collected = 0` (key absente du report inexistant)
- Branche `if total == 0 and collected == 0` → `score = 0.0, ok = False`

## 3. Root cause précise

**Cause directe** : le plugin `pytest-json-report` n'est pas systématiquement disponible dans l'environnement où `pytest_agent` exécute la commande.

Quatre sources de fragilité, par ordre d'impact :

### 3a. Template `_generate_template()` (mode fallback sans Anthropic)

`backend/app/agents/claude_code_agent.py:297` génère un `requirements.txt` ne contenant PAS pytest du tout :

```python
requirements = "fastapi==0.115.0\nuvicorn[standard]==0.32.0\npydantic==2.9.2\nhttpx==0.27.2\n"
```

Si le worker est configuré pour créer un venv par projet et y installer les requirements, pytest n'est pas dans ce venv → la commande `pytest` échoue avant même de lire les flags.

### 3b. SYSTEM_PROMPT (mode Anthropic)

`backend/app/agents/claude_code_agent.py:31-34` :

```
"Contraintes : code ruff-clean, tests pytest dans tests/, requirements.txt, README.md."
```

Le prompt ne demande pas explicitement `pytest-json-report` ni `pytest-cov`. Le modèle ajoute en général `pytest`/`pytest-asyncio` mais ignore les plugins. C'est exactement le cas du livrable dendani-residences (cf. `generated/dendani-residences/requirements.txt` original).

### 3c. `pytest_agent.py` n'a aucun fallback

Si `--json-report` échoue, l'agent ne retombe pas sur un parsing du stdout. Il rapporte 0/0 silencieusement.

### 3d. `pytest_agent.py` ne logue pas le stderr complet

La trace `unrecognized arguments` n'est conservée que sur les 500 derniers caractères (`stderr_tail`). Si le pipeline ne propage pas ce champ jusqu'au dashboard, le diagnostic est invisible.

## 4. Pattern reproductible

Oui, **systématique** dès lors que :

1. `pytest-json-report` n'est pas dans le venv où la commande `pytest` est résolue, OU
2. Le modèle Anthropic produit un `requirements.txt` sans le plugin, et le worker lance pytest dans un venv project-local après `pip install -r requirements.txt`.

Vérifié manuellement : sur Windows host, `python -m pip uninstall pytest-json-report` puis re-run reproduit instantanément `score=0.0`.

## 5. Impact

- **Tous** les livrables Classe A en mode fallback template sont à 0% Tests.
- Les livrables Classe A/B en mode Anthropic sont à 0% **sauf si** le modèle inclut spontanément `pytest-json-report` (rare — il l'a fait pour ~aucun de nos test runs).
- Le `validation_score` global plafonne à **0.70** au lieu de 1.0 même si le code est parfait → projets refusés ou en CONDITIONAL_PASS.

## 6. Solution proposée — défense en profondeur (4 couches)

| Couche | Action | Bénéfice |
|--------|--------|----------|
| 1. Template fallback | Ajouter `pytest`, `pytest-asyncio`, `pytest-json-report`, `pytest-cov` à `requirements.txt` du template | Mode fallback robuste |
| 2. SYSTEM_PROMPT | Ajouter contrainte explicite "requirements.txt DOIT inclure : pytest, pytest-asyncio, pytest-json-report, pytest-cov" | Mode Anthropic robuste |
| 3. pytest_agent | Détecter "unrecognized arguments" et fallback sur parsing stdout `X passed, Y failed` | Résilience même si plugin absent |
| 4. Quality Gates | Vérifier explicitement avant livraison : pytest PASS, coverage ≥ 70%, Docker build OK, README complet | Refus de livrer un projet cassé |

Couches 1+2 corrigent la cause. Couches 3+4 garantissent qu'on ne re-tombe jamais dans ce trou.

## 7. Evidence

- Reproduction commande : `audit_v85/evidence/repro_uninstall.txt`
- Pytest passing après fix : `audit_v85/evidence/repro_fixed.txt`
- Source agent buggy : `backend/app/agents/pytest_agent.py:32-55`
- Source template buggy : `backend/app/agents/claude_code_agent.py:297`
