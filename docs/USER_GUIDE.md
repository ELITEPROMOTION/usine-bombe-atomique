# UBA — Guide utilisateur (Ahmed CEO)

> Public cible: **Ahmed**, CEO, utilisateur principal et premier validateur des decisions UBA.
> Tu peux lire ce guide une seule fois en entier, ou y revenir section par section quand tu en as besoin.

---

## 1. Premier login

1. Ouvre `https://uba.dendani.dz` dans ton navigateur (Chrome / Firefox / Safari recents).
2. Saisis ton email **ahmed@dendani.dz** et le mot de passe defini lors du wizard `--phase credentials`.
3. Au premier login, UBA te demande:
   - de **changer ton mot de passe** (si valeur par defaut),
   - d'**activer la 2FA** (TOTP via Google Authenticator / Authy),
   - de **sauvegarder les codes de recovery** (8 codes a usage unique, imprime-les).
4. Tu arrives sur le **Dashboard CEO** par defaut.

> Astuce: bookmark `https://uba.dendani.dz/ceo` — c'est l'ecran le plus utile au quotidien.

---

## 2. Tour des ecrans

### 2.1 Dashboard CEO (`/ceo`)
- **KPIs en haut**: revenus du mois, marge, cash-flow, top 5 clients.
- **Decisions UBA en attente** au centre — chaque ligne = une recommandation que UBA propose.
- **Ahmed Inbox** (bouton orange en haut a droite) — alertes critiques qui demandent ton attention.

### 2.2 Domaines (`/domains`)
UBA opere sur **5 domaines** (fiscal_dz, juridique, comptabilite, rh, logistique). Chaque carte affiche:
- nombre de regles actives,
- derniere mise a jour des regles,
- score de confiance moyen des decisions du mois.

### 2.3 Tasks (`/projects`)
Liste des projets que tu as confies a UBA. Chaque task a un **statut** (queued / running / awaiting_human / done / failed) et un **bouton "Voir progres"**.

### 2.4 Cognition (`/cognition`)
Voir comment UBA "raisonne":
- **Memoire de travail** (faits actifs),
- **Reasoning chain** (trace des etapes),
- **Confiance** par etape.

### 2.5 Truth (`/truth`)
Recherche dans le **Cross-Truth Cache** — UBA verifie ses outputs entre 3 sources independantes avant de te repondre.

### 2.6 Automation (`/automation`)
Workflows planifies (rapports mensuels, backups, scans). Tu peux **declencher manuellement** ou **mettre en pause**.

### 2.7 Observability (`/observability`)
6 onglets (Overview / Traces / Metrics / Logs / Errors / CI-CD). C'est la vue infra. Lis l'onglet **Overview** chaque matin: 30 secondes pour voir si tout est vert.

### 2.8 Fleet (`/fleet`)
Liste de tous les clients qu'UBA gere (multi-tenant). Un seul client (toi) au demarrage.

---

## 3. Lancer un projet (cas typique)

Exemple: "Je veux un rapport fiscal trimestriel."

1. `/new` (bouton **+ Nouveau** en haut a gauche).
2. Choisis le type de projet: **Rapport fiscal**.
3. Remplis le contexte: trimestre, periode, type d'activite, regime fiscal.
4. **Submit** → UBA cree une task et te redirige vers `/tasks/<id>`.
5. Tu vois la **timeline en temps reel**:
   - validation des inputs,
   - collecte des donnees,
   - application des regles fiscales (12 regles actives sur fiscal_dz),
   - generation du rapport,
   - validation par l'agent **conformite_dz**,
   - notification finale dans Ahmed Inbox.

Duree typique: 2 a 8 minutes.

---

## 4. Comprendre une decision UBA

Chaque decision a une **fiche d'explication** (XAI) accessible via le bouton **Pourquoi?** (icone ampoule).

La fiche contient:
- **Resume Ahmed-friendly** (1-2 phrases en francais simple),
- **Top 5 features** qui ont le plus pese (importance triee),
- **Counterfactuals** ("si tu changes X, le resultat devient Y"),
- **Source rules** appliquees (regles YAML versionnees),
- **Confiance** (de 0.0 a 1.0).

Si la confiance est **inferieure a 0.7**, la decision est routee vers Ahmed Inbox pour validation humaine.

---

## 5. Override une decision (human in the loop)

Tu n'es **jamais oblige** d'accepter UBA. Pour chaque decision, 4 actions:
- **Accepter** (vert) → UBA enregistre + execute,
- **Modifier** (bleu) → tu changes des champs avant execution,
- **Rejeter** (rouge) → UBA n'execute pas + apprend,
- **Demander explication** (gris) → ouvre la fiche XAI.

