# V9 Phase 9M-bis — Backend `/client/*` endpoints — Final Report

**Date** : 2026-05-01
**Branche** : `feature/vague9-bootstrap` (continuée depuis 9M)
**Statut final** : **PASS**

---

## 1. Résumé exécutif

Phase 9M-bis branche le frontend espace client (Phase 9M) sur le
backend V9 réel :

1. **JWT client** : module `app/security/jwt_client.py` séparé du JWT
   admin. Secret distinct (`JWT_CLIENT_SECRET`), issuer distinct
   (`uba-studio/client`), claim **`project_id`** (UUID) qui scope
   tous les endpoints — un client ne peut accéder qu'au project pour
   lequel son token est émis. Cf. ADR-33.
2. **Services dérivés** : module `app/saas_factory/client_area/`
   avec `ClientDashboardService`, `ClientPaymentsService`,
   `ClientProfileService`. Réutilisation des tables existantes
   (projects, payments, invoices, handoff_requests, audit_events,
   user_consents, data_export_requests, data_erasure_requests) —
   **aucune nouvelle migration**.
3. **Mappings dérivés** : status DB (8 valeurs) → status UI (5),
   progress_pct (0–100), 5 milestones standard derivées du status.
   Cf. `_status_mapping.py` + `_milestones.py`.
4. **12 endpoints** sous `/api/v1/client/*` :
   - GET `/project`, `/milestones`, `/activity`
   - GET `/deliverables` (stub liste vide), `/deliverables/{token}/download`
   - GET `/invoices`, `/invoices/{token}/pdf` (302 redirect),
     `/handoffs`
   - GET `/profile`, PATCH `/profile/consents`
   - POST `/profile/gdpr/export` (202), POST `/profile/gdpr/erasure` (202)
5. **Auth fail-closed** : 503 si `JWT_CLIENT_SECRET` non configuré,
   401 si pas de Bearer, 403 si token invalide.

| Indicateur | Valeur | Cible |
|---|---|---|
| Endpoints livrés | 12 | 12 |
| Modules livrés | 8 (jwt_client + 7 client_area) | 8 |
| Tests Phase 9M-bis | 40 / 40 ✅ | toutes |
| Tests cumulés (9-BOOT à 9M-bis) | **758 / 758** ✅ | toutes |
| Coverage Phase 9M-bis | **~99%** | ≥ 90% |
| Coverage cumulée | **98%** | ≥ 90% |
| Ruff | 0 erreur (1 autofix + 1 manuel SIM105) | 0 |
| Bandit (≥ Medium) | 0 issue | 0 |
| Migration | 0 (réutilise V9F + V9H + V9I + V9A) | 0 |
| Auto-fix loop | 1 itération (deux ProjectNotFoundError) | ≤ 3 |

---

## 2. Livrables

### 2.1 JWT client (`backend/app/security/`)

| Fichier | LOC |
|---|---|
| `jwt_client.py` | 131 |

API :
- `is_jwt_client_mode_enabled()` → bool
- `create_client_token(*, owner_email, project_id, ttl_minutes)` → str
- `verify_client_token(token)` → `JWTClientPayload`
- Erreurs : `JWTClientConfigMissingError`, `JWTClientError`

### 2.2 Services (`backend/app/saas_factory/client_area/`)

| Fichier | LOC | Rôle |
|---|---|---|
| `__init__.py` | 27 | exports |
| `_status_mapping.py` | 48 | DB status ↔ UI status + progress_pct |
| `_milestones.py` | 118 | 5 milestones dérivées |
| `dashboard_service.py` | 207 | project + milestones + activity |
| `payments_service.py` | 131 | invoices + handoffs |
| `profile_service.py` | 164 | profile + consents + GDPR |

### 2.3 Router (`backend/app/routers/client.py`)

12 endpoints, 369 LoC :

