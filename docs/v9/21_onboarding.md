# 21 — New developer onboarding

Bienvenue. Ce doc se lit en 30 minutes et te donne tout ce qu'il
faut pour ouvrir une PR utile dans la première semaine.

## J0 — Setup machine

### Backend

```bash
git clone <repo>
cd uba/backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
# Éditer .env (DATABASE_URL minimal pour dev local)
python -m pytest tests/saas_factory/   # 758 tests doivent passer
```

### Frontend

```bash
cd ../frontend
npm install
npm run dev   # http://localhost:5173
```

## J1 — Lire dans l'ordre

1. [01 — Architecture](./01_architecture.md) (10 min)
2. [02 — Master plan](./02_master_plan.md) (5 min)
3. Le phase report de la zone que tu vas toucher (~15 min) :
   `docs/V9_PHASE_9X_REPORT.md`
4. ADRs liés (~10 min) : `docs/V9_ARCHITECTURE_DECISIONS.md`,
   index dans [03](./03_adr_index.md).

## J2 — Premier code

Conseil : commencer par un **bug fix mineur** ou une **petite
amélioration** d'un module dont tu viens de lire le rapport.

Workflow :
1. Branche : `git checkout -b fix/<topic>`
2. Code + test
3. `python -m pytest tests/saas_factory/test_<module>.py -v`
4. `python -m ruff check app/<module>/ --fix`
5. `python -m bandit -r app/<module>/ -ll`
6. Commit (conventional) : `fix(<scope>): <message>`
7. PR

## Conventions importantes

- **Commits conventionnels** : `feat(scope): ...`, `fix(scope): ...`,
  `test(scope): ...`, `docs(scope): ...`.
- **Pas de tag autonome** : ne taggue pas une release sans validation
  équipe.
- **Pas d'appel externe payant en CI** : Stripe/Hostinger/Anthropic
  doivent être stubs dans tous les tests. Live gate `UBA_LIVE_*=1`
  uniquement en prod.
- **Coverage cible** : critique ≥ 99%, globale ≥ 90%.
- **ADR pour décisions durables** : si tu fais un choix non-évident
  (e.g. "pourquoi pas Celery"), append un ADR.

## Patterns à apprendre

### Mock asyncpg pool (tests)

Cf. [07 — Testing](./07_testing.md). C'est LE pattern à maîtriser.

### `safeGet` (frontend)

Wrapper axios avec fallback sur fixtures. Permet le dev offline.

### CircuitBreaker async (backend)

Pour tout appel externe, wrapper avec `cb.call(client.method, ...)`.
Politiques pré-câblées dans `RESILIENCE_POLICIES`.

### V9Metrics avec registry injectable

```python
metrics = V9Metrics(registry=CollectorRegistry())   # tests
metrics = get_v9_metrics()                           # prod
```

## Pièges connus

- `datetime.utcnow()` est deprecated → toujours
  `datetime.now(UTC)`.
- `random.Random()` lève Bandit B311 → `secrets.SystemRandom()`.
- `assert` en prod lève Bandit B101 → `raise RuntimeError(...)`.
- `f"... {sql}"` peut lever B608 → utiliser `$1`/`$2` placeholders.
- Pour éviter bouclage Sentry : `# noqa: BLE001` sur les `except
  Exception` qui logguent + return.
- ESLint v9 nécessite `eslint.config.js` : pas livré en V9 (TODO
  maintenance).

## Channels & escalation

- `#dev` Slack : questions techniques
- `#ops` Slack : incidents prod
- `#compliance` : GDPR / sec
- DPO : `dpo@ubastudio.io`

## Voir aussi

- [04 — Backend dev](./04_backend_dev.md)
- [08 — Frontend dev](./08_frontend_dev.md)
- [22 — Release notes](./22_release_notes.md)
