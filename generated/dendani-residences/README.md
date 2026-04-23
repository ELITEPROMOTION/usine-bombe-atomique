# Genere une API FastAPI de gestion des clients pour les residences du Groupe Dend

## Specification

Genere une API FastAPI de gestion des clients pour les residences du Groupe Dendani (Algerie).

CONTEXTE METIER :
- 4 residences fixes : IRENE, AUREA, MAGNOLIA, ASTERIA
- Vente en l'Etat Futur d'Achevement (VEFA) regie par le droit algerien
- Conformite fiscale algerienne : TVA 19%, TAP 2% (Taxe sur l'Activite Professionnelle)
- Echeancier VEFA 5 paliers standards : 20 / 15 / 35 / 25 / 5 pourcent

ENTITES (Pydantic v2 + in-memory stores) :
1. Residence : nom (IRENE|AUREA|MAGNOLIA|ASTERIA), ville, nb_lots_total
2. Client : id (int), nom, prenom, nin (18 chiffres, valide), telephone, email, adresse, created_at (datetime)
3. Reservation : id, client_id, residence_nom, num_lot, prix_ht (Decimal), tva_19pct, tap_2pct, prix_ttc, date_reservation, statut (active|annulee|completed)
4. Paiement : id, reservation_id, palier (1..5), pourcentage (20|15|35|25|5), montant_du, montant_paye (default 0), date_echeance, statut (a_venir|a_jour|retard|paye)
5. Echeancier : liste des 5 paiements generee automatiquement a la creation d'une reservation

ENDPOINTS REST :
- GET /residences ; GET /residences/{nom}
- CRUD complet /clients (POST, GET list, GET one, PUT, DELETE)
- POST /reservations -> cree automatiquement les 5 paiements (20/15/35/25/5) avec echeances mensuelles
- GET /reservations/{id} ; GET /reservations/{id}/echeancier
- POST /paiements/{id}/regler -> met montant_paye = montant_du, statut = paye
- GET /reports/encaissements -> total encaisse et reste a encaisser par residence
- GET /health

REGLES METIER (dans app/business.py) :
- tva_19pct = round(prix_ht * 0.19, 2)
- tap_2pct  = round(prix_ht * 0.02, 2)
- prix_ttc  = prix_ht + tva_19pct + tap_2pct
- valider_nin(nin: str) -> bool : 18 chiffres
- generer_echeancier(reservation_id, prix_ttc, date_debut) -> 5 paiements avec pourcentages [20,15,35,25,5] qui somment a 100, date_echeance espacee de 30 jours

TESTS pytest (tests/) :
- test_business_nin : valide/invalide
- test_business_tva_tap : calculs exacts TVA 19 pourcent et TAP 2 pourcent
- test_business_echeancier : 5 paliers, somme des pourcentages = 100, montants corrects
- test_clients_crud : cycle complet POST/GET/PUT/DELETE
- test_reservations : creation declenche generation des 5 paiements
- test_paiements_regler : passage a statut paye
- test_reports : agregation correcte

LIVRABLES ATTENDUS :
- app/__init__.py, app/main.py, app/models.py, app/store.py, app/business.py
- app/routers/__init__.py, residences.py, clients.py, reservations.py, paiements.py, reports.py
- tests/__init__.py, tests/conftest.py, plus les tests ci-dessus
- requirements.txt (fastapi, uvicorn, pydantic, email-validator, httpx, pytest)
- Dockerfile (python:3.12-slim, expose 8000, uvicorn)
- README.md (titre Dendani Residences API, contexte, endpoints, exemples curl en francais)

Exigences qualite :
- Code ruff-clean
- Typage strict, response_model sur chaque endpoint
- Aucun Any non justifie, aucun print, logging via logger standard
- Montants en Decimal (quantize 2 decimales)
- Tous les handlers avec HTTPException en cas d'erreur (404/400)

Reponds UNIQUEMENT avec un JSON {"files": {"<chemin>": "<contenu>"}}.

## Structure

- `Dockerfile` (text, 207 o)
- `README.md` (markdown, 4149 o)
- `app/__init__.py` (python, 0 o)
- `app/business.py` (python, 2568 o)
- `app/main.py` (python, 897 o)
- `app/models.py` (python, 3018 o)
- `app/routers/__init__.py` (python, 0 o)
- `app/routers/clients.py` (python, 2287 o)
- `app/routers/paiements.py` (python, 1235 o)
- `app/routers/reports.py` (python, 2036 o)
- `app/routers/reservations.py` (python, 2811 o)
- `app/routers/residences.py` (python, 757 o)
- `app/store.py` (python, 3938 o)
- `requirements.txt` (text, 140 o)
- `tests/__init__.py` (python, 0 o)
- `tests/conftest.py` (python, 1443 o)
- `tests/test_business_echeancier.py` (python, 1850 o)
- `tests/test_business_nin.py` (python, 757 o)
- `tests/test_business_tva_tap.py` (python, 1081 o)
- `tests/test_clients_crud.py` (python, 2172 o)
- `tests/test_paiements_regler.py` (python, 1468 o)
- `tests/test_reports.py` (python, 2192 o)
- `tests/test_reservations.py` (python, 1930 o)

## Installation

```bash
pip install -r requirements.txt
```


## Utilisation

```bash
uvicorn app.main:app --reload
```


## Tests

```bash
pytest -q
```

