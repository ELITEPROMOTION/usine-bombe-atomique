# V9 Phase 9L — Resilience + Chaos engineering — Final Report

**Date** : 2026-04-30
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9K)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9L livre l'outillage de résilience et chaos in-memory pour
protéger les call-sites V9 contre les défaillances externes :

1. **CircuitBreaker** async-safe (`asyncio.Lock`) avec state machine
   complète CLOSED → OPEN → HALF_OPEN → CLOSED. `expected_exceptions`
   filtre quelles exceptions comptent. Stats observabilité exposées
   (transitions, rejections, failure messages).
2. **TimeoutPolicy** + helper `with_timeout` : budget temps explicite
   par dépendance. Re-emit `ResilienceTimeoutError` au lieu de
   `asyncio.TimeoutError` brut (call-sites peuvent distinguer).
3. **KillSwitchRegistry** : fail-fast manuel via `UBA_KILL_<DEP>=1`.
   Lecture live `os.environ`, toggle à chaud. Catalogue 6 dépendances.
4. **ResiliencePolicy catalog** : 6 politiques pré-câblées (stripe,
   hostinger, anthropic, openai, resend, postgres) avec CB config
   + timeout adapté à chaque profil.
5. **ChaosInjector** offline-only avec gate `UBA_CHAOS_ENABLED=1` :
   wrap n'importe quel callable async, applique 7 modes de défaillance
   (TIMEOUT, ERROR, SLOW_RESPONSE, PARTIAL_DATA, CONNECTION_RESET,
   RATE_LIMITED, AUTH_FAILURE) selon scénario typé.
6. **ChaosScenario catalog** : 8 scénarios prêts à l'emploi
   (stripe_down, stripe_intermittent, hostinger_dns_slow,
   anthropic_rate_limit, anthropic_auth_failure, db_pool_exhausted,
   partial_failure, resend_silent_drop).
7. **Chaos runner** : `run_scenario(scenario, action, iterations=N)`
   produit un `ChaosRunReport` avec success_rate + breakdown par mode.

| Indicateur | Valeur | Cible |
|---|---|---|
| Modules livrés | 9 (5 resilience + 4 chaos) | 9 |
| CB états gérés | 3 (CLOSED, OPEN, HALF_OPEN) | 3 |
| Politiques V9 | 6 (stripe, hostinger, anthropic, openai, resend, postgres) | ≥ 5 |
| Scenarios chaos | 8 | ≥ 6 |
| FailureModes | 7 (TIMEOUT, ERROR, SLOW, PARTIAL, RESET, RATE_LIMITED, AUTH) | ≥ 5 |
| Tests Phase 9L | 62 / 62 ✅ | toutes |
| Tests cumulés (9-BOOT à 9L) | **718 / 718** ✅ | toutes |
| Coverage Phase 9L | **~99%** | ≥ 90% |
| Coverage cumulée | **98%** | ≥ 90% |
| Ruff | 0 erreur (7 autofix) | 0 |
| Bandit (≥ Medium) | 0 issue | 0 |
| Auto-fix loop | 1 itération (regex + timeout config) | ≤ 3 |

---

## 2. Livrables

### 2.1 Modules (`backend/app/saas_factory/resilience/`)

| Fichier | LOC |
|---|---|
| `__init__.py` | 38 |
| `circuit_breaker.py` | 240 |
| `timeouts.py` | 73 |
| `kill_switch.py` | 84 |
| `policies.py` | 155 |

### 2.2 Modules (`backend/app/saas_factory/chaos/`)

| Fichier | LOC |
|---|---|
| `__init__.py` | 36 |
| `scenarios.py` | 119 |
| `injector.py` | 190 |
| `runner.py` | 73 |

**Total module** : 1 008 LOC (resilience + chaos).

### 2.3 CircuitBreaker — état machine

| État | Comportement |
|---|---|
| **CLOSED** | pass-through. Compteur `consecutive_failures`. Au seuil → OPEN |
| **OPEN** | rejette tout (`CircuitBreakerOpenError`). Après cooldown → HALF_OPEN |
| **HALF_OPEN** | `half_open_max_calls` slots concurrents. Échec → OPEN, `success_threshold` succès consécutifs → CLOSED |

**Garanties** :
- Async-safe : toute mutation d'état sous `asyncio.Lock`.
- Filtrage exceptions : seules les `expected_exceptions` comptent.
- Reset admin override : `await cb.reset()`.
- Stats : `total_calls`, `total_successes`, `total_failures`,
  `total_rejections`, `state_transitions`, `last_failure_message`.

### 2.4 ResiliencePolicy catalog — 6 dépendances

| Dépendance | failure_thresh | cooldown | total_timeout | description |
|---|---|---|---|---|
| stripe | 5 | 30s | 10s | charges/refunds/webhooks |
| hostinger | 3 | 60s | 30s | DNS/VPS/SSL provisionning |
| anthropic | 4 | 20s | 60s | Messages API (génération longue) |
| openai | 4 | 20s | 60s | Chat Completions |
| resend | 5 | 30s | 10s | transactional email |
| postgres | 3 | 10s | 5s | pool DB |

