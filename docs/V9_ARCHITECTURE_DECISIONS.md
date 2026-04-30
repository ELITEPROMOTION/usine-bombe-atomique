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
