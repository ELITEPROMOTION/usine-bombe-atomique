# 10 — Client area integration

L'espace client est livré en deux phases :
- **9M** : frontend (4 pages, 4 composants luxe, mock fixtures).
- **9M-bis** : backend (12 endpoints, JWT client séparé).

## Architecture

```
Frontend (9M)                  Backend (9M-bis)
─────────────                  ──────────────
ClientShell                    JWT client (JWT_CLIENT_SECRET)
  ├── ClientDashboardPage      ├── GET  /client/project
  ├── ClientDeliverablesPage   ├── GET  /client/milestones
  ├── ClientPaymentsPage       ├── GET  /client/activity
  └── ClientProfilePage        ├── GET  /client/deliverables (stub)
                                ├── GET  /client/deliverables/:t/download (stub)
api/client_*.ts                ├── GET  /client/invoices
  safeGet(url, fallback)       ├── GET  /client/invoices/:t/pdf
                                ├── GET  /client/handoffs
api/client_fixtures.ts         ├── GET  /client/profile
  (single source of mocks      ├── PATCH /client/profile/consents
   ADR-31)                     ├── POST /client/profile/gdpr/export (202)
                                └── POST /client/profile/gdpr/erasure (202)
```

## JWT client

Token JWT signé avec `JWT_CLIENT_SECRET` (≥ 32 chars). Issuer
`uba-studio/client`. Claims :
- `sub` : owner_email
- `project_id` : UUID — scope de tous les endpoints
- `iat`, `exp` : standard
- `iss` : `uba-studio/client`

TTL par défaut : 24h. Création :
```python
from app.security.jwt_client import create_client_token
token = create_client_token(
    owner_email="client@example.com",
    project_id=UUID("..."),
)
```

Cf. ADR-33 pour la justification d'un secret distinct du JWT admin.

## Endpoint stubs (à brancher en V10)

- `/client/deliverables` retourne `[]` — table `deliverables`
  absente du schéma V9.
- `/client/deliverables/:token/download` retourne 404.

## Mock data layer (frontend)

`api/client_fixtures.ts` exporte les types et fixtures. Chaque
wrapper `client_*.ts` utilise :

```ts
async function safeGet<T>(path: string, fallback: T): Promise<T> {
  try { return (await apiClient.get<T>(path)).data; }
  catch { return fallback; }
}
```

Pour brancher au backend réel : remplacer `safeGet` par
`apiClient.get` direct. Cf. ADR-31.

## Login flow client (à venir)

V9M-bis ne livre **pas** de login flow client. Les tokens doivent
être créés côté admin (via `create_client_token`) ou via magic-link
email à câbler en V10.

Workflow envisagé V10 :
1. Client visite `/client/login?email=...`
2. Backend POST `/auth/client/request-link` → email avec token
3. Client clique le lien → JS lit le token, l'enregistre dans
   `useAuth` store, redirige vers `/client`.

## AuthGuard frontend

Actuellement, `AuthGuard` ne discrimine **pas** client/admin. Un
admin peut visiter `/client/*` (probablement vide car son token
n'a pas de `project_id`). Pour V10, ajouter un `<ClientAuthGuard>`
qui valide le claim `iss=uba-studio/client`.

## Voir aussi

- [05 — API reference](./05_api_reference.md)
- [16 — Security](./16_security.md)
- `docs/V9_PHASE_9M_REPORT.md`
- `docs/V9_PHASE_9M_BIS_REPORT.md`