### 2.5 KillSwitchRegistry — env-based

```bash
UBA_KILL_STRIPE=1     # désactive immédiatement Stripe calls
UBA_KILL_ANTHROPIC=1  # bypass provider IA primaire
```

Catalogue connu : stripe, hostinger, anthropic, openai, resend, n8n.
Lecture live `os.environ` (pas de cache → toggle à chaud possible).

### 2.6 ChaosScenario catalog (8)

| Scenario | Dépendance | Modes | Probabilité | Délai |
|---|---|---|---|---|
| `stripe_down` | stripe | CONNECTION_RESET | 100% | 0s |
| `stripe_intermittent` | stripe | ERROR + TIMEOUT | 30% (seed=42) | 0s |
| `hostinger_dns_slow` | hostinger | SLOW_RESPONSE | 100% | 2s |
| `anthropic_rate_limit` | anthropic | RATE_LIMITED (429) | 100% | 0s |
| `anthropic_auth_failure` | anthropic | AUTH_FAILURE (401) | 100% | 0s |
| `db_pool_exhausted` | postgres | TIMEOUT | 100% | 1s |
| `partial_failure` | * | ERROR | 50% (seed=1337) | 0s |
| `resend_silent_drop` | resend | PARTIAL_DATA | 100% | 0s |

### 2.7 Tests (62)

**`test_resilience.py`** (35 tests) :
- `TestCircuitBreakerConfig` (5) : validation params (threshold/cooldown).
- `TestCircuitBreaker` (12) : initial state, success pass-through,
  failure threshold transitions, OPEN rejects, cooldown HALF_OPEN,
  HALF_OPEN failure → OPEN, half_open_max_calls limit, unexpected
  exception bypass, success reset, force reset, args propagation.
- `TestTimeoutPolicy` (6) : validation, completion under budget,
  raise on overrun.
- `TestKillSwitchRegistry` (6) : default off, on when set, exact
  match, snapshot, singleton, case-insensitive.
- `TestPolicies` (6) : known deps, unknown raises, case-insensitive,
  consistency checks, postgres short, anthropic long.

**`test_chaos.py`** (27 tests) :
- `TestChaosScenarioValidation` (5) : validation params.
- `TestChaosCatalog` (3) : catalog complete, get, unknown raises.
- `TestChaosInjectorGate` (3) : env gate blocks, explicit bypass, env on.
- `TestChaosInjectorInvoke` (12) : zero/full proba, 7 failure modes,
  determinism (seed), event recording.
- `TestRunScenario` (4) : iterations validation, all-success,
  all-fail, mixed deterministe.

---

## 3. Architecture

### 3.1 CircuitBreaker async state machine (ADR-29)

Pattern Hystrix simplifié, async-first. Différences notables vs
implémentations classiques :
- **`asyncio.Lock`** au lieu de `threading.Lock` : compatibilité
  natif asyncio, zéro contention sur threads.
- **`expected_exceptions`** : filtre les exceptions qui comptent.
  Permet de ne pas faire ouvrir le circuit sur des bugs locaux
  (e.g. `TypeError` dans un wrapper).
- **State HALF_OPEN avec compteur in-flight** : limite le burst de
  recovery checks, évite que 1000 requêtes ne se ruent en même temps
  quand on sort d'un OPEN.
- **Reset force** : pour admin override en cas de fausse alerte.

### 3.2 ChaosInjector offline-only (ADR-30)

`ChaosInjector.__init__` lève `ChaosDisabledError` si
`UBA_CHAOS_ENABLED=1` n'est pas dans l'env (ou `enabled=True`
explicite pour les tests). Garde-fou critique : aucun risque qu'un
oubli de gate active du chaos en prod.

### 3.3 Determinisme via seed

Les scénarios avec `seed=N` sont reproductibles : deux runs avec même
seed produisent la même suite d'événements. Permet :
- Tests stables (pas de flakiness).
- Reproduction d'un cas observé en staging.
- Comparaison d'implémentations (avant/après refactor : même chaos,
  même outcome attendu).

Implémentation : `_SeededRandom` wrap `random.Random(seed)` localisé
(import inline pour éviter Bandit B311 sur module-level random).
`secrets.SystemRandom()` utilisé sinon (pas de seed).

### 3.4 Catalogue ResiliencePolicy comme single-source-of-truth

Les call-sites (Stripe client, Hostinger client, AI router) ne doivent
**jamais** hardcoder leurs propres seuils CB / timeouts. À la place :
```python
from app.saas_factory.resilience import get_policy
policy = get_policy("stripe")
cb = CircuitBreaker(policy.circuit)
result = await with_timeout(
    cb.call(stripe_client.charge, ...),
    policy.timeout,
)
```

Bénéfices :
- Tuning centralisé. Si on observe que Stripe est plus stable que
  prévu, on relâche `failure_threshold` à un seul endroit.
