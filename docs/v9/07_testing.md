# 07 — Testing guide

## Stratégie V9

- **Unit tests** : `tests/saas_factory/test_<module>.py`, mock
  asyncpg via `_make_pool()` pattern.
- **E2E pipelines** : `tests/saas_factory/test_e2e_pipeline.py`
  (9R), validation cross-modules par sequenced side_effects.
- **Frontend** : Vite build + tsc check (pas de Playwright en V9).

**Coverage cible** :
- Critique : ≥ 99%
- Globale : ≥ 90% (atteint 98% cumulé)

**État final V9** : 758 tests verts.

## Mock asyncpg pool (ADR-21)

```python
def _make_pool(side_effects=None):
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    if side_effects is not None:
        conn.fetchrow = AsyncMock(side_effect=side_effects)
    else:
        conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    return pool, conn
```

Pourquoi pas de DB réelle :
- PostgreSQL-specific (JSONB, gen_random_uuid, INTERVAL) rend
  SQLite shim inadéquat.
- Lancer un Postgres dans CI ralentit (10x+) et complique les
  tests parallèles.
- Le mock pool valide les **contracts** entre modules ; les
  triggers SQL et CHECK constraints sont validés en migration
  smoke test.

## Pattern : sequenced side_effects (E2E)

```python
conn.fetchrow.side_effect = [
    project_row,        # appel 1 : SELECT projects
    payment_row,        # appel 2 : INSERT payments RETURNING
    handoff_row,        # appel 3 : INSERT handoff_requests RETURNING
]
```

## Pattern : isolated Prometheus registry (ADR-27)

```python
from prometheus_client import CollectorRegistry
from app.saas_factory.observability import V9Metrics

def test_metric_works():
    metrics = V9Metrics(registry=CollectorRegistry())  # ← isolation
    metrics.record_payment(amount_cents=100, currency="EUR", status="succeeded")
```

## Pattern : Sentry mock (ADR-28)

```python
def test_sentry_record_path(monkeypatch):
    fake_sdk = ...
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)
    add_project_context(uuid4())
    fake_sdk.configure_scope.assert_called()
```

## Pattern : chaos test enabled bypass (ADR-30)

```python
def test_chaos_scenario():
    injector = ChaosInjector(scenario, enabled=True)  # bypass env gate
    with pytest.raises(RuntimeError):
        await injector.invoke(failing_action)
```

## Tests rapides

```bash
# Tout
python -m pytest tests/saas_factory/ -q

# Fichier spécifique
python -m pytest tests/saas_factory/test_observability.py -v

# Test unique
python -m pytest tests/saas_factory/test_observability.py::TestV9Metrics::test_record_payment

# Sans warnings
python -m pytest -W ignore::DeprecationWarning
```

## Tests frontend (V9)

Pas de tests automatisés — validation par :
1. `npx vite build` doit passer.
2. `npx tsc --noEmit` doit retourner 0 sur les fichiers V9.
3. Page `/styleguide` (admin) review manuelle.

## Voir aussi

- [04 — Backend dev](./04_backend_dev.md)
- [13 — Incident response](./13_incident_response.md)
- `docs/V9_PHASE_9R_REPORT.md` (E2E strategy)
