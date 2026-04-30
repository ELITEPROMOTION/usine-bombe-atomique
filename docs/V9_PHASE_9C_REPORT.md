# V9 Phase 9C — Intelligence Engine — Final Report

**Date** : 2026-04-30
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9B)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9C livre la **brain** du SaaS factory : 4 moteurs orchestrés
(qualification, pricing, assembly, progression) + 9 packs contextuels +
1 migration de 4 tables. La qualification utilise un `ClaudeProvider`
Protocol-injectable — **aucun appel Claude réel** n'est émis en 9C.

| Indicateur | Valeur | Cible |
|---|---|---|
| Engines | 4 (qualification, pricing, assembly, progression) | 4 |
| Packs | 9 (E-Commerce S/M/L, SaaS S/M/L, Mobile, API B2B, Custom) | 9 |
| Migration | 041_intelligence_engine.sql (4 tables) | 1 |
| Tests Phase 9C | 49 / 49 ✅ | toutes passent |
| Tests cumulés (9-BOOT + 9A + 9B + 9C) | **190 / 190** ✅ | toutes |
| Coverage Phase 9C | **99%** (qualification 100%, pricing 99%, assembly 98%, progression 99%, packs 99%) | ≥ 90% |
| Coverage critique | **qualification 100%, pricing 99%** | ≥ 99% |
| Coverage cumulée | **98%** | ≥ 90% |
| Ruff | 0 erreur (6 autofix triviaux : import order) | 0 |
| Bandit (≥ Medium) | 0 issue (2 LOW résolus en remplaçant `assert` par `raise`) | 0 |
| Auto-fix loop | 0 itération | ≤ 3 |
| Appels Claude réels | 0 | 0 |

---

## 2. Livrables

### 2.1 Modules (`backend/app/saas_factory/intelligence/`)

| Fichier | LOC | Coverage |
|---|---|---|
| `__init__.py` | 50 | 100% |
| `packs/packs.json` | 9 packs × 2 locales | n/a |
| `packs/catalog.py` | 175 | 99% |
| `pricing_engine.py` | 240 | 99% |
| `qualification_engine.py` | 220 | 100% |
| `assembly_engine.py` | 175 | 98% |
| `progression_engine.py` | 230 | 99% |

### 2.2 Migration

**041_intelligence_engine.sql** — 4 tables :

- `intelligence_qualifications` (qualification_id, project_id, pack_hint,
  facets_json, detected_domain, locales[], risks[], confidence,
  rationale, cdc_text_hash, created_at) + 4 indexes
- `intelligence_pricings` (pricing_id, project_id, pack_id, status,
  currency, net_price, tax_amount, gross_price, facets_json,
  coefficients_json, breakdown_json, notes_json, created_at) + 3 indexes
- `intelligence_assemblies` (assembly_id, project_id, qualification_id FK,
  pricing_id FK, pack_id, outcome, modules[], deliverables[],
  selected_addons[], phase_weights_json, notes_json, created_at) + 2 indexes
- `project_progression` (project_id, phase, weight_pct, status,
  completion_pct, started_at, completed_at, paywall_triggered_at,
  updated_at, UNIQUE (project_id, phase)) + 3 indexes

Plus seal `evidence_ledger`.

### 2.3 Tests (`backend/tests/saas_factory/test_intelligence.py`)

49 tests :

- **PackCatalog (9 tests)** : 9 packs chargés, phases somment à 100,
  labels EN/FR, `custom` = manual_quote, JSON invalide rejeté, phases
  non-100 rejetées, manual_quote+price>0 rejeté, `label()` fallback.
- **PricingEngine (12 tests)** : quote OK, `custom` → REQUIRES_MANUAL_QUOTE,
  capping max_complexity_factor, factor=1.0 quand zero facets, persistence
  `INSERT INTO intelligence_pricings`, `_apply_margin_floor` (below/above
  min, zero price, 100% guard), `_round_2` ROUND_HALF_UP, `ProjectFacets`
  Pydantic (out-of-range, missing field), constante NORMALIZER.
- **QualificationEngine (6 tests)** : qualify+persist, empty cdc raises,
  unknown pack_hint raises, invalid facets raises, low confidence
  propagates, StubClaudeProvider call_count.
- **AssemblyEngine (6 tests)** : AUTO outcome, MANUAL_QUOTE outcome,
  DEGRADED si confidence=low, addons filtrés au pack.suggested_addons,
  pack mismatch loggé mais pricing wins, helper serialize.
- **ProgressionEngine (16 tests)** : initialize 6 phases, set invalide
  rejeté, somme ≠ 100 rejetée, completion hors bornes rejeté, status=DONE
  force completion=100, snapshot calcule overall, paywall trigger à 20%,
  unknown project raises, `_compute_overall` cap à 100, `_current_phase`
  in_progress > pending > last DONE, `_eta` extrapolation, websocket
  payload format, constante 20%.

### 2.4 Docs

- `docs/V9_PHASE_9C_REPORT.md` (ce fichier)
- `docs/V9_ARCHITECTURE_DECISIONS.md` — ADR-11 nouvelle

---

## 3. Architecture des 4 moteurs

### 3.1 PricingEngine — calcul déterministe en 4 étapes

```
1. contributions[k] = facets[k] × coefficients[k]   (∀ k ∈ COEFFICIENT_KEYS)
2. raw_factor = 1.0 + sum(contributions) / NORMALIZER (=30)
3. effective_factor = min(raw_factor, pack.max_complexity_factor)
4. price = pack.base_price × effective_factor
   cost  = pack.estimated_cost × effective_factor
   if margin < 50% : price = cost / (1 - 0.5)   ← floor lifted
   tax = price × vat_pct
   gross = price + tax
```

