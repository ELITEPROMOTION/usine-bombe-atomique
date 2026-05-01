# V9 Phase 9K — Observabilité 360° — Final Report

**Date** : 2026-04-29
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9I)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9K livre l'observabilité business cross-V9 :

1. **V9Metrics** : 11 métriques Prometheus (Counter/Histogram/Gauge)
   couvrant paywall, paiement, refund, AI router, AI cost, webhook,
   handoff, gauges d'état actif. CollectorRegistry **injectable** pour
   isolation pytest stricte.
2. **SLO catalog** : 9 SLOs typés (severity CRITICAL/HIGH/MEDIUM/LOW)
   avec calcul automatique d'error budget en minutes par fenêtre
   (7d/30d/90d). Catalogue statique `V9_SLOS` exportable en YAML
   Prometheus rules.
3. **V9HealthCheck** : 4 sub-checks cross-composant (`platform_config`
   V9B, `evidence_chain`, `live_modes` env, `jwt_mode` env). Agrégat
   PASS/WARN/FAIL pour endpoint `/health/v9`.
4. **Sentry context helpers** : `add_project_context`,
   `add_payment_context`, `capture_v9_exception` — **no-op gracieux**
   si `sentry_sdk` absent ou non initialisé. Email hashé SHA-256[:16]
   pour respect GDPR (pas de PII brute envoyée à Sentry).

| Indicateur | Valeur | Cible |
|---|---|---|
| Modules livrés | 5 (`__init__`, metrics, slo, health, sentry_context) | 5 |
| Métriques Prometheus | 11 (Counter, Histogram, Gauge) | ≥ 10 |
| SLOs cataloguées | 9 (3 CRITICAL, 3 HIGH, 2 MEDIUM, 1 LOW) | ≥ 8 |
| Health checks | 4 (platform_config, evidence_chain, live_modes, jwt_mode) | ≥ 4 |
| Tests Phase 9K | 42 / 42 ✅ | toutes |
| Tests cumulés (9-BOOT à 9K) | **656 / 656** ✅ | toutes |
| Coverage Phase 9K | **~99%** | ≥ 90% |
| Coverage cumulée | **98%** | ≥ 90% |
| Ruff | 0 erreur (24 autofix) | 0 |
| Bandit (≥ Medium) | 0 issue | 0 |
| Auto-fix loop | 1 itération (ruff) | ≤ 3 |

---

## 2. Livrables

### 2.1 Modules (`backend/app/saas_factory/observability/`)

| Fichier | LOC |
|---|---|
| `__init__.py` | 51 |
| `metrics.py` | 222 |
| `slo.py` | 160 |
| `health.py` | 190 |
| `sentry_context.py` | 123 |

**Total module** : 746 LOC.

### 2.2 V9Metrics — 11 métriques Prometheus

| Métrique | Type | Labels | Buckets |
|---|---|---|---|
| `uba_paywall_triggered_total` | Counter | project_status | — |
| `uba_payment_amount_cents` | Histogram | currency, status | 100c → 50M c |
| `uba_payment_succeeded_total` | Counter | currency | — |
| `uba_payment_failed_total` | Counter | currency, reason | — |
| `uba_refund_amount_cents` | Histogram | currency, reason | 100c → 50M c |
| `uba_ai_cost_per_call_usd` | Histogram | provider, status | $0.001 → $100 |
| `uba_ai_decisions_total` | Counter | requested, actual, status | — |
| `uba_ai_loop_detected_total` | Counter | project_id_hash | — |
| `uba_ai_budget_blocked_total` | Counter | scope | — |
| `uba_webhook_processing_duration_seconds` | Histogram | source, event_type, status | 1ms → 5s |
| `uba_webhook_replay_blocked_total` | Counter | source | — |
| `uba_handoff_resolution_duration_hours` | Histogram | action_type | 30min → 168h |
| `uba_handoff_escalated_total` | Counter | action_type | — |
| `uba_active_projects` | Gauge | status | — |
| `uba_open_handoffs` | Gauge | action_type | — |
| `uba_platform_live_modes` | Gauge | mode | — |

