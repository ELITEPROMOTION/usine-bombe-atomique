# Rapport de verification UBA

**Statut global :** `FAIL`
**Duree :** 1086.7 s
**Phases :** 5

## Phase 1 · Verification par module

- Statut : `FAIL`
- Score : 78.6%
- Duree : 632.9 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P1.1 AST parse (backend) | `PASS` | 12.89s | 242 fichiers analyses, 0 erreur(s) |
| P1.2 Pytest + coverage (gate 50%) | `FAIL` | 600.24s | pytest rc=-1, couverture=0.0% |
| P1.3 Ruff + Bandit | `WARN` | 14.88s | ruff=79, bandit(high)=0, bandit(total)=24 |
| P1.4 mypy (lenient) | `PASS` | 0.02s | 0 erreur(s), 0 critique(s) (call-arg/arg-type/assignment/return-value) |
| P1.5 OpenAPI contract | `PASS` | 1.10s | 226 endpoints declares, 0 requis manquants |
| P1.6 Imports coherence (app.*) | `PASS` | 4.07s | 89 modules 'app.*' references, 0 introuvables |
| P1.7 CDC DZ conformity (8 regles) | `PASS` | 0.01s | 8/8 regles presentes |

## Phase 2 · Verification par ligne

- Statut : `FAIL`
- Score : 50.0%
- Duree : 25.3 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P2.1 Cyclomatic complexity (gate CC>15, dense<22) | `WARN` | 4.63s | 1728 blocs, 37 dense (11-15), 2 trop complexe (>15) |
| P2.2 Dead code (vulture conf>=80) | `PASS` | 0.00s | 0 candidat(s) de code mort |
| P2.3 Secrets hardcodes | `PASS` | 5.67s | 0 secret(s) suspect(s) detecte(s) |
| P2.4 Conventions nommage | `FAIL` | 3.77s | 15 violation(s) naming |
| P2.5 Duplications de fonctions | `WARN` | 4.12s | 1 cluster(s) de duplications |
| P2.6 Docstrings publiques (gate 40%) | `WARN` | 3.92s | 391/1079 fonctions publiques documentees (36%) |
| P2.7 Gestion erreurs (bare except / except pass) | `FAIL` | 3.21s | 13 pattern(s) douteux |

## Phase 3 · Cross-validation

- Statut : `PASS`
- Score : 100.0%
- Duree : 3.0 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P3.1 Coherence front <-> back | `PASS` | 0.04s | 0 ecart(s) |
| P3.2 BDD <-> models <-> migrations | `PASS` | 1.18s | 106 tables, 0 manquantes |
| P3.3 Agents <-> registry <-> DAG | `PASS` | 1.49s | catalog=24 real=11 dag=10 |
| P3.4 Config <-> env.example <-> compose | `PASS` | 0.12s | 39 cles .env.example, 0 ecart(s) |
| P3.5 Pipeline <-> scoring <-> verdicts | `PASS` | 0.10s | LEVEL_WEIGHTS=1.0 conf=1.0 |
| P3.6 Memoire <-> benchmarks <-> cost | `PASS` | 0.05s | 7/7 modules presents |
| P3.7 Securite bout-en-bout | `PASS` | 0.02s | 5/5 controles OK |

## Phase 4 · Stress

- Statut : `FAIL`
- Score : 78.6%
- Duree : 425.0 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P4.1 10 Classe A paralleles | `FAIL` | 181.64s | 0/10 completed, 0/10 termines |
| P4.2 Classe B complet (Paie DZ profond) | `WARN` | 241.46s | status=timeout score=None |
| P4.3 Logique rework / raffinement | `PASS` | 0.02s | refine=True rework_count_schema=True |
| P4.4 Fallback Anthropic timeout / quota | `PASS` | 0.01s | template_fn=True exception_handler=True |
| P4.5 DB + analytics sous charge | `PASS` | 0.06s | health=200 overview=200 marketplace=200 |
| P4.6 WebSocket 100 connexions | `PASS` | 0.86s | 100/100 ouvertes, 100 premiers messages recus |
| P4.7 Injection SQL + XSS + prompt | `PASS` | 1.12s | 3 injections testees, 0 probleme(s) |

## Phase 5 · V4.2 Quality Gates

- Statut : `PASS`
- Score : 100.0%
- Duree : 0.5 s

| Check | Statut | Duree | Resume |
|---|---|---|---|
| P5.1 V4.2 modules (24+5) | `PASS` | 0.14s | 29/29 modules presents |
| P5.2 Test manifests (4 types) | `PASS` | 0.03s | 4/4 manifests |
| P5.3 Migration 008 tables V4.2 | `PASS` | 0.01s | 9/9 tables declarees |
| P5.4 DZ rules seedees | `PASS` | 0.02s | 8 regles actives (>=8 requis) |
| P5.5 Innovation pipeline 8 stages + rejete | `PASS` | 0.05s | 9 stages, transitions definies |
| P5.6 Quality Kernel : invariants | `PASS` | 0.18s | 6 invariants signes |
| P5.7 Patch types : matrice revalidation complete | `PASS` | 0.03s | 6/6 types couverts |