Le pack `custom` (manual_quote_required=true) bypasse l'étape 1-4 et
retourne `REQUIRES_MANUAL_QUOTE` avec `net_price=0`. L'orchestrateur 9F
routera la demande vers un handoff Ahmed.

### 3.2 QualificationEngine — Claude via Protocol

Le moteur ne touche pas l'API Claude. Il appelle
`provider.analyze_cdc(cdc_text, system_prompt)` puis valide la réponse via
Pydantic v2 (`_ClaudeResponseSchema`). Si :

- réponse invalide → `QualificationError`
- pack_hint inconnu → `QualificationError`
- cdc_text vide → `QualificationError`

Le `StubClaudeProvider` (utilisé par les tests) retourne une réponse
canned, ce qui rend la suite de tests entièrement offline et déterministe.
Le **vrai** provider Claude sera injecté en Phase 9D via l'AI Router.

### 3.3 AssemblyEngine — composition

3 outcomes possibles :

- `AUTO` : qualification confidence ∈ {high, medium} ET pricing OK
- `MANUAL_QUOTE` : pricing = REQUIRES_MANUAL_QUOTE (pack `custom`)
- `DEGRADED` : qualification confidence = low → handoff Ahmed recommandé

Les addons sélectionnés sont **filtrés** par `pack.suggested_addons` :
les addons hors-catalogue sont silencieusement ignorés (les notes le
mentionnent, mais ce n'est pas une erreur dure).

### 3.4 ProgressionEngine — 6 phases pondérées

Phases canoniques : ANALYSIS → DESIGN → CORE → FEATURES → TESTING → DEPLOY
(somme 100%, validation au schema). Chaque pack a son propre dosage des
poids (E-Commerce Small a 35% en CORE, SaaS Large a 28%).

Calcul : `overall = sum(weight × completion / 100)`, plafonné à 100.

**Paywall** : se déclenche dès que `overall >= 20%` (cf. CDC). Le moteur
écrit `paywall_triggered_at` la 1ère fois, puis l'orchestrateur de
billing (Phase 9H) prendra le relais pour générer le checkout Stripe.

**ETA** : extrapolation naïve à partir des phases déjà terminées
(`done_weight / cumulative_duration` → `seconds_per_pct`). Retourne
`None` si aucune phase DONE n'a de timestamps. Précision suffisante
pour un dashboard ; pas un SLA contractuel.

---

## 4. Conformité aux contraintes

| Contrainte | Respect |
|---|---|
| Marge ≥ 50% (CDC) | ✅ `_apply_margin_floor` testée 4 cas |
| 15 coefficients exacts | ✅ `COEFFICIENT_KEYS` partagé avec 9B |
| Paywall à 20% | ✅ `PAYWALL_THRESHOLD_PCT = 20.0` |
| Pas d'appel Claude réel | ✅ Protocol+Stub |
| 9 packs livrés | ✅ |
| Tests ≥ 99% critique | ✅ qualif 100%, pricing 99% |
| Tests ≥ 90% global | ✅ 99% Phase 9C, 98% cumulé |
| Pas de tag autonome | ✅ |
| Aucune régression | ✅ 190/190 cumulés |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (190 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (0 erreur, 6 autofix triviaux) |
| bandit -ll | ✅ PASS (0 Medium+, 2 LOW résolus) |
| coverage critique ≥ 99% | ✅ PASS |
| coverage globale ≥ 90% | ✅ PASS (98%) |
| Aucun appel API externe payant | ✅ |
| Aucun secret en clair | ✅ |

---

## 6. Limitations & dette technique

- **`assembly_engine.py` à 98%** : 1 ligne (la vérification tautologique
  qui sera nettoyée quand Project will have a typed FK contract).
- **`packs/catalog.py`, `pricing_engine.py`, `progression_engine.py` à 99%** :
  1 ligne chacun (chemins de validateur Pydantic peu testables sans
  doublonner l'effort).
- **Pas de `projects` table** : `project_id` est un `TEXT` libre. Quand
  Phase 9F (client onboarding) créera la vraie table `projects`, on
  ajoutera des FK rétroactives sur `intelligence_qualifications.project_id`,
  `intelligence_pricings.project_id`, `intelligence_assemblies.project_id`
  et `project_progression.project_id`.
- **ETA naïve** : extrapole linéairement, ne tient pas compte des
  variations de complexité phase-à-phase. Suffisant pour le dashboard ;
  un modèle plus fin (régression Bayesienne) sera ajouté en Phase 9M
  si besoin.
- **Pas d'invalidation de qualification ancienne** : si Ahmed re-saumet
  un CDC modifié, on crée une nouvelle ligne (pas de UPDATE). Le hash
  `cdc_text_hash` permet de détecter si c'est le même CDC.
- **Pas d'API HTTP** : router FastAPI à câbler en Phase 9N (admin).

---

## 7. Statut & next-step

```
PHASE 9C : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

Phases V9 complétées sur cette branche : **9-BOOT + 9A + 9B + 9C**.
Total cumulé : 4 phases, 190 tests verts, 98% coverage, +6 327 lignes V9
(estimation après commit 9C).

**Suite logique** : Phase 9D (AI Orchestrator — AI Router, Cost Guard,
Loop Detector, Decisions Logger) — câble le **vrai** Claude provider et
remplace `StubClaudeProvider` dans `QualificationEngine`. Migration 040
(`ai_decisions_log`).