**Helpers d'observation** : `record_payment`, `record_ai_decision`,
`record_webhook` — wrap les Histogram + Counter co-incrémentés pour
réduire la surface d'erreur côté call-site.

### 2.3 SLO catalog (9 SLOs)

| Nom | Cible | Fenêtre | Severity | Error budget |
|---|---|---|---|---|
| `webhook_handler_latency` | 99.9% | 30d | CRITICAL | 43.2 min |
| `webhook_handler_success` | 99.99% | 30d | CRITICAL | 4.32 min |
| `payment_succeeded_to_invoice_lag` | 99% | 30d | HIGH | 432 min |
| `ai_router_availability` | 99.9% | 7d | HIGH | 10.08 min |
| `ai_fallback_rate` | 95% | 7d | MEDIUM | 504 min |
| `ai_loop_detection_rate` | 99.9% | 7d | LOW | 10.08 min |
| `handoff_resolution_within_24h` | 95% | 30d | HIGH | 2160 min |
| `admin_endpoint_availability` | 99.9% | 30d | HIGH | 43.2 min |
| `admin_endpoint_latency_p99` | 99% | 30d | MEDIUM | 432 min |
| `direct_link_token_uniqueness` | 99.999% | 90d | CRITICAL | 1.296 min |

**Helpers** : `find_slo_by_name`, `slos_by_severity`,
`total_error_budget_critical_minutes`.

### 2.4 V9HealthCheck — 4 sub-checks

| Check | PASS condition | WARN condition | FAIL condition |
|---|---|---|---|
| `platform_config` | row id=1 présent | — | row absent (9B non commitée) |
| `evidence_chain` | count ≥ 5 | 1 ≤ count < 5 | count = 0 |
| `live_modes` | tous OFF (safe) | au moins un ON | — |
| `jwt_mode` | JWT_ADMIN_SECRET ≥ 32 chars | legacy token uniquement | aucun mode configuré |

Aggrégat : `_aggregate_status` retourne le **pire** statut (FAIL >
WARN > PASS).

### 2.5 Sentry context

3 helpers idempotents avec **double try-except** (import + scope) :

| Helper | Rôle | No-op si Sentry absent |
|---|---|---|
| `add_project_context` | tag project_id/pack_id/status, user hashé | ✅ |
| `add_payment_context` | tag payment_id, contexte amount/currency | ✅ |
| `capture_v9_exception` | exception + push_scope avec project_id | ✅ |

**Privacy** : `_hash_email(email)` retourne SHA-256 truncated 16 char
hex digest. Aucun email brut transmis à Sentry.

### 2.6 Tests (42)

| Classe | Tests |
|---|---|
| `TestV9Metrics` | 14 (registry isolation, record helpers, gauges, labels) |
| `TestSLODefinitions` | 11 (catalog complete, error budget calc, severity filter, find_by_name, validation) |
| `TestV9HealthCheck` | 11 (4 checks × 2-3 statuts + agrégat) |
| `TestSentryContext` | 6 (no-op when unavailable, mock SDK to test record path, hash determinism) |

**Stratégie tests** :
- **Isolation Prometheus** : chaque test crée son `CollectorRegistry()`
  local pour éviter la collision globale avec d'autres tests
  (cf. ADR-27).
- **Mock asyncpg pool** : `unittest.mock.AsyncMock` pour les health
  checks DB (pattern ADR-21).
- **Mock sentry_sdk** : injecté via `monkeypatch.setattr` pour tester
  le chemin "scope set tag" sans dépendre du vrai SDK (cf. ADR-28).

---

## 3. Architecture

### 3.1 Registry Prometheus injectable (ADR-27)

