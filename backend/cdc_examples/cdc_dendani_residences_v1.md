# Module Gestion Reservations Residences Dendani

## Objectif

Permettre la gestion complete des reservations des residences Dendani Algerie.

## Features

### 1. CRUD Residences (chambre / suite / appartement)
- Champs : `id` (uuid), `type` (chambre|suite|appartement), `capacite` (int >= 1),
  `prix_nuit_dzd` (decimal > 0), `status` (libre|occupe|maintenance)
- Validations : prix_nuit_dzd > 0, capacite >= 1, type dans liste autorisee

### 2. CRUD Clients
- Champs : `id` (uuid), `nom`, `prenom`, `nin` (numero d'identification national DZ
  18 chiffres), `tel` (format E.164), `email`
- Validations : NIN format DZ regex `^\d{18}$`, tel format E.164 `^\+\d{7,15}$`,
  email RFC

### 3. Reservations
- Champs : `id`, `residence_id`, `client_id`, `date_debut`, `date_fin`,
  `status` (pending|confirmed|cancelled|completed)
- Validations :
  - date_fin > date_debut
  - pas de conflit dates sur meme residence (overlap detection)
  - residence_id existe et status='libre' au moment de la reservation

### 4. Paiements DZ
- Champs : `id`, `reservation_id`, `montant_dzd`, `mode` (CB|cheque|virement|especes),
  `tva_pct` (defaut 19), `irg_applicable` (bool)
- Calculs auto :
  - TVA 19% sur montant HT
  - IRG si applicable (bareme tranches DZ 2026)
- Sortie : recu PDF (template simple, numeros de facture sequentiels)

### 5. Reports
- `GET /reports/occupation` : taux d'occupation par mois (JSON + chart-ready)
- `GET /reports/ca` : chiffre d'affaires mensuel
- `GET /reports/top-clients` : top 10 clients par CA
- `GET /reports/conformite-fiscale` : rapport conformite IRG/IBS/TVA DZ exportable XLSX

## Stack technique

- **Backend** : FastAPI Python 3.12 + SQLAlchemy 2.x + Pydantic v2 + asyncpg
- **DB** : PostgreSQL 16
- **Frontend** : React 18 + TypeScript + Tailwind 3
- **Containerise** : Docker + docker-compose.yml
- **Tests** : pytest >= 30 tests, coverage 85%+ minimum
- **Documentation** : README.md + OpenAPI auto via FastAPI

## Livrable attendu

- Code source complet : backend (`/app`, `/tests`, migrations) + frontend (`/src`)
- Dockerfile (backend) + docker-compose.yml fonctionnel
- Migrations SQL (Alembic) ou DDL bootstrap
- Tests automatises pytest qui PASS (target >= 30 tests)
- Documentation utilisateur (README) + section deploiement
- Pret a deployer en local : `docker compose up -d`

## Acceptance criteria (CDC valide si)

1. `docker compose up -d` demarre tous les services
2. `curl http://localhost:8000/api/v1/health` repond 200
3. CRUD complet residences/clients/reservations accessible via API
4. POST reservation avec dates conflit → 409 Conflict
5. Paiement avec montant_dzd <= 0 → 400 Bad Request
6. Report occupation retourne JSON valide
7. `pytest` PASS sans erreur
8. Coverage >= 85% sur le backend
