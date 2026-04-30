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

---

## ADR-07 — Tokens random + DB-lookup plutôt que JWT/HMAC stateless

**Date** : 2026-04-29 (Phase 9A)

**Contexte** : Phase 9A doit émettre des liens d'action (KYC, paiement,
download). Deux stratégies possibles :

1. **Token aléatoire + lookup DB** (`secrets.token_urlsafe(32)`, hash SHA-256
   stocké, validation = SELECT). Coût : 1 query par validation.
2. **JWT/HMAC signé** (payload base64 + signature HMAC-SHA256). Coût : 0 query
   pour valider, mais nécessite gestion de clé + rotation + révocation
   externe (blacklist Redis).

**Décision** : option **1** (random + DB-lookup).

**Justifications** :
- **Cohérence** avec Phase 9-BOOT (`handoff_kyc_orchestrator` utilise déjà
  `secrets.token_urlsafe(32)` + lookup `handoff_pending.magic_link_token`).
- **Révocation immédiate** : un `UPDATE direct_links SET revoked_at = NOW()`
  est instantanément effectif. Avec JWT, il faut un mécanisme de blacklist.
- **Pas de gestion de clé de signature** : `VAULT_ENVELOPE_KEY` (Phase 9-BOOT)
  reste réservé à l'enveloppe de secrets longue-durée, pas aux tokens
  éphémères qui peuvent rester en DB.
- **Performance acceptable** : la table `direct_links` est indexée sur
  `token_hash` (UNIQUE), 1 query = ~1ms. Pas un goulot pour notre charge.
- **Sécurité égale** : 256 bits d'entropie = équivalent crypto à un JWT signé.

**Conséquences** :
- Chaque validation = 1 SELECT + 1 INSERT audit. Si la charge devient
  critique (>1000 RPS soutenu), envisager un cache Redis read-through ou
  passer à HMAC.
- Le SHA-256 du token est stocké en DB ; le token brut quitte le serveur
  uniquement dans l'URL et n'est jamais re-écrit ailleurs.
- Pas d'incompatibilité avec un futur passage à JWT — le `token_hash` peut
  cohabiter avec un format `<jwt>.<sig>` côté client.

---

## ADR-08 — `handoff_pending` reste séparé de `direct_links`

**Date** : 2026-04-29 (Phase 9A)

**Contexte** : Phase 9-BOOT a créé `handoff_pending` (avec `magic_link_token`)
pour les KYC/card. Phase 9A introduit `direct_links` qui pourrait
techniquement absorber ces tokens.

**Décision** : conserver `handoff_pending` distinct de `direct_links`.

**Justifications** :
- **Sémantiques différentes** : `handoff_pending` modélise un *état métier*
  (pause/resume du pipeline, schedule de relances 1h/12h/24h, escalation
  Slack). `direct_links` modélise une *primitive de sécurité* (token,
  validation, audit).
- **Une refonte rétrocompatible** sera faite en **Phase 9P** : `handoff_pending`
  conservera son rôle, mais `magic_link_token` deviendra une référence
  (`link_id` UUID) vers une entrée `direct_links`. Cela découple « état du
  handoff » de « token cryptographique ».
- **Risque de régression** : tenter la fusion en 9A casserait les tests
  9-BOOT et l'orchestrateur d'`account_creator`. Garder l'isolement entre
  phases protège la non-régression.

**Conséquences** :
- Phase 9P (« injection liens directs livrables ») devra créer une
  migration qui ajoute `handoff_pending.direct_link_id UUID FK → direct_links.link_id`,
  backfille à partir des magic_link_token existants, puis nettoie la
  colonne magic_link_token quand tout est migré.
- D'ici là, deux tables coexistent. Pas de duplication des données : les
  tokens 9-BOOT ne sont pas dans `direct_links`.

---

## ADR-09 — Découpage du Setup Wizard en 4 étapes (Brand / Pricing / Catalog / Ops)

**Date** : 2026-04-30 (Phase 9B)

**Contexte** : le master plan V9 indiquait « Phase 9B : Setup Wizard Ahmed
4 étapes (4h) » sans détailler lesquelles. Une décision architecturale
nécessaire pour avancer en autonome.

