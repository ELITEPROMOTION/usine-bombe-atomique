# V9 Architecture Decisions Log

Décisions prises pendant l'exécution de la V9. Format ADR léger : Contexte →
Décision → Conséquences. Une décision = un titre `## ADR-NN — <titre>`.

---

## ADR-01 — Tests dans `backend/tests/saas_factory/` plutôt que `tests/unit/` et `tests/integration/`

**Date** : 2026-04-29 (Phase 9-BOOT)

**Contexte** : le brief Phase 9-BOOT demandait deux fichiers à des chemins
non existants dans le repo : `tests/unit/test_self_bootstrap.py` et
`tests/integration/test_vault_secrets.py`. Or, le repo a déjà une structure
de tests installée à `backend/tests/` avec des sous-dossiers thématiques
(`backend/tests/osint/`, `backend/tests/intelligence/`, `backend/tests/health/`,
`backend/tests/observability/`, etc.) et un `pytest.ini` qui pointe sur
`testpaths = tests` relatif à `backend/`.

**Décision** : créer le sous-dossier `backend/tests/saas_factory/` avec :
- `test_self_bootstrap.py` (tests unitaires, pool DB mocké)
- `test_vault_secrets.py` (tests d'intégration légers, VaultClient mocké)

**Conséquences** :
- Cohérence avec les ~30 modules de tests existants.
- `pytest tests/saas_factory/` fonctionne directement sans configuration
  supplémentaire.
- Couverture remontée par `--cov=app/saas_factory --cov=app/security`.
- La distinction unit/integration est faite **par classe pytest** plutôt
  que par fichier, ce qui colle à la convention déjà en place dans
  `test_autonomy_v5_1*.py` (unit) et `test_autonomy_v5_1_integration.py`
  (intégration).

---

## ADR-02 — Numérotation des migrations 043/044 alors que 037-042 sont vides

**Date** : 2026-04-29 (Phase 9-BOOT)

**Contexte** : le master plan V9 réserve les migrations 037-047 pour les
19 phases, et attribue 043 (`self_bootstrap`) et 044 (`mandates_eidas`) à
Phase 9-BOOT — qui s'exécute pourtant en premier. Le repo actuel s'arrête
à la migration 036.

**Décision** : suivre la numérotation du master plan (043/044) plutôt que
prendre les premiers numéros libres (037/038).

**Justification** :
- Postgres applique les migrations en ordre numérique. Les phases 9A-9J
  qui combleront 037-042 ne référencent que des tables créées avant 035,
  ou créeront de nouvelles tables indépendantes — donc 043/044 ne créent
  aucune dépendance qui forcerait 037-042 à exister déjà.
- 043/044 ne référencent que `evidence_ledger` (créée en 004) et la fonction
  `digest()` de pgcrypto (utilisée depuis migration 035).
- Renoter 9-BOOT en 037/038 obligerait à renuméroter le master plan tout
  entier, ce qui crée plus de désordre que de valeur.

**Conséquences** :
- Quand les phases 9A-9J seront implémentées, elles devront créer
  effectivement leurs migrations 037-042.
- Tests de migration order (existant : `test_migrations_integrity.py`)
  doivent valider que chaque migration est idempotente
  (`CREATE TABLE IF NOT EXISTS`, etc.) — déjà respecté.

---

## ADR-03 — `app/security/vault_secrets.py` au-dessus de `app/integrations/vault_client.py`

**Date** : 2026-04-29 (Phase 9-BOOT)

**Contexte** : un `VaultClient` minimaliste existait déjà
(`app/integrations/vault_client.py`) avec `put/get/get_key/seed_from_env`.
Le brief demandait `app/security/vault_secrets.py` avec rotation 90j,
chiffrement AES-256-GCM, audit, fallback.

**Décision** : créer `app/security/vault_secrets.py` comme **wrapper haut-niveau**
au-dessus de l'existant, sans le modifier.

**Conséquences** :
- `VaultClient` reste l'API bas-niveau (KV v2 brute) — non régression V8.x.
- `VaultSecrets` ajoute la couche métier : enveloppe AES-256-GCM, rotation,
  fallback env, logs sans secret. Utilisable indépendamment ou via DI.
- La clé d'enveloppe (32 bytes base64url) doit être stockée hors Vault
  (variable d'environnement `VAULT_ENVELOPE_KEY`) — sinon le chiffrement
  Vault ⊕ enveloppe Vault est circulaire.
- Migration recommandée : un futur `seed_envelope` qui regénère la clé
  d'enveloppe et re-chiffre les valeurs à chaque rotation des 90 jours.

---

## ADR-04 — Aucune exécution réelle dans Phase 9-BOOT

**Date** : 2026-04-29 (Phase 9-BOOT)

**Contexte** : Phase 9-BOOT vise à préparer l'orchestrateur. Le brief stipule
explicitement « PAS d'exécution réelle dans Phase 9-BOOT (juste l'orchestrateur prêt) »
et la liste des actions interdites en autonome (achat domaine, VPS, Stripe live,
Manus, > 5 USD).

**Décision** :
- `AccountCreatorOrchestrator.plan_all()` boucle sur la priority queue et
  appelle `mark_success()` immédiatement pour débloquer les dépendances —
  c'est de la simulation, pas une activation réelle.
- `HandoffKycOrchestrator.open_handoff()` insère en DB un handoff_pending
  avec un magic-link cryptographiquement aléatoire, mais **n'envoie pas
  l'email** si `email_sender` n'est pas injecté.
- Les méthodes `tick()` (relances) et `resolve()` (résolution magic-link)
  sont implémentées et testées, mais leur câblage à un job périodique Arq
  est reporté en Phase 9Q.

**Conséquences** :
- Aucun coût externe consommé pendant 9-BOOT.
- Le passage en mode "exécution réelle" se fera au plus tôt en Phase 9-G/9-H,
  avec validation explicite par Ahmed avant chaque appel facturable.

---

## ADR-05 — Pas de DB Postgres réelle pour les tests Phase 9-BOOT

**Date** : 2026-04-29 (Phase 9-BOOT)

**Contexte** : la suite de tests existante (`backend/tests/conftest.py`)
prévoit une fixture `pool` qui instancie `asyncpg.create_pool` réellement.
Lancer cela hors docker-compose nécessite un Postgres up.

**Décision** : pour Phase 9-BOOT, mocker le pool via
`unittest.mock.MagicMock + AsyncMock`. Les tests vérifient le SQL appelé,
les paramètres bindés et la logique de sérialisation, sans toucher Postgres.

**Conséquences** :
- Tests rapides (~3s pour 58 tests).
- Limite : ne valide pas la conformité DDL réelle. À couvrir par un test
  d'intégration Postgres dédié en Phase 9R (suite `production_readiness`).
- `test_migrations_integrity.py` existe déjà et continuera de tester
  l'ordre/idempotence des migrations contre une DB réelle pendant CI.

---

## ADR-06 — `FRONTLOAD` en français pour les docstrings et messages internes

**Date** : 2026-04-29 (Phase 9-BOOT)

**Contexte** : le repo utilise déjà le français pour les docstrings de
modules (`integrations/vault_client.py`, `orchestration/audit_events.py`,
etc.) — mais les noms de classes/méthodes restent en anglais.

**Décision** : maintenir la convention. Docstrings en français, identifiants
en anglais. Templates email présents en EN et FR (placeholder pour AR/ES en
Phase 9I).

**Conséquences** : pas de switch de langue requis. La doc utilisateur finale
(22 docs Phase 9S) sera multilingue.