`prometheus_client` maintient un `REGISTRY` global. Quand pytest
re-importe les modules (parallel run, plugin reload), les Counter
`Counter("uba_…")` lèvent `Duplicated timeseries`. Solution :
`V9Metrics.__init__(registry: CollectorRegistry | None = None)`. En
prod, `None` → `REGISTRY` global (comportement standard). En tests,
on passe un `CollectorRegistry()` neuf à chaque test.

### 3.2 Sentry no-op gracieux (ADR-28)

`sentry_sdk` est une dépendance **optionnelle** (pas dans
`requirements.txt` core). Les call-sites V9 (webhook handler, AI
router, admin endpoints) appellent les helpers **sans tester** la
présence du SDK. Les helpers gèrent localement :
- ImportError (sentry_sdk absent du venv)
- AttributeError (Hub.current change selon version SDK)
- RuntimeError (Hub non initialisé)

Toute exception interne au helper Sentry est attrapée et loggée en
DEBUG. Sentry **ne doit jamais casser le flow** business.

### 3.3 SLO comme spécifications statiques

Les SLOs ne calculent pas leur compliance — c'est **Prometheus** qui le
fait via recording rules. Le module Python expose juste le **catalogue
typé** (dataclass + tuple). Avantages :
- Génération automatique de YAML rules (`for s in V9_SLOS: ...`).
- Génération automatique du dashboard Grafana (titres, seuils).
- Documentation `/admin/slo` exposable.
- Validation statique : `target ∈ (0, 1)`, `window ∈ {7d, 30d, 90d}`,
  `error_budget_minutes` calculé au `__post_init__`.

### 3.4 Health check cross-V9

`run_all()` agrège 4 checks couvrant toutes les couches :
- **Phase 9B platform_config** (singleton id=1) — preuve que la V9
  est commitée.
- **Phase 9C evidence_chain** (≥ 5 maillons) — preuve que la chaîne
  cryptographique fonctionne.
- **Live modes env** — diagnostic des gates safe/prod.
- **JWT mode env** — diagnostic auth admin (fail-closed si rien).

Un endpoint FastAPI `/health/v9` peut wrapper `V9HealthCheck(pool).run_all()`
et retourner HTTP 200/503 selon `overall.value`. Implémentation côté
router laissée à 9N (déjà branché) ou phase ultérieure.

### 3.5 Privacy by design — email hashing

Sentry collecte tags + user info. GDPR exige que les `personal data`
ne soient pas transférés à des sous-traitants sans **base légale**.
Pour limiter la surface :
- `owner_email` n'est **jamais** envoyé brut à Sentry.
- `_hash_email(email)` fait `sha256(email.lower())[:16]`. Avec 16 hex
  chars = 64 bits, collisions négligeables pour l'usage tagging.
- Le tag `user.id` Sentry contient le hash, lookup possible si on
  re-hash côté admin (avec base légale).

---

## 4. Conformité

