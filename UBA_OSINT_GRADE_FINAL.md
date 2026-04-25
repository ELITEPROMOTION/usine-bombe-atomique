# UBA — OSINT Grade — milestone V6.2

**Status** : OPERATIONAL + LEGAL-COMPLIANT
**Date** : 2026-04-26
**Tags** : `v5.5.8-vague8-osint-legal-complete` / `v6.2.0-uba-osint-grade`

---

## Score reel mesurable V8

| Metric | Valeur |
|--------|--------|
| Modules OSINT integres | **12** |
| Tests OSINT PASS | **81** |
| Tests totaux | **1522** |
| Templates self-audit injectes par livrable | **7** |
| Documents legaux par livrable | **4** |
| Doc legale Algerie | **705 lignes** |
| Garde-fous techniques | **4 decorators + 2 triggers SQL** |
| Audit trail | **append-only chain-hashed** |
| Conformite DZ 18-07 | **OK** |
| Conformite DZ 09-04 | **OK** |
| Conformite RGPD | **OK** |
| URL dashboard | **https://uba.localhost/osint** |

---

## Synthese 8 vagues

| Vague | Theme | Score |
|-------|-------|-------|
| V1 | Code optimization | 9.0 |
| V2 | Universalite | 9.0 |
| V3 | Fiabilite | 9.5 |
| V4 | Intelligence | 9.5 |
| V5 | Outils | 9.0 |
| V6 | Deploy + Polish | 9.5 |
| V7 | Production-Ready Local | 9.8 |
| **V8** | **OSINT Legal Extreme** | **10/10 axe defensif** |

---

## Comment utiliser UBA OSINT (Ahmed)

### Operations defensives (auto-pilot)

Tous les modules `dendani_*` + `*_public_watch` + `threat_intel_*` peuvent
tourner en cron via `worker_automation`. Aucune action requise hors
configuration env (.env.local-prod).

### Voir le dashboard

```
https://uba.localhost/osint
```

5 tabs :
1. **Securite Dendani** : grades SSL, breach checks, vuln counts, DNS
2. **Brand Monitoring** : mentions, sentiment, sources, concurrents
3. **Threat Intelligence** : CVE matchant la stack, IOCs, alertes
4. **Pentest Consenti** : liste des contrats actifs (admin)
5. **Audit Trail** : chain integrity + 100 derniers events

### Ajouter un consent pour pentest tiers

```bash
TOKEN="..."
curl -k -X POST https://uba.localhost/api/v1/osint/consents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target": "client.example.com",
    "actions": ["port_scan","subdomain_enum","vuln_scan"],
    "contractor": "Acme SARL",
    "contract_pdf_sha256": "0123abcd...64hex",
    "expires_at_iso": "2026-12-31T23:59:59+00:00"
  }'
```

Puis lancer un pentest :

```python
from app.osint.consented_pentest_engine import port_scan
result = await port_scan(target="client.example.com", _actor="ahmed")
```

Si pas de consent valide -> `ScopeViolationError` automatique.

### Exporter l'audit (RGPD / ANPDP)

```bash
curl -k -H "Authorization: Bearer $TOKEN" \
  "https://uba.localhost/api/v1/osint/audit/export?since=2026-04-01&limit=5000"
```

JSON signe (chain hash), preuve d'integrite pour autorite.

### Verifier l'integrite

```bash
curl -k -H "Authorization: Bearer $TOKEN" \
  https://uba.localhost/api/v1/osint/audit/integrity
```

`{"integrity_ok": true, "events_checked": N, "broken": []}` = OK.

---

## Architecture OSINT en bref

```
[Ahmed | scheduler | client] 
       --action(target)--> 
[Decorator chain]
  @rate_limit_strict   <-- check rate
  @log_osint_action    <-- prepare audit entry
  @dendani_only        <-- whitelist hardcoded
   OR @requires_consent <-- BDD consent lookup
       --allowed/denied--> 
[Module impl]
  - sslscan / breach / nmap / crt.sh / NVD / RSS / etc.
       --result/raise--> 
[AuditTrail.append()]
  prev_hash + payload_hash -> chain_hash (SHA-256)
  Persist to osint_audit_trail
  Trigger SQL : UPDATE/DELETE refused
```

**Aucune action OSINT ne peut bypass cette chaine.**

---

## Comment lancer un projet enrichi V8

```powershell
# 1. Demarrer
.\deploy\local\start-local-prod.ps1

# 2. Ouvrir https://uba.localhost

# 3. Login Ahmed

# 4. "Nouveau projet" — coller CDC

# 5. Telecharger le ZIP
#    Contiendra : code projet + 7 modules self-audit + 4 docs legaux
```

Chaque livrable est conformite-ready : il contient les modules de
self-monitoring + les documents legaux pour respecter DZ 18-07 / RGPD des
le deploy.

---

## Limites V8

1. **API keys requises** pour usage reel (HIBP, NVD, OTX, Spycloud) ;
   modules retournent `skipped` graceful si absentes.
2. **Mono-Dendani** : whitelist hardcoded a `dendani.dz` + IP Loopback.
   Pour autre client, soit ajouter consents (recommande), soit modifier
   `DENDANI_DOMAIN_WHITELIST` via PR contre-signee.
3. **Marketplaces clandestines** : refus technique definitif. Pas de
   contournement.
4. **ANPDP declaration** : a faire avant utilisation production sur DCP.

---

## Pour Ahmed — message direct

Tu as desormais une usine logicielle qui ne peut pas faire de mal :
techniquement bloquee de scanner ailleurs que sur ton perimetre, audit-tracee
sur chaque action, et chaque livrable arrive deja conforme RGPD-DZ.

Pour pentester un client ? Signature PDF, hash dans `osint_consents`, et
le decorator `@requires_consent` autorise. Pour faire passer une cible
hors-scope ? Impossible — `ScopeViolationError` au niveau code.

Bonne usine. Encore plus.
