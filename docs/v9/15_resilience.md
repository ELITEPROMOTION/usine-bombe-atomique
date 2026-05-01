# 15 — Resilience & chaos

Référence : Phase 9L (`docs/V9_PHASE_9L_REPORT.md`), ADR-29/30.

## CircuitBreaker (ADR-29)

State machine async-safe :
- **CLOSED** : pass-through, compteur consecutive_failures
- **OPEN** : fail-fast, attente cooldown
- **HALF_OPEN** : probe limité, succès → CLOSED, échec → OPEN

```python
from app.saas_factory.resilience import (
    CircuitBreaker, CircuitBreakerConfig, get_policy,
)

policy = get_policy("stripe")
cb = CircuitBreaker(policy.circuit)
result = await cb.call(stripe_client.charge, ...)
```

## Catalogue politiques (6 dépendances)

| Dépendance | failure_thresh | cooldown | total_timeout |
|---|---|---|---|
| stripe | 5 | 30s | 10s |
| hostinger | 3 | 60s | 30s |
| anthropic | 4 | 20s | 60s |
| openai | 4 | 20s | 60s |
| resend | 5 | 30s | 10s |
| postgres | 3 | 10s | 5s |

```python
from app.saas_factory.resilience import RESILIENCE_POLICIES

for dep, policy in RESILIENCE_POLICIES.items():
    print(f"{dep}: {policy.timeout.total_seconds}s")
```

## TimeoutPolicy

```python
from app.saas_factory.resilience import with_timeout, TimeoutPolicy

policy = TimeoutPolicy(name="stripe", total_seconds=10.0)
result = await with_timeout(stripe_client.charge(...), policy)
# Re-emit ResilienceTimeoutError au lieu d'asyncio.TimeoutError brut
```

## Kill switches (env-based)

```bash
UBA_KILL_STRIPE=1     # Stripe désactivé
UBA_KILL_ANTHROPIC=1  # Anthropic bypassé (fallback OpenAI)
```

Lecture live `os.environ` (pas de cache).

```python
from app.saas_factory.resilience import get_kill_switches

ks = get_kill_switches()
ks.ensure_alive("stripe")    # raises KillSwitchActiveError si ON
```

## Chaos engineering (offline-only, ADR-30)

⚠ **NEVER active en prod**. Gate `UBA_CHAOS_ENABLED=1`.

```python
from app.saas_factory.chaos import ChaosInjector, get_scenario

# Tests
injector = ChaosInjector(get_scenario("stripe_down"), enabled=True)
result = await injector.invoke(stripe_client.charge, ...)
# Lèvera ConnectionResetError 100% du temps
```

### Scenarios cataloguées (8)

| Scenario | Modes | Probabilité |
|---|---|---|
| stripe_down | CONNECTION_RESET | 100% |
| stripe_intermittent | ERROR + TIMEOUT | 30% (seed=42) |
| hostinger_dns_slow | SLOW_RESPONSE | 100% delay 2s |
| anthropic_rate_limit | RATE_LIMITED (429) | 100% |
| anthropic_auth_failure | AUTH_FAILURE (401) | 100% |
| db_pool_exhausted | TIMEOUT | 100% delay 1s |
| partial_failure | ERROR | 50% (seed=1337) |
| resend_silent_drop | PARTIAL_DATA | 100% |

### Drill staging

```bash
# Sur staging seulement !
kubectl set env deploy/api-staging UBA_CHAOS_ENABLED=1
kubectl rollout restart deploy/api-staging
# Lancer trafic synthétique
# Vérifier que l'API reste up + CB s'ouvre + recovery OK
# Désactiver
kubectl set env deploy/api-staging UBA_CHAOS_ENABLED-
```

## Voir aussi

- [13 — Incident response](./13_incident_response.md)
- [14 — Observability](./14_observability.md)
- `docs/V9_PHASE_9L_REPORT.md`