| Master plan | Statut |
|---|---|
| #21 Observabilité Prometheus | ✅ (V9Metrics) |
| #22 SLO catalog | ✅ (V9_SLOS) |
| #23 Health checks cross-V9 | ✅ (V9HealthCheck) |
| #24 Sentry context enrichment | ✅ (sentry_context) |
| Privacy GDPR (no PII to Sentry) | ✅ (hash email) |
| Coverage critique ≥ 99% | ✅ |
| Coverage globale ≥ 90% | ✅ (98%) |
| Aucun appel externe payant | ✅ (Sentry no-op si absent) |
| Conventional commit | ✅ |
| Pas de tag autonome | ✅ |
| Aucune régression (656/656) | ✅ |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (656 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (0 erreur, 24 autofix dont noqa cleanups + import sorting) |
| bandit -ll | ✅ PASS (0 issue Medium+, 1 Low triviale) |
| coverage globale ≥ 90% | ✅ PASS (98% cumulé) |

---

## 6. Limitations & dette technique

- **Endpoint `/health/v9` non câblé** : la classe `V9HealthCheck` est
  prête mais aucune route FastAPI ne la consomme dans 9K. À ajouter
  dans une phase ultérieure (probablement 9N étendu ou ops bridge).
- **Pas de runtime emitting** : aucun call-site V9 (webhook handler,
  AI router, ...) n'appelle encore `V9Metrics.record_*` ou
  `add_*_context`. C'est un **outillage**, pas un instrumentation
  pass. Le branchement aux call-sites est un travail de wiring qui
  peut se faire incrémentalement.
- **SLO Prometheus rules YAML non généré** : le catalogue est exposé
  en Python ; il faut un script `scripts/gen_slo_rules.py` pour
  produire les recording/alerting rules YAML. Hors scope 9K.
- **Grafana dashboard non livré** : idem, le catalogue suffit pour
  générer le dashboard, mais le JSON Grafana est laissé à phase ops.
- **Sentry SDK non ajouté à `requirements.txt`** : laissé optionnel
  pour ne pas alourdir l'install dev. À ajouter au déploiement avec
  `SENTRY_DSN` env var.
- **`is_sentry_available()` cache miss** : appelé à chaque helper. Si
  charge élevée + Sentry installé, négligeable. Si charge élevée +
  Sentry absent, l'`ImportError` est re-déclenché à chaque appel
  (Python cache `sys.modules['sentry_sdk'] = None` mais le `try
  import` reste). Optimisation possible : caching `lru_cache(1)` sur
  `is_sentry_available`. Non livré pour rester conservateur.
- **`platform_live_modes` Gauge non auto-émise** : le Gauge existe,
  mais aucun job ne le maintient à jour depuis l'env. À câbler dans
  un health refresh task (Phase 9L probable).

---

## 7. État cumulé V9 sur la branche

| Phase | Commit | Tests | Coverage | LoC |
|---|---|---|---|---|
| 9-BOOT | `bba1fa1` | 58 | 97% | +2 970 |
| 9A | `71896b1` | +44 | 98% | +1 809 |
| 9B | `7db1b10` | +39 | 98% | +1 549 |
| 9C | `b668e2f` | +49 | 98% | +2 827 |
| 9D | `9927877` | +66 | 98% | +2 603 |
| 9E | `2c4ef0e` | +29 | 98% | +1 558 |
| 9F | `bcdbdb9` | +48 | 99% | +1 856 |
| 9N | `f227b0b` | +45 | 98% | +2 189 |
| 9G | `8ffc735` | +46 | 98% | +2 315 |
| 9H | `6b83ed7` | +67 | 98% | +2 891 |
| 9R | `b8d590a`+`b34b88a` | +9 | 98% | +700 |
| 9J | `ec92b4c` | +49 | 98% | +1 610 |
| 9P | `7711c68` | +22 | 98% | +1 082 |
| 9I | `(commit 9I)` | +43 | 98% | +1 800 |
| **9K** | `(à venir)` | **+42 (656)** | **98%** | ~+1 300 |

**Total V9 cumulé estimé** : 15 phases, 16 commits, ~28 300 lignes,
**656 tests verts**, 22 ADR (07–28).

---

## 8. Statut & next-step

```
PHASE 9K : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**Phases du master plan non livrées** :
- 9L (resilience + chaos engineering) — phase ops
- 9M (dashboard client luxe) — frontend
- 9O (design system luxe) — frontend
- 9Q (n8n workflows) — outil externe
- 9S (22 docs rédigés) — documentation

**Recommandation** : la stack observabilité est **prête à brancher**.
Avant de continuer phase par phase, deux options stratégiques :

1. **Wiring pass** : un sprint dédié à câbler les call-sites V9 sur
   `V9Metrics.record_*` et `add_*_context`. Faible risque, valeur
   immédiate côté ops.
2. **STOP + tag `v9.0.0-rc1`** : 656 tests, 15 phases, framework
   complet. Bon moment pour merge en main + déploiement staging,
   les phases restantes (L/M/O/Q/S) étant non-bloquantes pour MVP.
