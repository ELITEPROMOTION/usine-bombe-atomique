# Rapport de verification UBA

**Statut global :** `FAIL`
**Duree :** 929.6 s
**Phases :** 5

## Phase 1 · Verification par module

- Statut : `FAIL`
- Score : 78.6%
- Duree : 616.1 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P1.1 AST parse (backend) | `PASS` | 4.22s | 196 fichiers analyses, 0 erreur(s) |
| P1.2 Pytest + coverage (gate 50%) | `FAIL` | 600.11s | pytest rc=-1, couverture=0.0% |
| P1.3 Ruff + Bandit | `WARN` | 8.71s | ruff=128, bandit(high)=0, bandit(total)=25 |
| P1.4 mypy (lenient) | `PASS` | 0.02s | 0 erreur(s), 0 critique(s) (call-arg/arg-type/assignment/return-value) |
| P1.5 OpenAPI contract | `PASS` | 0.82s | 175 endpoints declares, 0 requis manquants |
| P1.6 Imports coherence (app.*) | `PASS` | 2.52s | 61 modules 'app.*' references, 0 introuvables |
| P1.7 CDC DZ conformity (8 regles) | `PASS` | 0.01s | 8/8 regles presentes |

## Phase 2 · Verification par ligne

- Statut : `WARN`
- Score : 71.4%
- Duree : 20.9 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P2.1 Cyclomatic complexity (gate CC>15, dense<22) | `WARN` | 2.48s | 1343 blocs, 36 dense (11-15), 0 trop complexe (>15) |
| P2.2 Dead code (vulture conf>=80) | `WARN` | 6.24s | 6 candidat(s) de code mort |
| P2.3 Secrets hardcodes | `PASS` | 2.72s | 0 secret(s) suspect(s) detecte(s) |
| P2.4 Conventions nommage | `PASS` | 2.15s | 0 violation(s) naming |
| P2.5 Duplications de fonctions | `PASS` | 3.03s | 0 cluster(s) de duplications |
| P2.6 Docstrings publiques (gate 40%) | `WARN` | 2.19s | 317/816 fonctions publiques documentees (39%) |
| P2.7 Gestion erreurs (bare except / except pass) | `WARN` | 2.15s | 2 pattern(s) douteux |

## Phase 3 · Cross-validation

- Statut : `PASS`
- Score : 100.0%
- Duree : 1.4 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P3.1 Coherence front <-> back | `PASS` | 0.03s | 0 ecart(s) |
| P3.2 BDD <-> models <-> migrations | `PASS` | 0.13s | 96 tables, 0 manquantes |
| P3.3 Agents <-> registry <-> DAG | `PASS` | 1.07s | catalog=24 real=11 dag=10 |
| P3.4 Config <-> env.example <-> compose | `PASS` | 0.05s | 39 cles .env.example, 0 ecart(s) |
| P3.5 Pipeline <-> scoring <-> verdicts | `PASS` | 0.08s | LEVEL_WEIGHTS=1.0 conf=1.0 |
| P3.6 Memoire <-> benchmarks <-> cost | `PASS` | 0.04s | 7/7 modules presents |
| P3.7 Securite bout-en-bout | `PASS` | 0.02s | 5/5 controles OK |

## Phase 4 · Stress

- Statut : `WARN`
- Score : 92.9%
- Duree : 290.8 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P4.1 10 Classe A paralleles | `PASS` | 163.71s | 10/10 completed, 10/10 termines |
| P4.2 Classe B complet (Paie DZ profond) | `WARN` | 125.00s | status=failed score=0.7 |
| P4.3 Logique rework / raffinement | `PASS` | 0.03s | refine=True rework_count_schema=True |
| P4.4 Fallback Anthropic timeout / quota | `PASS` | 0.02s | template_fn=True exception_handler=True |
| P4.5 DB + analytics sous charge | `PASS` | 0.05s | health=200 overview=200 marketplace=200 |
| P4.6 WebSocket 100 connexions | `PASS` | 1.94s | 100/100 ouvertes, 100 premiers messages recus |
| P4.7 Injection SQL + XSS + prompt | `PASS` | 0.17s | 3 injections testees, 0 probleme(s) |

## Phase 5 · V4.2 Quality Gates

- Statut : `PASS`
- Score : 100.0%
- Duree : 0.3 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P5.1 V4.2 modules (24+5) | `PASS` | 0.12s | 29/29 modules presents |
| P5.2 Test manifests (4 types) | `PASS` | 0.02s | 4/4 manifests |
| P5.3 Migration 008 tables V4.2 | `PASS` | 0.01s | 9/9 tables declarees |
| P5.4 DZ rules seedees | `PASS` | 0.01s | 8 regles actives (>=8 requis) |
| P5.5 Innovation pipeline 8 stages + rejete | `PASS` | 0.03s | 9 stages, transitions definies |
| P5.6 Quality Kernel : invariants | `PASS` | 0.12s | 6 invariants signes |
| P5.7 Patch types : matrice revalidation complete | `PASS` | 0.02s | 6/6 types couverts |