| Method | Path | Auth | Comment |
|---|---|---|---|
| GET | `/project` | client JWT | scope project_id |
| GET | `/milestones` | client JWT | dérivées du status |
| GET | `/activity?limit=N` | client JWT | filter via `payload_json->>'project_id'` |
| GET | `/deliverables` | client JWT | stub liste vide (table absente) |
| GET | `/deliverables/{token}/download` | client JWT | 404 (stub) |
| GET | `/invoices` | client JWT | join payments+invoices |
| GET | `/invoices/{token}/pdf` | client JWT | 302 → `pdf_url` ou 409 |
| GET | `/handoffs` | client JWT | tri ouvert d'abord |
| GET | `/profile` | client JWT | + consents agrégés |
| PATCH | `/profile/consents` | client JWT | toggle marketing/analytics |
| POST | `/profile/gdpr/export` | client JWT | 202 + request_id |
| POST | `/profile/gdpr/erasure` | client JWT | 202 + executable_after |

### 2.4 Tests (40)

**`test_jwt_client.py`** (13) :
- `TestSecretConfig` (5) : env enabled/disabled, raise sans secret,
  raise si trop court.
- `TestCreateAndVerify` (8) : round-trip, invalid email/ttl, empty
  token, garbage, expired, wrong issuer, missing project_id, invalid
  UUID.

**`test_client_endpoints.py`** (27) :
- `TestStatusMapping` (4) : derive_ui_status known/unknown,
  progress_pct croissant.
- `TestMilestones` (4) : 5 items générés, status par projet,
  next_milestone, après archived.
- `TestClientDashboardService` (8) : project 404, aggregation,
  unknown pack fallback, milestones, activity limit/maps.
- `TestClientPaymentsService` (3) : invoice status mapping,
  empty, handoff cta_label.
- `TestClientProfileService` (4) : agrégation consents, 404,
  export 404, export insert.
- `TestEndpointsAuth` (4) : no auth 401, garbage 403, no secret 503,
  deliverables 200 empty.

---

## 3. Architecture

### 3.1 JWT client séparé du JWT admin (ADR-33)

V9J avait livré un JWT admin. La tentation aurait été de réutiliser
le même secret, en différenciant juste par claim `role`. Pourquoi
on a refusé :

1. **Compromis blast radius** : si le secret admin fuit, un attaquant
   peut signer un token client. Inverse aussi (moins grave). Avec
   deux secrets, la fuite d'un seul ne contamine pas l'autre.
2. **Politiques de rotation différentes** : on peut vouloir rotater
   le secret client tous les mois (volume élevé, rotation moins
   risquée), tandis que le secret admin reste fixe (rotation
   coûteuse, peu de tokens en vol).
3. **Issuer distinct** : `uba-studio/client` vs `uba-studio/admin`.
   Le décodeur `verify_client_token` rejette explicitement les
   tokens admin, et vice-versa via `issuer=ISSUER` dans `jwt.decode`.

**Claim `project_id` scope-bound** :
- Tous les endpoints `/client/*` lisent `principal.project_id` et
  filtrent les requêtes DB sur cette valeur.
- Un client A ne peut **pas** accéder aux données du client B en
  manipulant l'URL — son token ne contient que son project_id.
- Le client peut avoir plusieurs projets ? V9 dit non — un compte
  client = un projet. Pour multi-projet futur, le claim deviendrait
  `project_ids: list[UUID]` ou un endpoint `/projects` listerait les
  projets accessibles.

### 3.2 Pas de nouvelle migration

L'objectif initial pouvait être de créer une table
`client_dashboard_state` avec `progress_pct`, `next_milestone`, etc.
On a refusé : c'est une vue dérivée du status. Source de vérité = la
table `projects` et son status enum. Le UI compute la vue via
`_status_mapping.py` + `_milestones.py`.

Avantages :
- Pas de désynchronisation possible entre le status réel et le
  dashboard.
- Pas de job d'update pour maintenir une nouvelle table.
- Si on change le state machine (V10), on update juste le mapping.

