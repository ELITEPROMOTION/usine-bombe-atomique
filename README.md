# Usine Bombe Atomique (UBA)

Plateforme de generation automatique de logiciels - Groupe Dendani.
Conforme CDC v3.0 - Bootstrap V0 genere le 2026-04-17.

## Vue d'ensemble

- **Frontend** React 18 + TypeScript + Vite (chat temps reel)
- **Backend** FastAPI 0.115 + asyncpg + Arq
- **BDD** PostgreSQL 16 + Redis 7
- **Agents** 23 agents specialises (stubs V0, a remplir)
- **Validation** Pipeline 9 niveaux (coherence, CDC, OWASP, perf, DZ, qualite, E2E, UX, prod-ready)

## Demarrage rapide

```bash
cp .env.example .env                 # deja fait par Bootstrap si .env absent
docker compose up -d --build
curl http://localhost:8000/api/v1/health
open http://localhost:3000
```

## Structure

```
uba/
  backend/
    app/
      agents/            # 23 agents + registry + base_agent
      routers/           # auth, health, tasks, websocket
      middleware/        # rate limiter
      validation/        # pipeline 9 niveaux
      config.py, database.py, main.py, worker.py, schemas.py
    migrations/versions/ # SQL init
    tests/               # pytest (registry, pipeline, schemas)
  frontend/
    src/
      components/chat/   # ChatInterface, MessageBubble, ChatInput, ProgressTracker
      hooks/             # useWebSocket
      stores/            # Zustand chatStore
      types/             # chat / task / agent types
  infra/                 # terraform, nginx, docker
  docs/                  # ARCHITECTURE.md
  .github/workflows/     # CI
  docker-compose.yml
```

## Endpoints cles

- `GET  /api/v1/health` - probe
- `POST /api/v1/auth/register` - creation utilisateur
- `POST /api/v1/auth/login` - JWT
- `POST /api/v1/tasks` - creer une tache de generation
- `GET  /api/v1/tasks/{id}` - consulter une tache
- `WS   /ws/tasks/{id}` - progression temps reel

## Variables d'environnement

Voir `.env.example`. Les secrets critiques a fournir :

- `ANTHROPIC_API_KEY` (Claude Sonnet 4)
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET` (auto-generes par Bootstrap)

## Roadmap V0 -> V1

- [x] G1 Completude CDC
- [x] G3 Bootstrap (repo + BDD + API + Frontend + Docker)
- [x] G4 Orchestration (FastAPI + Arq + DAG parallele)
- [x] G5 Agents initialises (23/23 : 5 reels + 18 stubs)
- [x] G6 Execution bout-en-bout (CRUD Classe A - score 0.999)
- [ ] G7 Auto-correction
- [ ] G8 Memoire reutilisee
- [ ] G9 Auto-amelioration

## Agents reels (V1)

| # | Agent         | Implementation                              |
|---|---------------|---------------------------------------------|
| 01| Claude Code   | Anthropic API + fallback template CRUD      |
| 02| SonarQube     | bandit + radon (proxy local)                |
| 04| Pytest        | pytest + json-report                        |
| 14| Linter        | ruff check --output-format json             |
| 21| README Gen    | rendu deterministe depuis manifest + spec   |

## Licence

Proprietaire - Groupe Dendani - CONFIDENTIEL.
