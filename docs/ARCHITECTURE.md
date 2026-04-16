# Architecture UBA

Conforme CDC v3.0 Ch.2 - architecture 3 couches.

## Vue 3 couches

```
UTILISATEUR
   |
   v
[FRONTEND React 18 + TS]      <-- Chat, ProgressTracker, WebSocket
   | REST + WSS
   v
[NGINX Reverse Proxy]
   |
   v
[FASTAPI Orchestrateur]       <-- Intent NLP, planification
   |--- [Claude Sonnet 4]     API Anthropic
   |--- [PostgreSQL 16]       Persistance transactionnelle ACID
   |--- [Redis 7]             Cache + broker Arq
   |
   v
[ARQ Workers (async)]
   |--- Agent #01  Claude Code       development
   |--- Agent #02  SonarQube         testing
   |--- Agent #03  Terraform         infrastructure
   |--- ...
   |--- Agent #23  Notifier          monitoring
   |
   v
[PIPELINE VALIDATION 9 NIVEAUX]
   | Verdict multi-dimensionnel
   |--- PASS / CONDITIONAL_PASS  -> Livraison
   |--- SOFT_FAIL / HARD_FAIL    -> Rework (max 5x)
```

## Flux de donnees principal

| # | Etape         | Composants                           |
|---|---------------|--------------------------------------|
| 1 | Soumission    | Frontend -> API Gateway              |
| 2 | Reception     | API -> PostgreSQL (row `tasks`)      |
| 3 | Analyse NLP   | Orchestrateur -> Claude API          |
| 4 | Planification | Orchestrateur interne                |
| 5 | Distribution  | Orchestrateur -> Arq -> Redis        |
| 6 | Execution     | Agents -> Claude Code CLI / APIs     |
| 7 | Collecte      | Agents -> Orchestrateur              |
| 8 | Validation    | Orchestrateur -> Validators 9 niveaux|
| 9 | Decision      | Verdict -> livraison ou rework       |
| 10| Livraison     | Orchestrateur -> Frontend WebSocket  |

## Ports (conforme CDC Ch.2.4.2)

| Service         | Port  | Exposition            |
|-----------------|-------|-----------------------|
| Frontend (Nginx)| 3000  | HTTP local            |
| Backend FastAPI | 8000  | HTTP local            |
| PostgreSQL      | 5432  | interne docker        |
| Redis           | 6379  | interne docker        |

## Hierarchie connecteurs (CDC Ch.11.6)

1. API REST native - priorite absolue
2. SDK officiel
3. CLI officielle (Terraform, Claude Code, git)
4. Connecteur n8n (SaaS tiers uniquement)
5. Automation navigateur (Playwright) - V3+
6. Desktop automation - INTERDIT prod

## Gates d'auto-construction

| Gate | Critere                                 | Etat V0 |
|------|-----------------------------------------|---------|
| G1   | Besoin + acces suffisants              | OK      |
| G2   | Pas de contradictions                   | OK      |
| G3   | Socle minimal genere                    | OK      |
| G4   | Orchestration Arq fonctionnelle         | partiel |
| G5   | 23 agents enregistres                   | stubs   |
| G6   | Execution bout-en-bout                  | TODO    |
| G7   | Auto-correction                         | TODO    |
| G8   | Memoire reutilisee                      | TODO    |
| G9   | Auto-amelioration                       | TODO    |
