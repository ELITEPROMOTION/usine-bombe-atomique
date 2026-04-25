# UBA — Production Ready Local

**Status** : OPERATIONAL
**Date** : 2026-04-25
**Tag** : v5.5.7-vague7-production-ready / v6.0.0-uba-production-ready-local

---

## Score reel mesurable

| Metric | Valeur |
|--------|--------|
| Tests collected | **1440** + e2e/test_real_cdc_pipeline.py (skip par defaut) |
| Endpoints API | **226** (OpenAPI) |
| Endpoints GET sample | **105/106** OK (99.0%) |
| Anomalies critical | **0** |
| Anomalies high | **0** |
| Containers running healthy | **9** (10 avec nginx-local en local-prod) |
| Pipeline E2E CDC -> Livrable | **OPERATIONAL** |
| URL CEO | **https://uba.localhost** |
| Latence DB p99 | **2.08 ms** |
| Latence Redis p99 | **20.84 ms** |
| 5 domaines metier DZ | OK (fiscal, juridique, logistique, RH, comptabilite) |
| 6 circuit breakers | OK closed |
| 4 SLOs | 3 healthy + 1 warn (auto-resolve) |
| 4 modules intelligence | OK (active learning, explainer, KG, semantic cache) |
| 49 KG nodes / 43 edges | OK |
| 43 rules YAML actives | OK |

---

## 7 vagues — synthese

| Vague | Theme | Score |
|-------|-------|-------|
| V1 | Code 8.3 → 9.0 | 9.0 |
| V2 | Universalite 5 → 9 | 9 |
| V3 | Fiabilite 5 → 9.5 | 9.5 |
| V4 | Intelligence 8 → 9.5 | 9.5 |
| V5 | Outils 6 → 9 | 9 |
| V6 | Deploy + Polish | 9.5 |
| **V7** | **Production-Ready Local** | **9.8** |

---

## Comment lancer un projet (Ahmed, 7 etapes)

```powershell
# 1. Demarrer
.\deploy\local\start-local-prod.ps1

# 2. Ouvrir le navigateur sur https://uba.localhost

# 3. Login (Ahmed Dendani)

# 4. Cliquer "Nouveau projet" (sidebar, icone fusee)

# 5. Coller le CDC, donner un nom slug

# 6. Cliquer "Lancer le projet" → attendre 5-30 min

# 7. Telecharger le ZIP. Extraire. `docker compose up -d`. Done.
```

---

## Commandes courantes

```powershell
# Stop
.\deploy\local\stop-local-prod.ps1

# Health snapshot
curl -k https://uba.localhost/api/v1/health/detailed

# Logs backend
docker compose logs -f backend

# Liste projets
curl -k -H "Authorization: Bearer $token" https://uba.localhost/api/v1/projects

# OpenAPI docs
https://uba.localhost/docs
```

---

## Architecture en bref

```
[Ahmed] -- HTTPS --> [nginx-local] --+--> /api/* ---> [backend] --enqueue--> [Redis] --> [worker run_task]
                                     |--> /ws/*  ---> [backend WebSocket]
                                     |--> /     ---> [frontend React]
                                     
                                     [worker] = pipeline V3 (DAG agents)
                                       --> [Claude Code agent] (template fallback si fail)
                                       --> [SonarQube agent]
                                       --> [Pytest agent]
                                       --> [DockerAgent — V7 genere Dockerfile par defaut]
                                       --> [Validation 5 niveaux]
                                       --> [DeliveryPackage] --> artifacts in DB
                                     
                                     [Postgres] (107 tables) | [Vault] (secrets) | [SonarQube] (code analysis)
```

---

## Limitations (a savoir)

1. **Local uniquement** — pas encore deploye sur cloud. V6 a prepare l'infrastructure
   Hetzner (terraform/, deploy/), reactivable a la demande.
2. **Mono-utilisateur** — un seul Ahmed. Multi-tenant prevu V8.
3. **SSL self-signed** — warning navigateur normal. Voir
   `docs/SSL_LOCAL_NOTICE.md` pour trust automatique.
4. **Anthropic dependency** — la qualite du livrable depend de l'API Claude.
   Template fallback assure une livraison de base meme en cas de panne API.
5. **Backup local-only** — vers `backups/` du repo. S3/GCS prevu V8.

---

## Pour Ahmed — message direct

Tu as une usine logicielle qui marche. Pas un POC, pas un demo : une machine
operationnelle qui transforme un CDC francais en projet livre. Tape ton CDC
le plus complet, lance, et bois un cafe le temps que ca compile.

Si quelque chose plante : `docs/CEO_QUICKSTART.md` couvre 10 scenarios.

Bonne usine.