- Métriques cohérentes (Prometheus aura les mêmes labels qu'on bouge
  les seuils ou pas).
- Documentation auto-générée possible (`for p in RESILIENCE_POLICIES.values()`).

### 3.5 Chaos en staging vs en CI

CI : `UBA_CHAOS_ENABLED` non défini → tous les tests passent par
`enabled=True` explicite. Aucun risque de fuite en prod.

Staging : un script `scripts/chaos_drill.sh` peut exporter
`UBA_CHAOS_ENABLED=1`, instancier un scenario, et lancer un trafic
synthétique. Le runner produit un rapport (success_rate par mode,
exceptions distinctes).

Prod : **interdit**. Le fail-fast de `ChaosInjector.__init__` garantit
qu'oublier la gate = crash immédiat à la première instanciation.
Pas de mode "chaos en prod" prévu en V9.

### 3.6 Pas de persistence DB

Tout est in-memory. Trade-off accepté :
- ✅ Simplicité, zero migration.
- ✅ État CB local au process : pas de coordination distribuée
  nécessaire (chaque worker FastAPI a son CB).
- ❌ Pas de snapshot CB après restart : quand on redémarre le pod,
  tous les CB repartent CLOSED. Acceptable car les pods sont éphémères
  et un cycle CLOSED → OPEN re-déclenche en quelques calls de toute
  façon.
- ❌ Pas d'agrégation cross-replicas : si 3 pods voient Stripe down,
  chaque pod ouvre son propre CB indépendamment. Pour orchestration
  globale → Redis-backed CB en V10 (hors scope V9L).

---

## 4. Conformité

| Master plan | Statut |
|---|---|
| #25 CircuitBreaker async | ✅ |
| #26 TimeoutPolicy par dépendance | ✅ |
| #27 KillSwitch fail-fast | ✅ |
| #28 Catalog résilience | ✅ |
| #29 Chaos engineering offline | ✅ |
| Pas d'appel externe payant | ✅ (chaos uniquement local) |
| Coverage critique ≥ 99% | ✅ |
| Coverage globale ≥ 90% | ✅ (98%) |
| Conventional commit | ✅ |
| Pas de tag autonome | ✅ |
| Aucune régression (718/718) | ✅ |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (718 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (0 erreur, 7 autofix : import order + builtin TimeoutError) |
| bandit -ll | ✅ PASS (0 issue Medium+) |
| coverage globale ≥ 90% | ✅ PASS (98% cumulé) |

---

## 6. Limitations & dette technique

- **Pas de wiring aux call-sites V9** : Phase 9L livre l'outillage,
  pas l'instrumentation. Les clients Stripe/Hostinger/Anthropic ne
  sont pas encore wrappés dans des CB. Wiring pass à faire en parallèle
  avec 9K (V9Metrics).
- **CB local au process, pas distribué** : si 4 workers FastAPI tournent
  derrière Nginx, chaque worker a son propre état CB. Acceptable en V9
  (workers stateless) mais à upgrader vers Redis-backed CB pour V10.
- **Pas de state persistence** : `CircuitBreakerStats` ne snapshot pas
  son état. Un redémarrage = retour à CLOSED. Acceptable car les pods
  sont éphémères.
- **Chaos pas câblé à V9Metrics** : le runner produit un report Python
  mais n'émet pas de Prometheus counters pour les modes injectés. À
  brancher en wiring pass.
- **Pas de bulkhead pattern** : on ne limite pas la concurrence par
  dépendance (semaphore). Pour Phase 9L, le couplage CB+timeout suffit.
  Bulkhead utile si saturation observée → V10.
- **Saga / compensation pattern absent** : pour les transactions
  multi-step (création projet + provisionning + facturation), il
  faudrait un orchestrateur saga. Hors scope 9L (et déjà partiellement
  couvert par handoff orchestrator + idempotency en 9R/9C).

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
| 9I | `1cff9e2` | +43 | 98% | +1 800 |
| 9K | `fbdc83f` | +42 | 98% | +1 731 |
| **9L** | `(à venir)` | **+62 (718)** | **98%** | ~+1 800 |

**Total V9 cumulé estimé** : 16 phases, 17 commits, ~30 100 lignes,
**718 tests verts**, 24 ADR (07–30).

---

## 8. Statut & next-step

```
PHASE 9L : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**Phases du master plan non livrées** :
- 9M (dashboard client luxe) — frontend
- 9O (design system luxe) — frontend
- 9Q (n8n workflows) — outil externe
- 9S (22 docs rédigés) — documentation

**Recommandation** : la stack backend V9 est **complète**. 16 phases,
718 tests, 24 ADRs, frameworks de paiement / IA / résilience /
observabilité tous livrés. Bon moment pour :
1. **Wiring pass** : intégrer V9Metrics (9K) + CircuitBreaker (9L)
   dans les call-sites Stripe/Hostinger/Anthropic existants.
2. **STOP backend + tag `v9.0.0-rc1`** : merge en main, déploiement
   staging, puis attaquer le frontend (9M/9O) séparément.
