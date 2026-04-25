# UBA — Mode d'emploi CEO Ahmed Dendani

> Generation V7 — Production-Ready Local — 2026-04-25

UBA (Usine Bombe Atomique) est votre usine logicielle personnelle : vous decrivez
un projet en francais, l'usine livre la solution complete (code + Docker + tests).

Ce guide vous donne tous les gestes courants. Pas de jargon, pas de theorie — uniquement les commandes qui marchent.

---

## TLDR — 5 commandes que vous utiliserez

```powershell
# Demarrer UBA
.\deploy\local\start-local-prod.ps1

# Stopper UBA
.\deploy\local\stop-local-prod.ps1

# Sauvegarder
.\deploy\local\backup.ps1

# Restaurer
.\deploy\local\restore.ps1 backup_2026-04-25.tar.gz

# Verifier sante
curl -k https://uba.localhost/api/v1/health
```

---

## 1. Demarrer UBA en local-production (1 commande)

```powershell
.\deploy\local\start-local-prod.ps1
```

**Que fait le script ?**
1. Stoppe la stack dev si elle tourne
2. Verifie l'entree `uba.localhost` dans hosts (eleve admin auto si manquant)
3. Demarre les 10 containers (postgres, redis, vault, sonarqube, backend, 3 workers, frontend, nginx-local)
4. Attend que tout soit healthy (max 120s)
5. Trust le certificat SSL self-signed dans Windows
6. Ouvre `https://uba.localhost` dans le navigateur

**Resultat** : `https://uba.localhost` accessible, login form visible.

**Si SSL warning navigateur** : voir `docs/SSL_LOCAL_NOTICE.md`.

---

## 2. Login

Premier demarrage : creez votre compte via :

```powershell
$body = '{"email":"ahmed@dendani.dz","password":"VOTRE_MOT_DE_PASSE","full_name":"Ahmed Dendani"}'
Invoke-RestMethod -Uri "https://uba.localhost/api/v1/auth/register" -Method POST -ContentType "application/json" -Body $body -SkipCertificateCheck
```

Puis connectez-vous via l'UI :
- URL : https://uba.localhost
- Email : `ahmed@dendani.dz`
- Mot de passe : votre choix au register

Le token JWT est stocke en `localStorage`. Expire au bout de 60 min, refresh auto au login.

---

## 3. Lancer un nouveau projet (3 minutes)

1. Cliquez **Nouveau projet** dans la sidebar (icone fusee, en haut)
2. Donnez un nom slug : ex `dendani-residences-v1` (minuscules, chiffres, tirets)
3. Collez votre **cahier des charges** dans la textarea (min 100 chars, max 50 000)
4. Laissez **Auto-resolution des ambiguites** sur ON (recommande)
5. Cliquez **Lancer le projet**

**Pendant l'execution** :
- 6 etapes visuelles : Intake -> Clarification -> Decomposition -> Execution -> Validation -> Livraison
- Progress bar 0-100%
- Tache courante affichee
- Estimation du temps restant
- Mises a jour temps reel via WebSocket

**Duree typique** : 5-30 min selon complexite.

**A la fin** :
- Statut **Livraison** : telecharger le ZIP
- Decompresser localement
- `docker compose up -d` dans le dossier extrait
- Application disponible sur `http://localhost:8000`

**Si echec** : message d'erreur explicite, bouton **Reessayer** disponible.

---

## 4. Operations courantes (sidebar de gauche)

| Entree menu | Que ca fait |
|-------------|-------------|
| Nouveau projet | Soumettre un nouveau CDC |
| Vue d'ensemble | Dashboard global UBA |
| CEO | Synthese executive (KPIs, metrics) |
| Boite A/B/C (Ahmed Inbox) | Decisions en attente : valider, refuser, demander info |
| Domaines (5) | Status fiscal/juridique/logistique/RH/comptabilite DZ |
| Fleet | Etat de tous les agents UBA |
| Automation | Workflows planifies (27+ tasks ARQ) |
| Cognition | Engine de raisonnement (CoT, ToT, MCTS, etc.) |
| Truth Engine | Verite augmentee + chaines hash |
| Observabilite | Metriques + traces + logs |
| Historique | Tous les projets soumis |

---

## 5. Stopper UBA

```powershell
.\deploy\local\stop-local-prod.ps1
```

Les volumes Docker (donnees postgres, redis, sonar) sont **preserves** par defaut.

Pour repartir de zero (perte des donnees) :
```powershell
.\deploy\local\stop-local-prod.ps1 -Volumes
```

---

## 6. Backup