Trade-off :
- L'UI est une **estimation**. Si un milestone réel arrive en retard
  ou en avance, ça ne se voit pas. Pour vraie traçabilité, il
  faudrait une table `project_milestones` explicite. Hors scope
  V9M-bis.

### 3.3 Endpoints `/deliverables` stub

La table `deliverables` n'existe pas dans le schéma V9. Le frontend
9M attendait des fichiers téléchargeables (Brief, Architecture,
Maquettes...). Deux options :
1. Créer la table + un seed → out of scope (changement de domaine).
2. Renvoyer une liste vide → frontend affiche "aucun livrable
   disponible".

On a choisi 2. Le frontend gère déjà l'état vide proprement (panel
`Aucun livrable disponible pour l'instant`). Branchement réel d'une
phase deliverables future remplacera juste l'implémentation du
endpoint.

### 3.4 Endpoints GDPR : 202 Accepted

`POST /profile/gdpr/export` et `/erasure` retournent **202 Accepted**
au lieu de 200/201. Sémantique HTTP : "la requête a été enregistrée
mais le traitement est asynchrone". Cohérent avec la réalité :
- Export → un job background va sérialiser les données et envoyer
  un mail au client.
- Erasure → la fenêtre 30j (ADR-26) avant exécution rend l'opération
  intrinsèquement asynchrone.

Le frontend (Phase 9M) accepte 200 ou 202 (les wrappers
`requestGdprExport` / `requestGdprErasure` ne discriminent pas).

### 3.5 Endpoint PATCH consents : idempotent

`PATCH /profile/consents` accepte un payload `{consent_marketing,
consent_analytics}` et synchronise l'état. Implementation :
- Si target=true et déjà actif → no-op (silencieux via
  `contextlib.suppress(ConsentAlreadyRecordedError)`).
- Si target=true et inexistant → record_consent.
- Si target=false → revoke_consent (qui est no-op si déjà revoqué).

Le client peut donc PATCH avec n'importe quel état désiré, le
backend converge. Aucun risque d'erreur "consent déjà existant"
exposée à l'UI.

---

## 4. Conformité

| Master plan | Statut |
|---|---|
| #34 JWT client séparé | ✅ |
| #35 12 endpoints `/client/*` | ✅ |
| #36 Services dérivés (no migration) | ✅ |
| GDPR Art 15/17/20 exposés au client | ✅ |
| Backend regression aucune | ✅ (758/758) |
| Coverage critique ≥ 99% | ✅ |
| Coverage globale ≥ 90% | ✅ (98%) |
| Conventional commit | ✅ |
| Pas de tag autonome | ✅ |

---

## 5. Quality Gates V8.5

| Gate | Statut |
|---|---|
| pytest (758 cumulés) | ✅ PASS |
| ruff check | ✅ PASS (0 erreur, 1 autofix + 1 manuel SIM105 contextlib.suppress) |
| bandit -ll | ✅ PASS (0 issue Medium+) |
| coverage globale ≥ 90% | ✅ PASS (98% cumulé) |

---

## 6. Limitations & dette technique

- **Auth `AuthGuard` frontend ne discrimine pas client/admin** :
  9M-bis livre la backend auth, mais le frontend `AuthGuard` actuel
  laisse passer indifféremment sur `/` et `/client/*`. À ajouter en
  phase sécurité frontend (un `<ClientAuthGuard>` qui check le claim
  `iss`/role du token côté JS).
- **Login flow client absent** : pas d'endpoint `/auth/client/login`.
  Les tokens client doivent être créés via `create_client_token`
  côté admin (ou via magic-link email). Phase login flow ultérieure.
- **Table `deliverables` absente** : endpoint stub renvoie liste vide.
  Phase deliverables future ajoutera la table + un endpoint complet.
