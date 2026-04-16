# Contribuer a UBA

## Regle d'or - CDC Zero Interpretation

Toute decision non triviale doit etre tracee dans le CDC ou dans un ADR (`docs/adr/`).
Pas de magie, pas d'implicite.

## Workflow

1. Branche : `feature/<ticket>-<slug>` ou `fix/<ticket>-<slug>`
2. Commits : conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`)
3. Pull Request : template auto-applique, 1 reviewer minimum
4. CI verte obligatoire avant merge

## Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv/Scripts/activate
pip install -r requirements.txt
pytest                                                # tous les tests
ruff check app tests
```

## Frontend

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run dev
```

## Ajouter un agent

1. Creer `backend/app/agents/<nom>.py` heritant de `BaseAgent`
2. Implementer `_execute(self, inputs)`
3. L'enregistrer dans `registry.py::AGENT_CATALOG`
4. Ajouter un test dans `tests/test_agents_<nom>.py`

## Ajouter une migration

1. Creer `backend/migrations/versions/<NNN>_<slug>.sql`
2. Toujours prevoir le rollback dans un commentaire en tete
3. Tester l'ordre `initdb` via `docker compose down -v && docker compose up -d`

## Principes

- Aucun secret en clair dans Git
- Aucun `print()` en prod : logger structure
- Tests obligatoires pour tout agent metier
- Pipeline validation 9 niveaux non contournable