UBA backup automatique toutes les 6h via worker_automation. Backup manuel :

```powershell
.\deploy\local\backup.ps1
```

**Que fait le backup ?**
- Dump postgres (`pg_dumpall`)
- Snapshot redis (`SAVE`)
- Copie evidence_ledger + audit_events (chaines hash)
- Export rules YAML actives
- Tarball compresse vers `backups/backup_YYYY-MM-DD_HH-MM.tar.gz`

**Conservation recommandee** : 7 ans (cdc fiscal DZ).

---

## 7. Restore

```powershell
.\deploy\local\restore.ps1 backups\backup_2026-04-25_18-00.tar.gz
```

**Attention** : ecrase la BDD locale. Demande confirmation.

---

## 8. Troubleshooting (10 scenarios courants)

### S1 — UBA inaccessible (timeout sur https://uba.localhost)
```powershell
docker compose -f docker-compose.local-prod.yml ps
```
Si certains containers `unhealthy` ou `exited` :
```powershell
docker compose -f docker-compose.local-prod.yml restart <service>
```

### S2 — Login fail "401 Unauthorized"
Token expire (60 min). Re-login. Si persistant : reset password via :
```powershell
docker compose exec backend python scripts/reset_password.py ahmed@dendani.dz
```

### S3 — Projet bloque en "executing" depuis > 30 min
Probable timeout Anthropic ou worker plante. Verifier logs :
```powershell
docker compose logs worker --tail 100
```
Restart worker :
```powershell
docker compose restart worker worker_automation worker_automation_2
```

### S4 — UBA lent (UI traine)
Verifier ressources Docker Desktop (Settings → Resources) : recommande 6 CPU + 8 GB RAM.

### S5 — Disk full
```powershell
docker system prune -a --volumes
.\deploy\local\backup.ps1  # avant prune si tient a vos donnees
```

### S6 — SSL warning persistant
```powershell
certutil -addstore -f Root deploy\local\ssl\cert.pem
```
Voir `docs/SSL_LOCAL_NOTICE.md` pour Firefox + autres OS.

### S7 — WebSocket ne marche pas (UI ne se met pas a jour)
Verifier que nginx-local route `/ws/` :
```powershell
curl -k https://uba.localhost/ws/projects/test --upgrade
```
Pare-feu Windows peut bloquer : autoriser `nginx.exe`/Docker dans Windows Defender.

### S8 — Worker ne tourne pas
```powershell
docker compose ps worker
docker compose logs worker --tail 50
docker compose restart worker
```

### S9 — Migration SQL en erreur au boot
```powershell
docker compose exec postgres psql -U uba -d uba -c "\dt" | wc -l
```
Si tables manquantes :
```powershell
docker compose exec postgres bash -c "for f in /docker-entrypoint-initdb.d/*.sql; do psql -U uba -d uba -f \$f; done"
```

### S10 — CDC rejete au submit
Erreurs courantes :
- CDC < 100 chars : trop court, etoffer
- CDC > 50000 chars : trop long, condenser
- project_name slug invalide : minuscules/chiffres/tirets uniquement

---

## 9. Limites connues (V7)

| Aspect | Statut V7 | Plan futur |
|--------|-----------|------------|
| Mono-utilisateur | OUI (Ahmed only) | Multi-tenant V8 |
| Single-node | OUI | Cluster Hetzner V9 |
| SSL self-signed | OUI | Let's Encrypt sur deploy public |
| Backup local-only | OUI | S3/GCS V8 |
| Anthropic dependency | partielle (template fallback OK) | Multi-LLM provider V8 |

---

## 10. Glossaire express

- **CDC** : Cahier Des Charges, votre specification en francais naturel
- **Pipeline** : sequence Intake -> Decompose -> Execute -> Validate -> Deliver
- **Livrable** : ZIP final contenant code + Docker + tests + README
- **Agent** : composant specialise (Claude Code, Pytest, SonarQube, Linter, etc.)
- **DAG** : graphe de taches qu'UBA execute en parallele
- **Truth Engine** : moteur de verite (chaines hash + evidence ledger)
- **Active Learning** : UBA s'auto-ameliore a chaque livraison (V5.8)
- **ARQ** : queue Redis qui execute les workers async

---

## Support

- Logs en temps reel : `docker compose logs -f backend`
- Health snapshot : `https://uba.localhost/api/v1/health/detailed`
- OpenAPI docs : `https://uba.localhost/docs`
- Code source UBA : `C:\Users\BARACHE\Desktop\C\uba`

Bonne usine, Ahmed.
