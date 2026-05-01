# 19 — AI Router & cost guards

Référence : Phase 9D (`docs/V9_PHASE_9D_REPORT.md`), ADR-11/12.

## Composants

| Module | Rôle |
|---|---|
| `AIRouter` | route entre providers selon disponibilité + budget |
| `CostGuard` | enforce limites (per_call / per_project / daily) |
| `LoopDetector` | détecte boucles répétitives (anti-runaway) |
| `RetryPolicy` | exponential backoff + jitter |
| `DecisionsLogger` | persist decisions dans `ai_decisions_log` |
| `StubAIProvider` | provider in-memory pour tests offline |

## AIRouter

```python
from app.saas_factory.ai_orchestrator.router import (
    AIRouter, RoutingPolicy,
)

router = AIRouter(
    providers=[claude_provider, openai_provider],
    policy=RoutingPolicy.PREFER_PRIMARY_FALLBACK_SECONDARY,
)
result = await router.complete(prompt="...", project_id=UUID("..."))
```

### Stratégies fallback (ADR-11)

- `PREFER_PRIMARY_FALLBACK_SECONDARY` : Claude → OpenAI si fail
- `BALANCED_ROUND_ROBIN` : alterne (cost reduction)
- `PRIMARY_ONLY` : pas de fallback (test ou strict prod)

## CostGuard 3-niveau (ADR-12)

```python
guard = CostGuard(
    per_call_max_usd=0.50,
    per_project_daily_max_usd=10.0,
    platform_daily_max_usd=500.0,
)
guard.check_or_raise(estimated_cost_usd, project_id=UUID("..."))
```

Lève `BudgetExceededError` (counter `uba_ai_budget_blocked_total`
incrémenté). Scope `'per_call' | 'per_project' | 'daily'`.

## LoopDetector

Détecte si la même séquence de prompts (hash) revient > N fois en
<window>. Si déclenché :
- Counter `uba_ai_loop_detected_total{project_id_hash}`.
- Bloque les appels pour ce project pendant cooldown.
- Crée un handoff `ai_loop_review` pour l'admin.

## DecisionsLogger

Toute décision routée est loggée dans `ai_decisions_log` avec :
- `requested_provider`, `actual_provider`, `status`
- `prompt_hash` (SHA-256, pas le prompt brut)
- `tokens_in`, `tokens_out`, `cost_usd`
- `latency_ms`
- `project_id`

## Métriques Prometheus

- `uba_ai_decisions_total{requested,actual,status}` Counter
- `uba_ai_cost_per_call_usd{provider,status}` Histogram
- `uba_ai_loop_detected_total{project_id_hash}` Counter
- `uba_ai_budget_blocked_total{scope}` Counter

## SLOs

- `ai_router_availability` : 99.9% / 7d (CRITICAL)
- `ai_fallback_rate` : ≤ 5% / 7d (MEDIUM)
- `ai_loop_detection_rate` : ≤ 0.1% / 7d (LOW false positive)

## Live mode

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...      # optionnel, fallback
```

Si aucune clé : `StubAIProvider` instancié, tous les appels retournent
des fixtures déterministes.

## Voir aussi

- [14 — Observability](./14_observability.md)
- `docs/V9_PHASE_9D_REPORT.md`