Chaque override **alimente l'active learner** (apprentissage actif): UBA ajustera ses futurs scores.

---

## 6. Ahmed Inbox

`/ahmed_inbox` — c'est ta to-do list UBA. Y arrivent:
- Decisions de **faible confiance**,
- Alertes (cash-flow, deadline fiscale, anomalies),
- Demandes d'override de la part des agents internes,
- Validations de **rapports** avant envoi externe.

Triage rapide:
- **Swipe gauche** = rejeter,
- **Swipe droite** = accepter,
- **Tap** = ouvrir fiche complete.

Vide ton Ahmed Inbox **2 fois par jour** (matin + soir). C'est le rythme cible.

---

## 7. Workflows automatiques (Automation)

UBA a **4 workflows** programmes par defaut:

| Workflow                    | Cadence    | Ce qu'il fait                                      |
|-----------------------------|------------|----------------------------------------------------|
| `daily_kpi_refresh`         | 06:00 UTC  | Recalcule tous les KPIs du dashboard CEO           |
| `monthly_fiscal_report`     | 1er du mois 04:00 | Genere TVA, IRG, IBS                       |
| `hourly_backup_incremental` | toutes 1h  | Snapshot DB + push vers Scaleway                   |
| `daily_anomaly_scan`        | 02:00 UTC  | Cherche transactions atypiques (Isolation Forest)  |

Tu peux **ajouter un workflow personnalise** depuis `/automation` (bouton **+ Nouveau workflow**).

---

## 8. Ahmed Inbox — code couleur des badges

- **Rouge** = critique (a traiter dans l'heure)
- **Orange** = important (dans la journee)
- **Bleu** = informationnel (cette semaine)
- **Gris** = purement audit (a archiver)

---

## 9. Recherche transverse

Barre de recherche **CMD+K** (ou CTRL+K) — disponible partout.
- Recherche par **nom de client**, **NIF**, **numero de facture**, **regle YAML**, **decision**.
- Resultats classes par **score semantique** (TF-IDF + embeddings).

---

## 10. Notifications

3 canaux possibles (configures dans `/settings`):
1. **Web push** (active par defaut),
2. **Email** (a `ahmed@dendani.dz`),
3. **Telegram** (si tu as cree un bot).

Filtres anti-spam: tu peux choisir de recevoir **uniquement les criticites rouges + oranges**.

---

## 11. Mobile

UBA est **PWA** (Progressive Web App). Sur ton telephone:
1. Ouvre `https://uba.dendani.dz` dans Safari (iOS) ou Chrome (Android).
2. Menu → **"Ajouter a l'ecran d'accueil"**.
3. UBA s'ouvre comme une app native, plein ecran, supporte les notifications push.

---

## 12. Donnees personnelles et tes droits

- Tu peux **exporter toutes tes donnees** depuis `/settings → Mes donnees → Export ZIP`.
- Tu peux **supprimer ton compte** (irreversible apres 30 jours de quarantaine).
- UBA scrub automatiquement les emails + telephones DZ + NIF des logs d'erreur.

---

## 13. Raccourcis clavier

| Raccourci      | Action                          |
|----------------|---------------------------------|
| `CMD/CTRL + K` | Ouvrir la recherche transverse  |
| `G` puis `D`   | Aller au Dashboard              |
| `G` puis `I`   | Aller a Ahmed Inbox             |
| `G` puis `T`   | Aller aux Tasks                 |
| `G` puis `O`   | Aller a Observability           |
| `?`            | Voir l'aide raccourcis          |
| `ESC`          | Fermer modal / panel actif      |

---

## 14. FAQ

**Q: UBA a fait une erreur. Que faire?**
R: Ouvre la fiche XAI de la decision (bouton **Pourquoi?**), rejette-la, puis ouvre un ticket sur GitHub avec les screenshots. Le rejet alimente l'active learner.

**Q: Comment delegate a un assistant?**
R: `/settings → Equipe → Inviter` — l'assistant aura un role limite (lecture + traitement Ahmed Inbox).

**Q: Mes donnees sont-elles sauvegardees?**
R: Oui, **toutes les heures**. Backups sur Scaleway, retention 90 jours par defaut.

**Q: Comment exporter un rapport en PDF?**
R: Ouvre la task → bouton **Export → PDF** (ou Excel / CSV).

---

## 15. Contact

- Issue GitHub: https://github.com/dendani/uba/issues
- Email d'urgence: dev@dendani.dz
- Telephone d'urgence: voir `DEPLOYMENT_AHMED_STEP_BY_STEP.md` annexe contacts.

---

*Genere depuis UBA V5.9. Mis a jour avec la Vague 6 — score 9.5/10.*