- **Activity feed peu peuplé** : le filtre
  `payload_json->>'project_id'` ne match que les events qui
  encodent project_id dans leur payload. Beaucoup d'events V9 ne
  le font pas → activity feed souvent vide. À normaliser dans une
  phase observabilité ultérieure (ADR-future).
- **Multi-project clients non supporté** : le claim `project_id`
  est singulier. Si un client a 3 projets, il doit avoir 3 tokens.
  Pour multi-project, refonte du claim en `project_ids: list[UUID]`
  + endpoint `/client/projects` listant les projets accessibles.
- **Pas de rate limiting spécifique `/client/*`** : utilise le
  middleware global. Si un client malveillant abuse de
  `POST /gdpr/erasure`, on n'a pas de quota dédié. À ajouter en
  phase ops.
- **Pas de logs `client_actions`** : les actions client (consent
  toggle, gdpr request) ne sont pas tracées dans une table dédiée.
  Visibles dans `audit_events` (via le middleware) mais pas dans une
  vue dashboard admin. À ajouter si besoin compliance.
- **`/invoices/{token}/pdf` requires `pdf_url` populated** : si le
  job async qui génère le PDF n'a pas encore tourné, on retourne 409.
  Le frontend devrait afficher un état "PDF en cours de génération"
  plutôt que une erreur sèche. À polir frontend-side.

---

## 7. État cumulé V9 sur la branche

| Phase | Commit | Tests | Coverage | LoC |
|---|---|---|---|---|
| 9-BOOT | `bba1fa1` | 58 | 97% | +2 970 |
| 9A | `71896b1` | +44 | 98% | +1 809 |
| 9B | `7db1b10` | +39 | 98% | +1 549 |
| 9C | `b668e2f` | +49 | 98% | +2 827 |
| 9D | `9927877` | +66 | 98% | +2 603 |
| 9E | `2c4ef0e` | +29 | 98% | +1 558 |
| 9F | `bcdbdb9` | +48 | 99% | +1 856 |
| 9N | `f227b0b` | +45 | 98% | +2 189 |
| 9G | `8ffc735` | +46 | 98% | +2 315 |
| 9H | `6b83ed7` | +67 | 98% | +2 891 |
| 9R | `b8d590a`+`b34b88a` | +9 | 98% | +700 |
| 9J | `ec92b4c` | +49 | 98% | +1 610 |
| 9P | `7711c68` | +22 | 98% | +1 082 |
| 9I | `1cff9e2` | +43 | 98% | +1 800 |
| 9K | `fbdc83f` | +42 | 98% | +1 731 |
| 9L | `6828047` | +62 | 98% | +2 218 |
| 9M | `b2ae431` | 0 (frontend) | n/a | +1 964 |
| **9M-bis** | `(à venir)` | **+40 (758)** | **98%** | ~+1 730 |

**Backend cumulé** : 17 phases backend, 758 tests verts, ~31 800 LoC,
25 ADR (07–33). Frontend 9M : 1 520 LoC, build Vite 510 KB / 152 KB
gzip.

---

## 8. Statut & next-step

```
PHASE 9M-BIS : PASS ✅
Branche  : feature/vague9-bootstrap
Commit   : (à créer après ce rapport)
Tag      : NON POSÉ
```

**Phases du master plan non livrées** :
- 9O (design system luxe étendu) — frontend
- 9Q (n8n workflows) — outil externe
- 9S (22 docs rédigés) — documentation

**Recommandation** : la **stack V9 complète** (backend + frontend +
client area câblé) est livrée. 18 phases, 758 backend tests verts,
frontend Vite OK. Bon moment pour :
1. **STOP + tag `v9.0.0-rc1`** : merge en main, déploiement staging.
   Les 3 phases restantes (9O frontend, 9Q n8n, 9S docs) sont **non-
   bloquantes** pour MVP.
2. **9O** : design system étendu si on veut polir avant rc1.
3. **9S** : si on a besoin de la doc avant le déploiement.
