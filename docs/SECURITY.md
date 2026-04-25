# UBA — Politique et bonnes pratiques de securite

---

## 1. Modele de menace

UBA traite **donnees fiscales, juridiques et financieres** d'un cabinet algerien. Les principales menaces:

1. **Fuite de donnees client** (RGPD-DZ, art. 7 loi 18-07).
2. **Compromission du compte CEO** (Ahmed) → controle integral.
3. **Manipulation des decisions UBA** (poisoning des regles ou des donnees d'apprentissage).
4. **Indisponibilite** au mauvais moment (deadline TVA, cloture annuelle).
5. **Supply-chain attack** (deps Python/npm malveillantes).

---

## 2. Politique de mot de passe

- **Longueur minimale**: 14 caracteres.
- **Complexite**: au moins 1 majuscule, 1 minuscule, 1 chiffre, 1 symbole.
- **Rotation**: pas obligatoire (NIST SP 800-63B), sauf en cas de breach connu.
- **Stockage**: bcrypt cost 12 (deja configure dans `app/auth/password.py`).
- **Anti-bruteforce**: rate limit 5 tentatives / 15 min / IP, lock-out compte 30 min.

Outils recommandes pour les utilisateurs: 1Password, Bitwarden, KeePassXC.

---

## 3. Authentification a 2 facteurs (2FA)

Toujours **TOTP RFC 6238** (Google Authenticator, Authy, Aegis).

- Active obligatoire pour les roles: **admin**, **editor**.
- Active recommande pour: **viewer**.
- Codes de recovery: 8 codes a usage unique, generes au setup, affiches **une seule fois**.

Reset 2FA: necessite l'admin (toi) + verification offline (telephone).

---

## 4. Reponse a incident

### 4.1 Detection
3 sources:
- Sentry (erreurs applicatives anormales),
- Datadog (anomalies metrique),
- Audit log (`/api/v1/analytics/audit/tail`) — actions sensibles.

### 4.2 Triage (15 min)
1. Identifier le **type** (data leak / compromise / DoS / bug).
2. Identifier le **scope** (combien de users / quelle data).
3. Decider si **arret immediat** est requis (`POST /admin/maintenance/start`).

### 4.3 Containment (1h)
- **Compromise compte**: revoke tous tokens, force logout, reset password.
- **Compromise serveur**: snapshot disk, isolation reseau (Hetzner > Server > Power off), restore from backup.
- **Data leak**: notifier Ahmed dans l'heure, identifier les donnees touchees.

### 4.4 Notification (72h max)
Obligation legale CNDP en cas de fuite de donnees personnelles.
Template fourni dans `docs/incidents/cndp_template.md`.

### 4.5 Post-mortem (7 jours)
Analyse cause racine, action items, mise a jour du registre des risques.
Template: `docs/incidents/postmortem_template.md`.

---

## 5. Donnees: classification et retention

| Categorie                       | Exemples                       | Retention | Chiffrement |
|---------------------------------|--------------------------------|-----------|-------------|
| Audit events                    | login, action critiques        | 5 ans     | TLS + DAR   |
| Donnees fiscales clients        | NIF, factures                  | 10 ans    | TLS + DAR   |
| Donnees personnelles employes   | nom, email, telephone, salaire | 5 ans apres depart | TLS + DAR |
| Logs techniques                 | requetes HTTP, exceptions      | 90 jours  | TLS         |
| Backups DB                      | snapshots                      | 90 jours  | AES-256-CBC |
| Tokens API (encrypted at rest)  | wizard                         | rotation 90j | Fernet  |

DAR = Data At Rest (chiffrement disque LUKS sur le VPS).

---

## 6. Gestion des secrets

### 6.1 Au runtime
Les secrets sont injectes via:
1. `.env.production` (chmod 600, jamais commit),
2. **HashiCorp Vault** (deja deploye, port 8200).

### 6.2 Au repos
- `deploy/config/credentials.enc` chiffre Fernet (cle locale chmod 600).
- `terraform/terraform.tfvars` jamais commit (`.gitignore`).
- Secrets HashiCorp Vault chiffres AES-256.

### 6.3 Rotation
- Tokens API providers: **tous les 90 jours**.
- JWT secret: **180 jours**.
- Mots de passe DB: **180 jours**.
- Cle Fernet wizard: **180 jours** (re-chiffre les credentials).

### 6.4 Detection de fuite
- Pre-commit hook `trufflehog` (a installer).
- Workflow CI `security-scan.yml` cron 03:00 UTC.

---

## 7. RGPD / Loi 18-07 (Algerie)

UBA respecte la **loi 18-07 du 10 juin 2018** relative a la protection des
personnes physiques dans le traitement des donnees a caractere personnel.

### 7.1 Bases legales
- **Consentement explicite** (case a cocher explicite, pas de pre-cochee).
- **Necessite contractuelle** pour les donnees fiscales.
- **Obligation legale** pour la conservation 10 ans.

### 7.2 Droits des personnes
- **Droit d'acces**: endpoint `GET /api/v1/users/{id}/export` (renvoie ZIP JSON).
- **Droit de rectification**: UI `/profile`.
- **Droit a l'oubli**: endpoint `DELETE /api/v1/users/{id}` (anonymise + 30j de quarantaine puis hard-delete).
- **Portabilite**: format JSON ou CSV.

### 7.3 Registre des traitements
Maintenu dans `docs/registre_traitements.md` (a creer apres le 1er deploiement).
Contenu obligatoire:
- Finalite du traitement,
- Categories de donnees,
- Destinataires,
- Duree de conservation,
- Mesures de securite.

---

## 8. Headers de securite (verification)

UBA configure par defaut les headers suivants (verifie par `production_readiness/test_security_headers.py`):

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; ...
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

---

## 9. CORS

Whitelist stricte:
```python
CORS_ORIGINS = [
    "https://uba.dendani.dz",
    "https://www.uba.dendani.dz",
]
```
**Jamais** `*` en production.

---

## 10. Rate limiting

Configurations par defaut dans `app/middleware/rate_limiter.py`:
- **Authentifie**: 100 req / minute / user.
- **Anonyme**: 30 req / minute / IP.
- **Login attempts**: 5 / 15 min / IP.
- **Admin actions**: 200 / minute / user.

Bypass possible via header `X-UBA-API-Key` pour les workers internes.

---

## 11. Audit trail

Tout est loggue dans `audit_events` (table append-only). Schema:
```sql
event_id, actor (user_id), action (string),
target_type, target_id, payload (jsonb),
ip_address, user_agent, created_at
```

Requetes utiles:
- Qui a modifie une regle X dans la derniere semaine?
- Quels logins echoues sur compte Y?
- Quelles decisions UBA en faible confiance?

Exposees via `/api/v1/analytics/audit/tail`, `/audit/search`.

---

## 12. Supply-chain hygiene

### 12.1 Pinning
- Python: `requirements.txt` avec versions exactes (`==`).
- Frontend: `package-lock.json` commit.
- Docker: tags fixes (`postgres:16.4-alpine`, pas `postgres:latest`).
- Terraform: providers pinned (`~> 1.48`).

### 12.2 Scan automatique
Workflow CI `security-scan.yml`:
- `pip-audit` + `safety` (Python deps),
- `npm audit` (frontend),
- `bandit` (Python SAST),
- `semgrep` (rules auto),
- `trivy` (container + filesystem),
- `trufflehog` (secrets in git).

Issues HIGH+ creent une issue auto.

### 12.3 SBOM
Genere a chaque release tag (workflow `deploy-production.yml` step `sbom-generate` — a ajouter).

---

## 13. Backup & disaster recovery

### 13.1 RPO (Recovery Point Objective)
- 1 heure (backup horaire).

### 13.2 RTO (Recovery Time Objective)
- 30 minutes pour restore postgres + redeploy app.

### 13.3 Procedure DR (haute-niveau)
1. `bash deploy/scripts/restore.sh --from <backup>` sur un VPS frais.
2. Reconfigure DNS Cloudflare vers le nouveau VPS.
3. Verifie smoke tests.
4. Notifie Ahmed.

---

## 14. Acces minimum (least privilege)

Roles UBA:
- **admin**: tout.
- **editor**: CRUD sur les domains/regles, pas de suppression user.
- **viewer**: lecture seule.
- **api**: pour les workers internes, pas d'UI.

Defaut nouveau compte: **viewer**. Promotion explicite par admin.

---

## 15. Audit annuel

Externe recommande:
- Pentest boite blanche 1 fois par an.
- Audit de conformite RGPD/loi 18-07.
- Verification des journaux d'acces > 1 an.

---

*UBA V5.9 / Vague 6 — Securite as code, pas as document.*
