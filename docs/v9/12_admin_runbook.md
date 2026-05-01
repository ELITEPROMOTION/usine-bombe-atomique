# 12 — Admin runbook

## Auth admin

### Production : JWT mode (Phase 9J)

```bash
# Générer un token admin
python -c "
from app.security.jwt_admin import create_admin_token, AdminRole
print(create_admin_token(admin_id='ahmed', role=AdminRole.ADMIN))
"
```

Roles : `admin` (full), `viewer` (read-only), `auditor` (read +
admin_actions read).

### Legacy mode (Phase 9N, fallback)

`X-Admin-Token: <UBA_ADMIN_TOKEN>` — header pour les tools qui ne
peuvent pas faire JWT. Désactivé si `JWT_ADMIN_SECRET` configuré et
prioritaire.

## Tâches courantes

### Issuer un token client

```python
from app.security.jwt_client import create_client_token
from uuid import UUID

token = create_client_token(
    owner_email="client@example.com",
    project_id=UUID("..."),
    ttl_minutes=24*60,    # 24h
)
# Envoyer ce token au client (email, magic-link, etc.)
```

### Override un handoff

```bash
curl -X POST https://api.ubastudio.io/api/v1/admin/handoffs/<id>/escalate \
  -H "Authorization: Bearer <admin_token>"
```

L'override est **tracé** dans `admin_actions` (Phase 9J).

### Reset un circuit breaker

Pas d'endpoint dédié en V9. Restart pod = retour CLOSED. Pour
override sans restart, utiliser un Python REPL :

```python
from app.saas_factory.resilience import CircuitBreaker
# (mais le CB est in-memory par-process, donc inaccessible depuis
# un REPL externe — le restart est plus simple)
```

### Activer un kill switch

```bash
# En staging (Kubernetes)
kubectl set env deploy/api UBA_KILL_STRIPE=1
kubectl rollout restart deploy/api

# Vérifier
kubectl exec deploy/api -- env | grep UBA_KILL
```

### Ramper un live mode

```bash
# Activer Hostinger live (prod uniquement)
kubectl set env deploy/api UBA_LIVE_HOSTINGER=1
kubectl rollout restart deploy/api

# Health check doit montrer warn sur live_modes
curl https://api.ubastudio.io/api/v1/health/v9 | jq '.checks.live_modes'
```

### Inspecter un evidence chain

```sql
SELECT id, actor, chain_hash, created_at
  FROM evidence_ledger
 ORDER BY id DESC
 LIMIT 20;
```

## GDPR

### Vue compliance

```sql
SELECT * FROM v_gdpr_compliance;
```

### Exécuter une erasure (après 30j)

Pas d'endpoint. Lancer manuellement :

```python
from app.saas_factory.legal.gdpr_erasure import GDPREraser
from uuid import UUID

eraser = GDPREraser(pool)
await eraser.execute_erasure(request_id=UUID("..."))
```

Idempotent. Anonymise les colonnes PII des tables non-audit.

### Force erasure (legal hold override)

```python
await eraser.execute_erasure(request_id=UUID("..."), force=True)
```

⚠ Trace dans `admin_actions`. Documenter la raison juridique.

## Voir aussi

- [11 — Deployment](./11_deployment.md)
- [13 — Incident response](./13_incident_response.md)
- [16 — Security](./16_security.md)
- [17 — GDPR](./17_gdpr.md)