**Décision** : 4 étapes séquentielles dans cet ordre :

1. `brand_identity` — platform_name, logo_url, primary_color, support_email,
   default_locale, default_timezone, default_currency
2. `pricing_baseline` — base_currency, minimum_margin_pct (≥ 50% per CDC),
   default_vat_pct, 15 coefficients (préparation Phase 9C)
3. `service_catalog` — enabled_packs (subset de 9 packs : E-Commerce S/M/L,
   SaaS S/M/L, Mobile, API B2B, Custom), featured_pack, accept_custom_briefs
4. `operations_defaults` — hostinger_default_plan (kvm1/2/4/8),
   backup_retention_days (7-365), refund_sla_hours (1-168), AI router split
   Claude/Perplexity/Manus/Internal (somme = 100%)

**Justifications** :
- **Dépendance logique** : identité → prix → offre → exécution. Pas de
  référence forward dans aucune étape.
- **15 coefficients** : explicite dans le brief (master plan #8). Listés
  dans `COEFFICIENT_KEYS` avec validation Pydantic stricte (set requis,
  pas de doublon).
- **Marge ≥ 50%** : explicite dans le brief (master plan « marge >= 50% »).
  Encodé en `Field(ge=MIN_MARGIN_PCT=50)` non-modifiable côté UI.
- **AI router somme à 100** : prépare la Phase 9D (`AI Router` master plan
  #16 : « Claude 80% / Perplexity 15% / Manus 5% / Internal V8.5 ») avec
  un model_validator strict.

**Conséquences** :
- Phases dépendantes :
  - 9C lit `platform_config.pricing_json` pour `pricing_engine`.
  - 9D lit `platform_config.operations_json.ai_router_*` pour le routeur.
  - 9G lit `platform_config.operations_json.hostinger_default_plan`.
  - 9N (dashboard admin) implémentera l'UI du wizard.
- Si plus tard une 5ème étape devient nécessaire (e.g. « Compliance
  defaults »), elle peut être ajoutée à `WIZARD_STEP_ORDER` sans casser
  les commits existants car `platform_config.version` permet la migration.

---

## ADR-10 — Migration 045 (et non 038) pour le Setup Wizard

**Date** : 2026-04-30 (Phase 9B)

**Contexte** : le master plan réservait les migrations 037-047 :
- 037 : Phase 9A (`direct_links`) ✅ posée
- 038 : Phase 9H (`billing_full`) — à venir
- 039 : Phase 9G (`hostinger_provisioning`) — à venir
- 040 : Phase 9D (`ai_decisions_log`) — à venir
- 041 : Phase 9C (`pricing_history`) — à venir
- 042 : Phase 9J (`audit_trail_immutable`) — à venir
- 043-044 : Phase 9-BOOT (`self_bootstrap`, `mandates_eidas`) ✅ posées

Phase 9B n'avait pas de slot prévu. Décision à prendre : préempter 038,
ou prendre le prochain slot libre.

**Décision** : utiliser **045**.

**Justifications** :
- 038 est explicitement réservé pour `billing_full` (Phase 9H). Préempter
  obligerait à renuméroter le master plan, ce qui crée du désordre dans
  les ADR et la trace historique.
- Postgres applique les migrations en ordre numérique. Tant que 038-042
  ne référencent pas (par FK) les tables de 043-045, l'ordre actuel
  n'introduit aucun blocage. C'est respecté : `setup_wizard_state` et
  `platform_config` sont indépendantes des futures tables `billing` /
  `hostinger` / `ai_decisions` / `pricing_history` / `audit_trail`.
- Plus simple à expliquer dans la doc : « Phase X = migration X+10 dans
  le master plan ; les phases hors plan prennent le prochain numéro libre ».

**Conséquences** :
- Quand les phases 9C-9J seront implémentées, leurs migrations 038-042
  s'inséreront chronologiquement *avant* 043-045 dans la séquence appliquée
  (numérique), même si elles sont créées plus tard. Aucun conflit FK puisque
  ces 5 migrations ne référencent que des tables historiques (≤ 036).
- Les futurs wizards/features doivent suivre la même règle : prochain
  numéro libre. La Phase 9-BOOT (043) est l'exception historique.

---

## ADR-11 — Migration 041 = `intelligence_engine` (et non juste `pricing_history`)

**Date** : 2026-04-30 (Phase 9C)

**Contexte** : le master plan réservait 041 à `pricing_history` uniquement.
Mais Phase 9C nécessite 4 tables coordonnées :
`intelligence_qualifications`, `intelligence_pricings`,
`intelligence_assemblies`, `project_progression`. Trois choix possibles :

1. Une migration par table (037-est déjà occupé, 038-040 réservés à d'autres
   phases — pas pratique).
2. Garder 041 avec juste `pricing_history` et créer 046-048 pour les 3
   autres.
3. Élargir 041 pour englober tout l'Intelligence Engine.

**Décision** : option **3**. La migration 041 contient les 4 tables sous
le nom global `041_intelligence_engine.sql`.

**Justifications** :
- **Cohérence** : les 4 tables sont créées et seedées par la même phase.
  Les FK `intelligence_assemblies.qualification_id → intelligence_qualifications`
  et `intelligence_assemblies.pricing_id → intelligence_pricings` doivent
  exister dans la même transaction. Splitter en 3-4 migrations rend les
  rollbacks et le debug plus pénibles.
- **Evidence_ledger** : un seul seal pour Phase 9C (1 maillon de chaîne)
  au lieu de 4. Plus lisible dans l'audit trail.
- **Master plan inchangé** : 041 reste « Phase 9C ». Le label
  `pricing_history` était un nom interne ; on le conserve via le nom de
  la table (`intelligence_pricings`) qui en est la généralisation.
- Aucun impact sur la numérotation des phases suivantes : 040 reste
  réservé à 9D (`ai_decisions_log`), 042 reste réservé à 9J
  (`audit_trail_immutable`).

**Conséquences** :
- Si plus tard une migration *additive* à Intelligence Engine est
  nécessaire (e.g. un index ou une colonne), elle prend un nouveau
  numéro libre (ex. 046+) et **ne réutilise pas** 041. Idempotence des
  migrations existantes garantie via `CREATE TABLE IF NOT EXISTS`.
- Documentation : si quelqu'un cherche « pricing_history », il trouve
  `intelligence_pricings` dans 041. Le commentaire SQL le mentionne
  explicitement.

---

## ADR-12 — Providers IA : `_do_call()` extrait + `# pragma: no cover` plutôt que vrais tests réseau

**Date** : 2026-04-30 (Phase 9D)

**Contexte** : Phase 9D doit implémenter `ClaudeAIProvider`,
`PerplexityAIProvider`, `ManusAIProvider` — wrappers du SDK
`anthropic` et de `httpx`. La contrainte autonome interdit tout appel
réseau facturable. Trois options pour la coverage :

1. Tester les bodies réseau en mockant `httpx.AsyncClient` et
   `anthropic.AsyncAnthropic` au niveau test.
2. Marquer les bodies entiers `# pragma: no cover`.
3. Extraire le body réseau dans une méthode privée `_do_call()` et la
   marquer `# pragma: no cover` ; garder la méthode `call()` publique
   coverable (notamment l'`if not api_key: raise` est testée).

**Décision** : option **3**.

**Justifications** :
- Les vrais bodies (parsing du `resp.usage`, formatage `messages=[...]`)
  sont du **glue code SDK** simple. Les mocker dans des tests unitaires
  duplique l'effort sans valider quoi que ce soit de vraiment unique :
  on testerait que notre mock ressemble à l'API réelle, pas que le code
  fonctionne réellement.
- Les vraies validations (cohérence prompt, parsing JSON, gestion d'erreurs
  réseau) seront couvertes par un test d'intégration `test_providers_live.py`
  derrière feature flag `CLAUDE_LIVE_TESTS=1` — exécuté manuellement quand
  Ahmed valide le branchement live.
- L'`if not api_key` reste coverable et testé dans la méthode `call()` :
  les tests `test_*_raises_when_no_api_key` continuent de fonctionner.
- `# pragma: no cover` est le pattern coverage.py standard pour ce cas
  (bodies d'intégration externe).

**Conséquences** :
- `providers.py` est à 94% au lieu de 100% : les ~5% manquants sont les
  retours `return await self._do_call(...)`. Acceptable.
- Quand le mode live sera activé, on pourra :
  - soit retirer le pragma si on ajoute des tests d'intégration unitaires
  - soit garder le pragma et ajouter un test E2E live derrière flag
- Pour la prod : aucun impact comportemental — `_do_call()` est appelée
  normalement, juste pas tracée par coverage.

---

## ADR-13 — Random PRNG : `secrets.SystemRandom()` partout pour silence Bandit B311

**Date** : 2026-04-30 (Phase 9D)

**Contexte** : `AIRouter._rng` (pour le pick pondéré) et `with_retry()`
(pour le jitter) ont besoin d'un générateur aléatoire. `random.Random()`
et `random.random()` font le job, mais Bandit signale B311 (PRNG non
crypto) à HIGH confidence.

**Décision** : utiliser `secrets.SystemRandom()` comme PRNG par défaut.

**Justifications** :
- `secrets.SystemRandom` est une sous-classe de `random.Random` qui utilise
  `os.urandom()` — overkill pour un jitter ou un weighted pick, mais
  sémantiquement correct et silencieux pour Bandit.
- Cela élimine les `# noqa: S311` et `# nosec B311` qui pollueraient
  le code et créeraient des warnings ruff RUF100 (le projet n'enable pas
  les règles `S` dans ruff, donc les noqa S311 sont marqués comme inutiles).
- L'overhead perf (~µs par appel) est négligeable : on en fait au plus
  quelques par requête utilisateur.
- Si plus tard on veut une vraie reproductibilité avec seed (tests
  déterministes), on peut injecter `random.Random(seed)` via le paramètre
  `rng` du constructeur.

**Conséquences** :
- Le test `test_weighted_choice_deterministic_with_seed` continue de
  fonctionner car il injecte `random.Random(42)` explicitement.
- Aucun warning Bandit B311 ni Ruff RUF100 dans le module.
- Pour les tests qui nécessitent la reproductibilité (router routage),
  on injecte `random.Random(seed)` ; pour la prod, c'est `SystemRandom`
  par défaut.

---

## ADR-14 — Coexistence `handoff_kyc_orchestrator` (9-BOOT) + `HandoffOrchestrator` (9E)

**Date** : 2026-04-30 (Phase 9E)

**Contexte** : Phase 9-BOOT a livré `handoff_kyc_orchestrator` avec sa
propre table `handoff_pending` (magic_link_token inline). Phase 9A a
livré `direct_links` (framework générique de tokens). Phase 9E doit
livrer un « Handoff Orchestrator » plus large.

Trois options :

1. **Refactor 9-BOOT** pour utiliser `direct_links` partout, fusionner
   `handoff_pending` et `handoff_requests` en une seule table.
2. **Coexistence** : 9-BOOT reste tel quel ; 9E est un nouveau pipeline
   à côté, utilisant `direct_links`.
3. **Tout réécrire** dans 9E et déprécier 9-BOOT.

**Décision** : option **2** (coexistence).

**Justifications** :
- **Non régression V9** : `handoff_kyc_orchestrator` est testé (5 tests
  9-BOOT) et déjà invoqué par `account_creator_orchestrator`. Le casser
  forcerait à réviser 9-BOOT entièrement.
- **Sémantiques différentes** : 9-BOOT modélise un *flux d'activation
  service tier* avec rappels 1h/12h/24h codés en dur ; 9E est *générique*
  (review, paiement, domaine, custom) avec callbacks injectables et
  state machine explicite.
- **Tables distinctes** : `handoff_pending` (9-BOOT) et `handoff_requests`
  (9E) ont des shapes différentes — `handoff_pending` n'a pas de
  `direct_link_id`, `handoff_requests` n'a pas de `magic_link_token`.
  Fusionner exigerait une migration de données complexe.
- **Plan de migration prévu** en **Phase 9P** : ajouter `handoff_pending.
  direct_link_id UUID FK → direct_links.link_id`, backfill via les
  magic_link_token existants, puis dropper la colonne magic_link_token
  une fois la transition complète. Documenté dans ADR-08 (9A).

**Conséquences** :
- Le code consommant les handoffs doit savoir à quel pipeline parler :
  - `account_creator_orchestrator` → `handoff_kyc_orchestrator`
  - tout le reste (Phase 9F+) → `HandoffOrchestrator`
- Documentation `V9_PHASE_9E_REPORT.md` §3.4 explicite cette dichotomie.
- À la fin de la V9 (post-9P), une seule table `handoff_unified` consolidera
  les deux. Pour l'instant, deux tables distinctes mais **toutes deux**
  rattachables à `direct_links` via `direct_link_id`.

---

## ADR-15 — FK rétroactives `project_id` reportées en Phase 9P

**Date** : 2026-04-30 (Phase 9F)

**Contexte** : Phase 9F crée enfin la table canonique `projects`. Avant
9F, les phases 9C/9D/9E utilisaient `project_id TEXT` libre car aucune
table parent n'existait. Maintenant que `projects` existe, on pourrait
ajouter des FK rétroactives sur :

- `intelligence_qualifications.project_id`
- `intelligence_pricings.project_id`
- `intelligence_assemblies.project_id`
- `project_progression.project_id`
- `handoff_requests.project_id`
- `ai_decisions_log.project_id`

Trois options :

1. Ajouter toutes les FK dans la migration 047 (Phase 9F).
2. Convertir colonnes en UUID + FK en Phase 9P (consolidation FK + handoff).
3. Laisser TEXT libre indéfiniment.

**Décision** : option **2** (Phase 9P).

**Justifications** :
- **Données existantes potentiellement inconsistantes** : si la suite de
  tests 9C-9E a inséré des `project_id` arbitraires (UUID ou strings),
  un `ALTER TABLE ... ADD CONSTRAINT FOREIGN KEY` bloquerait la migration.
  Phase 9P prévoit un script de validation + nettoyage avant l'ajout des FK.
- **Type mismatch** : les colonnes existantes sont `TEXT`, le PK de `projects`
  est `UUID`. Un `ALTER COLUMN ... TYPE UUID USING project_id::uuid` peut
  échouer sur des valeurs non-UUID. Phase 9P validera tous les `project_id`
  existants avant la conversion.
- **Phase 9P** est déjà la phase « Injection liens directs livrables »
  (master plan), un moment naturel pour faire le sweep d'unification (FK
  + merger handoff_pending dans handoff_requests, cf. ADR-08).

**Conséquences** :
- Pendant 9F→9O, les phases consommatrices doivent valider elles-mêmes
  que le `project_id` qu'elles utilisent existe dans `projects` (lookup
  applicatif au lieu de FK constraint).
- Risque limité : tous les `project_id` créés post-9F passent par
  `ProjectFactory.create_from_session()`, qui retourne le UUID généré par
  Postgres `gen_random_uuid()`. Donc 100% des nouveaux project_id sont
  des UUID valides.
- Phase 9P aura un script de migration data-aware :
  ```sql
  -- Pseudo-code pour 9P
  DELETE FROM intelligence_qualifications WHERE project_id NOT IN (SELECT project_id::TEXT FROM projects);
  ALTER TABLE intelligence_qualifications ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
  ALTER TABLE intelligence_qualifications ADD CONSTRAINT fk_iq_project FOREIGN KEY (project_id) REFERENCES projects(project_id);
  -- + idem pour les 5 autres tables
  ```

---

## ADR-16 — Découpage du Client Onboarding en 6 étapes (Identity / Brief / Pack / Branding / Technical / Review)

**Date** : 2026-04-30 (Phase 9F)

**Contexte** : le master plan brief V9 disait « onboarding client 6 étapes
(5 min target) » sans détailler les 6. Décision architecturale en autonome.

**Décision** : 6 étapes dans cet ordre :

1. `identity` — qui es-tu ? (email, full_name, company, country, locale, currency)
2. `project_brief` — quoi construire ? (title, description ≥ 30 chars, urgency)
3. `pack_selection` — quel format commercial ? (pack ∈ enabled, accept estimate)
4. `branding` — quelle apparence ? (logo, color, audience, sample copy)
5. `technical_preferences` — quelles contraintes tech ? (stack, locales, domaine)
6. `review_submit` — confirmer et accepter (tos_accepted obligatoire)

**Justifications** :
- **Friction croissante** : on commence par le plus simple (email +
  identité) pour engager le client, on garde les questions plus précises
  (technique) pour la fin quand l'investissement perçu est plus grand.
- **CDC en step 2** : le brief client est l'input principal pour le
  `QualificationEngine` (9C). Le placer tôt (step 2) garantit un texte
  riche qui alimente la suite. Min 30 chars force un effort minimum.
- **Pack en step 3** : après avoir vu le brief, le client choisit son
  format. Si le pack `custom` est sélectionné, le pricing engine retournera
  REQUIRES_MANUAL_QUOTE — flux qui boucle sur Ahmed.
- **Branding et technical séparés** : on aurait pu fusionner, mais ça
  produit un step trop chargé. Séparer permet aussi de skip technical
  pour les clients moins techniques (futur : detect-by-pack et masquer).
- **Review_submit obligatoire** : étape légale (TOS) et de confirmation
  visuelle (résumé des 5 étapes précédentes). Pydantic `tos_accepted=True`
  obligatoire + double-check dans `ProjectFactory`.

**Conséquences** :
- Phase 9N (UI client) implémente les 6 écrans dans cet ordre.
- Phase 9R (E2E tests) testera le funnel d'abandon par étape.
- Si l'analytics montre un drop-off à une étape, la step peut être
  retravaillée sans casser les autres (Pydantic schemas isolés).
- Une 7ème étape « payment_method » pourrait être ajoutée plus tard
  pour pré-remplir le checkout Stripe (Phase 9H), mais on garde 6 pour
  l'instant — c'est cohérent avec le master plan.

---

## ADR-17 — Auth admin token-based (stopgap V9N) plutôt que JWT/RBAC complet

**Date** : 2026-04-30 (Phase 9N)

**Contexte** : Phase 9N expose `/admin/*` — endpoints qui peuvent muter
des états critiques (cost limits, project status, handoff cancel,
direct_link revoke, router policy). Il faut une auth, mais Phase 9J
(« Sécurité Enterprise », 5h) est l'endroit prévu pour le RBAC complet.

Trois options pour 9N :

1. **Pas d'auth** (placeholder, à câbler en 9J).
2. **JWT + role check** maintenant (anticipe 9J).
3. **Token statique** lu depuis env `UBA_ADMIN_TOKEN` (stopgap).

**Décision** : option **3** (stopgap).

**Justifications** :
- Option 1 (pas d'auth) est dangereuse même en dev — quelqu'un pourrait
  hit `POST /admin/projects/{id}/status` par accident.
- Option 2 (JWT/RBAC) duplique l'effort de 9J. Le système d'auth existant
  dans `app/routers/auth.py` est marqué « stub Bootstrap — à durcir »
  donc s'appuyer dessus serait construire sur du sable.
- Option 3 est minimal mais sûr :
  - `secrets.compare_digest()` empêche les timing attacks
  - Si `UBA_ADMIN_TOKEN` n'est pas définie → 503 (refuse TOUT, mode
    fail-closed)
  - Token comparison à chaque requête (pas de cache) → rotation immédiate
  - `token_hint` (4 derniers chars) journalisé pour traçabilité, jamais
    le brut

**Conséquences** :
- Phase 9J devra remplacer `get_current_admin` par un check `JWT.role
  == 'admin'` ou équivalent. Les routers existants ne changeront pas
  (juste la dépendance).
- L'admin token doit être généré par Ahmed (e.g. `openssl rand -hex 32`)
  et placé dans `.env` avec rotation manuelle.
- Pour les tests, on override `get_current_admin` via
  `app.dependency_overrides` — agnostique à l'implémentation interne.
- Audit trail (`admin_actions.token_hint`) permet de reconstituer quel
  token a fait quoi en cas de fuite.
- Limitation acceptée : 1 seul admin (`admin_id='ahmed'`), pas de scopes
  granulaires. Suffit pour la V9 mono-admin.

---

## ADR-18 — HostingerClient : `_do_request` no-cover + 3 garde-fous (Pydantic + payment_id + live gate)

**Date** : 2026-04-30 (Phase 9G)

**Contexte** : Phase 9G doit construire l'intégration Hostinger
(achat domaine, création VPS, SSL, backups). Les achats domaine et la
création VPS sont **facturables** et **irréversibles** (un domaine acheté
n'est pas remboursable). Les standing instructions interdisent ces
opérations en mode autonome.

Plusieurs questions à trancher :

1. Comment garantir qu'aucun appel facturable n'est émis pendant les tests ?
2. Comment empêcher un bug applicatif de déclencher un achat sans paiement ?
3. Comment couvrir le code production-ready quand on ne peut pas appeler
   l'API réelle ?

**Décision** : trois couches de garde-fou + pattern `_do_request` no-cover :

**Couche 1 — Pydantic** : `DomainPurchaseRequest.payment_id =
Field(min_length=8, max_length=120)` et idem pour `VPSCreateRequest`. Un
appel sans payment_id (ou avec un payment_id trop court) est rejeté avant
même d'atteindre la logique métier.

**Couche 2 — `require_payment_id()`** : helper appelé en début de chaque
méthode facturable (`domain_manager.purchase`, `vps_provisioner.
create_instance`). Lève `PaymentIdRequiredError` si manquant. Double
validation explicite avec un message clair (l'opération est nommée).

**Couche 3 — Live gate `UBA_LIVE_HOSTINGER`** : dans
`HostingerClient.request()`, si `require_live=True` (défaut) et que
l'env var n'est pas `1`, on lève `HostingerLiveDisabledError` AVANT
tout appel réseau. Mode fail-closed.

**Pattern `_do_request` no-cover** : la méthode publique `request()` fait
les checks (gate live, headers, validation), puis délègue à
`_do_request()` qui est le seul endroit où `httpx.AsyncClient` est
appelé. `_do_request` est marqué `# pragma: no cover - integration only`.

**Justifications** :
- 3 couches superposées rendent **impossible** un appel facturable
  par accident :
  - Bug Pydantic ? La couche 2 catch.
  - Bug Pydantic + helper ? La couche 3 (live gate) catch.
  - Live gate désactivée par mégarde ? Pas de payment_id → fail-fast.
- `_do_request` no-cover évite de mocker httpx dans les tests
  unitaires (effort sans valeur ajoutée). Les tests d'intégration live
  (derrière feature flag `UBA_LIVE_HOSTINGER=1` + GO Ahmed) couvriront
  ces paths quand on validera la prod.
- Coverage cumulée à 98% reste atteinte malgré le no-cover, car le code
  applicatif au-dessus de `_do_request` (auth headers, gate live, parse
  JSON) est testé via le stub.

**Conséquences** :
- Pour activer le mode live, Ahmed doit :
  1. Vérifier que `HOSTINGER_API_TOKEN` est valide (déjà dans `.env`)
  2. Tester en read-only (`search`, `list_plans`) — gratuit
  3. Pour le 1er achat : `export UBA_LIVE_HOSTINGER=1` + GO explicite à
     l'orchestrateur, avec un payment_id valide issu de Phase 9H.
- **Ne jamais commit `UBA_LIVE_HOSTINGER=1`** dans CI/CD. La gate doit
  rester un opt-in manuel par environnement.
- En production, un test périodique pourrait échantillonner
  `HostingerClient.request("GET", "/health", require_live=True)` pour
  s'assurer que la connectivité fonctionne — sans coût réel.
- Migration future : ajouter une FK
  `hostinger_resources.payment_id → payments.payment_id` quand Phase 9H
  créera la table `payments`. Reportée en Phase 9P (cohérence avec ADR-15).

---

## ADR-19 — Tokens IA INVISIBLES dans les invoices client

**Date** : 2026-04-30 (Phase 9H)

**Contexte** : Phase 9D a livré `ai_decisions_log` qui trace chaque appel
LLM (provider, tokens_in, tokens_out, cost_usd, latency). Phase 9H génère
des invoices client. Question : ces métriques internes doivent-elles
apparaître dans l'invoice ?

**Décision** : **non**. Les invoices client ne référencent JAMAIS
`ai_decisions_log` ni aucune métrique IA. Le client voit uniquement :
- Description du projet
- Montant HT / TVA / TTC
- Numéro de facture, date, country

**Justifications** :
- **Modèle économique** : UBA Studio facture un *projet* livré, pas une
  consommation IA token-par-token.
- **Confidentialité contractuelle** : exposer "votre projet a coûté
  $X.YZ en appels Claude" laisserait penser au client qu'il pourrait
  négocier sur cette base. Or le coût AI est ~5% du prix final.
- **Simplicité** : une invoice "UBA Studio Pack saas_medium = 12 000 €
  TTC" est immédiatement compréhensible.
- **Conformité comptable** : les autorités fiscales attendent une
  description du service livré, pas un détail technique.

**Implémentation** :
- `invoice_generator.render_html()` n'utilise QUE les champs structurés
  de `Invoice`. `Invoice.metadata` est ignoré dans le rendu HTML.
- **Test dédié** `test_render_html_does_not_leak_ai_metadata` injecte
  des termes interdits (`claude`, `tokens_in`, `cost_usd`) dans
  `invoice.metadata` puis assert qu'aucun n'apparaît dans le HTML.

**Conséquences** :
- Si une admin invoice détaillée est requise un jour (comptabilité
  interne), créer un endpoint `/admin/invoices/{id}/details` distinct
  du rendu client.
- Les analytics FinOps (Phase 9N `/admin/ai/cost-dashboard`) restent
  internes et n'ont rien à voir avec les invoices.

---

## ADR-20 — Idempotency Stripe via `webhook_events.idempotency_key UNIQUE`

**Date** : 2026-04-30 (Phase 9H)

**Contexte** : Stripe peut retransmettre un même webhook plusieurs fois
(timeout serveur, retry exponentiel). Si on traite l'event 2 fois, on
peut valider 2 fois un projet (UPDATE payments × 2 + callback resume × 2).

**Décision** : index `UNIQUE` sur `webhook_events.idempotency_key` +
`INSERT ... ON CONFLICT DO NOTHING RETURNING event_db_id`.

**Justifications** :
- **Source de vérité unique** : la DB est le seul état partagé entre
  workers. Un index UNIQUE garantit l'unicité même sous concurrence
  multi-process.
- **Pas de dépendance externe** (Redis), pas de cache à invalider.
- **Replay tolérant** : 2 process qui reçoivent le même event en
  parallèle → seul le 1er gagne le INSERT, le 2ème reçoit
  `WebhookAlreadyProcessed` et retourne 200 OK à Stripe (qui arrête
  de retry).
- **Audit trail naturel** : `webhook_events` contient l'historique
  complet, requêtable pour debug.

**Implémentation** :
```python
row = await conn.fetchrow(
    "INSERT INTO webhook_events (...) VALUES ($1, ...) "
    "ON CONFLICT (idempotency_key) DO NOTHING RETURNING event_db_id",
    event_id, ...
)
if row is None:
    raise WebhookAlreadyProcessed(event_id)
```

**Conséquences** :
- Si le dispatch crash après l'INSERT, l'event est marqué "vu" mais
  pas processed. Un retry Stripe ne re-déclenchera pas le dispatch.
  → si le dispatch est critique, ajouter un endpoint admin
  `/admin/webhook-events/{id}/replay` (Phase 9N+).
- Pour les webhooks d'autres sources (Hostinger, Resend) : même pattern,
  `webhook_events.source` distingue.
