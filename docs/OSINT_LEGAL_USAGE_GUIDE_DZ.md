# UBA V8 OSINT — Guide d'usage legal Algerie

**Version** : 1.0 — V5.5.8 — 2026-04-26
**Public cible** : Ahmed Dendani, equipe interne, auditeurs externes consentis
**Statut** : document juridique de reference, valide a la mise en place V8

---

## Table des matieres

- [1. Engagement legal du proprietaire UBA](#1-engagement-legal-du-proprietaire-uba)
- [2. Cadre legal Algerie applicable](#2-cadre-legal-algerie-applicable)
- [3. Cadre legal supranational](#3-cadre-legal-supranational)
- [4. Modules UBA OSINT — classification legale](#4-modules-uba-osint--classification-legale)
- [5. Usages AUTORISES](#5-usages-autorises)
- [6. Usages INTERDITS techniquement bloques](#6-usages-interdits-techniquement-bloques)
- [7. Procedures conformite](#7-procedures-conformite)
- [8. Templates juridiques](#8-templates-juridiques)
- [9. Mecanismes techniques de garantie](#9-mecanismes-techniques-de-garantie)
- [10. Tableaux d'audit et de controle](#10-tableaux-daudit-et-de-controle)
- [11. FAQ juridique](#11-faq-juridique)
- [12. Annexes](#12-annexes)

---

## 1. Engagement legal du proprietaire UBA

Ahmed Dendani s'engage a utiliser UBA OSINT exclusivement dans le cadre legal :

1. **Audits consentis** : sur ses propres systemes ou sur ceux de clients sous
   contrat ecrit signe.
2. **Veille publique** : aggregation de sources ouvertes sans ciblage de
   personnes physiques identifiables.
3. **Auto-surveillance** : monitoring de ses propres livrables (modules
   self-audit).

Il s'engage a respecter :

- La **Loi DZ 18-07 du 25 ramadhan 1439 / 10 juin 2018** relative a la
  protection des personnes physiques dans le traitement des donnees a
  caractere personnel.
- La **Loi DZ 09-04 du 14 cha'ban 1430 / 5 aout 2009** portant regles
  particulieres relatives a la prevention et a la lutte contre les
  infractions liees aux technologies de l'information et de la communication.
- Le **RGPD UE** (2016/679) lorsque les donnees concernent des residents UE.

Aucun module ne vise des personnes ou systemes sans consentement explicite
ou autorisation legale.

---

## 2. Cadre legal Algerie applicable

### 2.1 Loi 18-07 — Donnees personnelles

#### Articles cles

- **Art. 2** : la presente loi s'applique a tout traitement automatise ou
  non, de donnees a caractere personnel.
- **Art. 7** : le consentement de la personne concernee doit etre prealable,
  libre, specifique, informe et univoque.
- **Art. 11** : les traitements doivent faire l'objet d'une autorisation /
  declaration prealable a l'ANPDP (Autorite Nationale de Protection des
  Donnees a caractere Personnel).
- **Art. 27** : la personne concernee a le droit d'acces, de rectification,
  d'effacement et d'opposition.
- **Art. 38-39** : transfert hors-DZ subordonne a un niveau de protection
  adequate.

#### Application UBA OSINT

| Module | Donnees personnelles ? | Mesures |
|--------|------------------------|---------|
| `dendani_ssl_audit` | non (metadata cert) | rien a notifier |
| `dendani_breach_check` | oui (email Dendani) | base legale = interet legitime employeur |
| `dendani_dependency_scanner` | non (libs OSS) | rien a notifier |
| `dendani_dns_audit` | non (DNS public) | rien a notifier |
| `dendani_brand_monitor` | possible (mentions tiers) | retention 90 jours, anonymisation des auteurs |
| `competitor_public_watch` | possible | id |
| `market_intelligence_dz` | non (statistiques agreges) | rien a notifier |
| `regulatory_watch_dz` | non | rien a notifier |
| `consented_pentest_engine` | possible | consent explicite + DPA |
| `vulnerability_assessment_consented` | possible | consent explicite + DPA |
| `threat_intel_aggregator` | non (CVE / IOC) | rien a notifier |
| `dark_web_monitor_lite` | oui (emails breach) | base legale = interet legitime + DPA HIBP/Spycloud |

#### Notification ANPDP

Les modules `dendani_breach_check`, `dendani_brand_monitor`, `competitor_public_watch`,
`consented_pentest_engine`, `vulnerability_assessment_consented`, `dark_web_monitor_lite`
ont vocation a faire l'objet d'une **declaration prealable a l'ANPDP** des
qu'ils traitent des donnees personnelles a caractere systematique.

Modele de declaration : Annexe A.

### 2.2 Loi 09-04 — Cybercrime

#### Articles cles

- **Art. 2** : prevention et lutte contre les infractions portant atteinte
  aux systemes de traitement automatise des donnees (STAD).
- **Art. 3** : acces ou maintien frauduleux dans tout ou partie d'un STAD.
- **Art. 4** : suppression / modification frauduleuse de donnees.
- **Art. 5** : entrave au fonctionnement d'un STAD.

#### Application UBA OSINT

UBA n'effectue **aucune action active** sur des STAD non-autorises :

- Pas de `nmap` sur cible non-consentie (`@requires_consent` bloque).
- Pas d'exploitation de vulnerabilites detectees.
- Pas de bruteforce, pas de DDoS, pas de spoofing.

Les modules `consented_pentest_engine` et `vulnerability_assessment_consented`
n'agissent qu'apres signature d'un contrat dont le SHA-256 est verifie en BDD.

### 2.3 Loi 04-15 — Commerce electronique (impact secondaire)

Pas d'impact direct sur les modules OSINT, mais a respecter pour les livrables
e-commerce que UBA peut generer.

### 2.4 Code penal DZ — articles connexes

- **Art. 303 bis 22 a 303 bis 31** : tentatives d'acces frauduleux au STAD,
  reprises de la Loi 09-04.

---

## 3. Cadre legal supranational

### 3.1 RGPD UE 2016/679

Applicable si :
- Les utilisateurs Dendani / clients consentis sont europeens.
- Les sub-processors (Anthropic, AWS, Hetzner, HIBP, Spycloud) traitent des
  donnees UE.

#### Bases legales utilisables (art. 6)

- Art. 6(1)(a) — consentement (modules pentest tiers).
- Art. 6(1)(b) — execution de contrat (audit propre infrastructure interne).
- Art. 6(1)(f) — interet legitime (security monitoring sa propre
  organisation).

#### Art. 32 — Securite du traitement

UBA repond aux exigences :
- Pseudonymisation et chiffrement (audit_trail SHA-256, JWT).
- Confidentialite, integrite, disponibilite (resilience 6 circuit breakers).
- Capacite a retablir disponibilite + acces (backup automation).

### 3.2 Convention 108+ Conseil Europe

Algerie n'est pas signataire mais le RGPD s'applique extraterritorialement
si UBA traite des donnees de citoyens UE.

### 3.3 ENISA / NIST

Recommandations techniques de reference :
- **NIST SP 800-53** : controles audit (AU-2, AU-3, AU-9 — protege en append).
- **ISO 27001 A.12.4** : journalisation et surveillance.

UBA mappe ces controles via le `osint_audit_trail` chain-hashed.

---

## 4. Modules UBA OSINT — classification legale

### 4.1 Categorie SECURITE DEFENSIVE DENDANI (4 modules)

| Module | Scope | Donnees | Conformite |
|--------|-------|---------|------------|
| `dendani_ssl_audit` | dendani_only | meta cert | OK (rien) |
| `dendani_breach_check` | dendani_only | email own org | OK (interet legitime) |
| `dendani_dependency_scanner` | dendani_only | libs OSS | OK |
| `dendani_dns_audit` | dendani_only | DNS public | OK |

**Aucune declaration ANPDP requise** car traitements internes / metadata.

### 4.2 Categorie VEILLE PUBLIQUE LEGALE (4 modules)

| Module | Sources | Mesures conformite |
|--------|---------|--------------------|
| `dendani_brand_monitor` | RSS Google Alerts, Reddit JSON | retention 90j, anonymisation |
| `competitor_public_watch` | RSS news DZ | retention 90j, agregation seule |
| `market_intelligence_dz` | ONS DZ, Banque Algerie | aucune DCP |
| `regulatory_watch_dz` | JORADP, DGI | aucune DCP |

**Sources publiques uniquement**. Pas de scraping derriere paywall ou auth.

### 4.3 Categorie PENTEST CONSENTI (2 modules)

| Module | Scope | Pre-condition | Documentation |
|--------|-------|---------------|---------------|
| `consented_pentest_engine` | requires_consent | contrat signe + SHA-256 enregistre | rapport remis client |
| `vulnerability_assessment_consented` | requires_consent | id | id |

**Garde-fou technique** : decorator `@requires_consent` verifie un consent_id
valide non-revoke avant toute action. Refus 0-cost si absent.

### 4.4 Categorie THREAT INTELLIGENCE PUBLIQUE (2 modules)

| Module | Sources | Donnees |
|--------|---------|---------|
| `threat_intel_aggregator` | NVD CVE, AlienVault OTX | metadata vulnerabilites |
| `dark_web_monitor_lite` | HIBP enterprise, Spycloud | breach data own org |

**Marketplace illegales** : refus technique pre-cable
(`attempt_marketplace_scrape` raises ScopeViolationError).

---

## 5. Usages AUTORISES

### 5.1 Audit propre infrastructure

Vous pouvez librement :

- Scanner SSL/TLS de `*.dendani.dz` pour detecter degradations.
- Verifier breach HIBP de `@dendani.dz` (sans transmettre les emails complets
  — k-anonymity sur passwords, hash full sur emails uniquement chez HIBP).
- Auditer dependances Python/Node/Docker des projets internes.
- Detecter typosquatting de domaines proches `dendani.dz`.

### 5.2 Veille publique

Vous pouvez :

- Aggreger flux RSS de news (lecture publique).
- Mentionner en interne / dashboard les analyses des concurrents publics.
- Suivre indicateurs ONS / Banque d'Algerie / JORADP.

**Restrictions** :
- Pas de scraping derriere authentification.
- Pas de constitution de profil sur personnes physiques.
- Pas de re-publication des contenus sources sans citation et droit d'auteur.

### 5.3 Audit / pentest pour client tiers

Vous pouvez :

- Lancer `consented_pentest_engine` SI consent enregistre, valide, non-revoke.
- Generer un rapport executif + technique a remettre au client.
- Conserver les logs 7 ans (DZ) pour preuve d'audit (immunable trail).

**Pre-conditions impossibles a contourner techniquement** :
- Contrat signe + scan SHA-256 dans `osint_consents`.
- Periode de validite (`expires_at` checke a chaque appel).
- Action explicitement listee dans `actions` du consent.
- Absence de revocation (`revoked_at IS NULL`).

### 5.4 Self-audit dans livrables UBA

Toute application livree par UBA contient 7 modules de self-audit qui
operent sur :

- Le domaine que possede l'utilisateur (configurable via env).
- Les emails de son propre domaine.
- Les flux CVE publics.

L'utilisateur final consent a ces modules en declarant via env qu'il est
proprietaire / mandate sur le domaine vise.

---

## 6. Usages INTERDITS techniquement bloques

### 6.1 Tentatives bloquees au niveau code

Liste exhaustive des refus pre-cables :

| Action | Module | Garde |
|--------|--------|-------|
| Scan SSL non-Dendani | `dendani_ssl_audit` | `@dendani_only` |
| Breach check email externe | `dendani_breach_check` | `_is_dendani_email` check |
| Scan dependence path externe | `dendani_dependency_scanner` | `_ensure_dendani_path` |
| DNS audit non-Dendani | `dendani_dns_audit` | `@dendani_only` |
| Pentest sans consent | `consented_pentest_engine` | `@requires_consent` |
| Vuln scan sans consent | `vulnerability_assessment_consented` | `@requires_consent` |
| HIBP sur email tiers | `dark_web_monitor_lite` | `@dendani_only` |
| Spycloud sur email tiers | `dark_web_monitor_lite` | `@dendani_only` |
| Scrape marketplace illegale | `dark_web_monitor_lite` | `attempt_marketplace_scrape` raise |
| Mutation audit_trail | tous | trigger SQL `osint_audit_block_mutations` |
| Delete audit_trail | tous | trigger SQL `osint_audit_block_mutations` |

### 6.2 Liste noire d'actions

Ce qui n'est **JAMAIS** implemente dans UBA OSINT :

- Bruteforce login / passwords.
- Phishing / social engineering automatise.
- DDoS / amplification attacks.
- Spoofing IP/email.
- Exfiltration de donnees personnelles via APIs leakees.
- Scraping sources illegales (telegram channels clandestins, marketplaces).
- Acquisition de donnees DGI / CNRC en infraction au mandat.
- Surveillance de personnes individuelles sans mandat judiciaire.

### 6.3 Si un developpeur futur tente de contourner

Garanties au niveau infra :

- Le code source du package `app/osint/` est review-only — toute PR
  modifiant `legal_framework.py` ou `DENDANI_DOMAIN_WHITELIST` doit etre
  contre-signee par Ahmed.
- Les triggers SQL bloquent UPDATE/DELETE sur `osint_audit_trail`.
- Le pre-commit hook `bandit` flag tout subprocess sans `shell=False`.
- Le test `test_audit_trail_records_module_denial` echoue si un module
  contourne le decorator `@log_osint_action`.

---

## 7. Procedures conformite

### 7.1 Onboarding nouveau module OSINT

Avant d'integrer un nouveau module :

1. Le proposer dans une issue GitHub avec : objectif, sources, donnees
   manipulees, base legale.
2. Verifier qu'il est couvert par un decorator existant (`@dendani_only`,
   `@requires_consent`, ou les deux).
3. Ajouter les tests : guard refuse / happy path mock.
4. Mettre a jour ce document section 4.
5. Faire signer la PR par Ahmed.

### 7.2 Onboarding client pentest tiers

1. Negocier le scope (domaines, IPs, actions, fenetre).
2. Completer le `CONSENT_TEMPLATE.md` (cf section 8).
3. Faire signer le PDF par les 2 parties.
4. Calculer SHA-256 du PDF signe.
5. Enregistrer le consent via :
   ```bash
   curl -X POST https://uba.localhost/api/v1/osint/consents \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target":"client.example.com","actions":["port_scan","subdomain_enum"],
          "contractor":"Acme Inc","contract_pdf_sha256":"...64hex...",
          "expires_at_iso":"2026-12-31T23:59:59+00:00"}'
   ```
6. Conserver le PDF signe 7 ans.

### 7.3 En cas de demande d'acces (droits art. 27 Loi 18-07)

Une personne concernee demande l'acces / effacement de ses donnees :

1. Identifier les modules ayant manipule la donnee via :
   ```sql
   SELECT * FROM osint_audit_trail
   WHERE payload_json::text ILIKE '%email_de_la_personne%';
   ```
2. Repondre dans 30 jours (DZ) / 1 mois (RGPD).
3. Effacer les donnees applicatives sans toucher l'audit trail (immutable
   par design).
4. Documenter la reponse + decision dans `osint_audit_trail` via :
   ```python
   trail.append(actor="dpo", module="rights", action="access_request",
                target=email, decision="allowed",
                payload={"request_type": "art27", "response_sent_at": ...})
   ```

### 7.4 En cas d'incident

Si un module OSINT est utilise hors scope :

1. Bloquer le compte utilisateur via :
   ```sql
   UPDATE users SET is_active = false WHERE email = '...';
   ```
2. Auditer les events recents :
   ```sql
   SELECT * FROM osint_audit_trail
   WHERE actor LIKE '%user_id%'
   ORDER BY created_at DESC LIMIT 100;
   ```
3. Verifier l'integrite chain hash :
   ```bash
   curl https://uba.localhost/api/v1/osint/audit/integrity
   ```
4. Notifier l'ANPDP dans les 72h si donnees personnelles concernees
   (loi 18-07 art. 35).

### 7.5 Conservation et destruction

| Donnee | Duree | Base |
|--------|-------|------|
| `osint_audit_trail` | 7 ans | DZ 18-07 + comptable |
| `osint_consents` | 10 ans | preuve contractuelle |
| Resultats brand monitoring | 90 jours | minimisation |
| Resultats CVE / threat intel | 1 an | utilite operationnelle |
| Logs application | 1 an | observabilite |

---

## 8. Templates juridiques

### 8.1 Modele de consentement pentest tiers

Voir `CONSENT_TEMPLATE.md` injecte dans chaque livrable. Reproduit en
annexe B integralement.

### 8.2 Modele de notice de confidentialite (front-end Dendani)

```markdown
# Notice de confidentialite — Dendani Residences

Dendani SARL, situee a Alger, traite vos donnees personnelles aux fins :
- Reservation de residences (donnees obligatoires : nom, NIN, telephone)
- Facturation et conformite fiscale (donnees obligatoires : NIN, adresse)

Base legale : execution du contrat (art. 6.1.b RGPD / art. 7.b loi 18-07).

Vos droits : acces, rectification, effacement, opposition, portabilite.
Pour les exercer : dpo@dendani.dz.

Notre infrastructure est monitoree par UBA OSINT (audit defensif). Aucune
donnee personnelle n'est partagee avec des tiers, hormis :
- Sub-processor d'envoi email (...)
- Sub-processor de paiement (CIB)
- Hebergeur cloud (...)

Conservation : 10 ans (obligation comptable DZ).

Reclamations : ANPDP (Algerie) / CNIL (UE residents).
```

### 8.3 Modele de DPA (Data Processing Agreement)

A signer avec chaque sub-processor (HIBP, Spycloud, Anthropic) :

```
DATA PROCESSING AGREEMENT (extract)

Subject : OSINT services
Duration : aligned with contract
Categories of data : email addresses, breach metadata
Categories of subjects : staff of {client}, registered users
Sub-processors : as listed in vendor contract
Security : TLS 1.2+, audit logs, authentication
Sub-data exports : EU only / DZ only as applicable
Notification : breach within 24h
```

### 8.4 Modele d'engagement employeur (RH)

A signer par tout employe Dendani ayant acces a UBA OSINT :

```
Engagement de confidentialite — UBA OSINT

Je soussigne ___, en ma qualite de ___, m'engage a :
- N'utiliser UBA OSINT que pour les missions confiees.
- Ne pas extraire, copier, partager les resultats hors-perimetre.
- Signaler immediatement toute tentative de contournement des garde-fous.
- Conserver mes credentials (JWT) en lieu sur.

Date : ___ Signature : ___
```

---

## 9. Mecanismes techniques de garantie

### 9.1 ScopeEnforcer

Code source : `backend/app/osint/legal_framework.py::ScopeEnforcer`.

Principe :
- Toute action OSINT passe par `enforcer.authorize(target, action)`.
- Whitelist Dendani **hardcoded en Python** (modification = PR
  contre-signee).
- Consents lus depuis `osint_consents` table avec verification
  validite + revocation.
- Decision tracee dans `osint_audit_trail` via `@log_osint_action`.

### 9.2 Audit trail append-only

Code source : `backend/app/osint/legal_framework.py::AuditTrail`.

Principe :
- Chaque event hashed : `chain_hash = SHA-256(prev_hash || payload_hash)`.
- Triggers PostgreSQL bloquent UPDATE et DELETE.
- Verification periodique via `verify_chain()` (dashboard /osint).
- Export RGPD via `GET /api/v1/osint/audit/export`.

### 9.3 Decorators de protection

| Decorator | Effet |
|-----------|-------|
| `@dendani_only(target_param)` | Refuse si target hors whitelist Dendani |
| `@requires_consent(target_param, action)` | Refuse si pas de consent |
| `@log_osint_action(risk_level, module)` | Log toute action (allowed/denied/error) |
| `@rate_limit_strict(max_per_hour)` | Limite stricte hors limite -> ScopeViolationError |

### 9.4 Tests verifiants

Suite de tests `backend/tests/osint/` :
- 42 tests `test_legal_framework.py` (Consent, Scope, Audit, Decorators).
- 39 tests `test_modules.py` (12 modules : guards + happy path mocks).

Total : **81 tests OSINT PASS**, executes a chaque CI build.

---

## 10. Tableaux d'audit et de controle

### 10.1 Matrice de controle interne

| Controle | Frequence | Responsable | Evidence |
|----------|-----------|-------------|----------|
| Verification chain integrity | quotidien | system | `/api/v1/osint/audit/integrity` |
| Revue consents actifs | mensuel | Ahmed | `/api/v1/osint/consents` |
| Audit logs export | trimestriel | DPO | `/api/v1/osint/audit/export` |
| Test penetration garde-fous | semestriel | securite | tests automatises |
| Revue politique RGPD | annuel | DPO | ce document |
| Notification ANPDP | si declenchement | DPO | record ANPDP |

### 10.2 Indicateurs cles (KPI compliance)

| KPI | Cible | Mesure |
|-----|-------|--------|
| Refus auto / total OSINT | < 5% en regime stable | dashboard /osint |
| Chain integrity | 100% | check integrity |
| Consents expires non-revokes | 0 | monthly cleanup script |
| Modules sans audit | 0 | code review |
| Donnees hors-EU/DZ | 0 sans DPA | revue sub-processors |

### 10.3 Registre des traitements (RGPD art. 30)

A maintenir, format suggere :

| Traitement | Finalite | Base legale | Categories DCP | Destinataires | Duree | Securite |
|-----------|----------|-------------|----------------|---------------|-------|----------|
| ssl_audit | Securite infra | interet legitime | aucune | Dendani interne | 1 an | TLS, JWT |
| breach_check | Securite emails | interet legitime | email Dendani | HIBP (US) | 1 an | TLS, hash |
| brand_monitor | Veille marque | interet legitime | mentions publiques | Dendani interne | 90j | TLS |
| pentest | Securite client | consentement | scope client | client + Dendani | 7 ans | TLS, audit |

---

## 11. FAQ juridique

### Q1 : Puis-je scanner le site d'un concurrent pour comparer prix ?

**Non**, sauf si :
- Le scan est passif (lecture HTML public, pas d'auth) ET
- Vous respectez `robots.txt` ET
- Vous ne contournez pas de protection technique (Cloudflare bot challenge).

UBA n'inclut pas d'outil pour cela : le respect du droit d'auteur + protection
des bases de donnees (loi 03-05 DZ) le rend risque. Preferez les sources
publiques structurees (RSS, APIs publiques).

### Q2 : Puis-je verifier si l'email d'un prospect est dans une breach ?

**Non**, ce serait un traitement DCP sans base legale. Le module
`dendani_breach_check` refuse explicitement les emails non-Dendani.

### Q3 : Puis-je faire de l'OSINT sur un fournisseur defaillant ?

**Cas par cas**. La veille publique (RSS news) est OK. Toute investigation
ciblant des personnes physiques necessite une base legale (art. 6 RGPD /
loi 18-07).

### Q4 : Que faire si un client refuse le pentest annuel mais pousse des bugs ?

Pas de pentest sans consent ; documentez le refus, transferez le risque par
ecrit, refusez si possible la prestation a risque eleve.

### Q5 : Le module `dark_web_monitor_lite` est-il legal ?

Oui s'il consomme **uniquement** des APIs commerciales (HIBP enterprise,
Spycloud) avec DPA en regle. Le scraping direct de marketplaces clandestines
est explicitement bloque (`attempt_marketplace_scrape` raise).

### Q6 : Combien de temps conserver l'audit trail ?

7 ans (loi DZ 18-07 et obligations comptables) avec verification d'integrite
au moins trimestrielle.

### Q7 : Puis-je transferer l'audit trail hors-DZ ?

Oui pour backup chiffre vers hebergeur certifie (Hetzner FR/DE = adequate
RGPD ; AWS / GCP necessitent SCCs ou DPA EU).

### Q8 : Que se passe-t-il en cas de subpoena d'autorite ?

Cooperer en remettant l'export d'audit trail filtree (date / cible). Notifier
le DPO ; conserver la copie de la subpoena 10 ans.

### Q9 : UBA peut-il etre utilise par un employe en interne pour ses
recherches personnelles ?

Non. L'engagement employeur (section 8.4) interdit toute utilisation
hors-mission. Audit trail montre l'identifiant utilisateur a chaque action.

### Q10 : Que faire si je decouvre une vuln d'un tiers via OSINT passif ?

Responsible disclosure : alerter le tiers en prive (security@), donner 90
jours de remediation, ne publier qu'apres correction. UBA inclut un
modele de mail dans `docs/RESPONSIBLE_DISCLOSURE.md` (a creer).

---

## 12. Annexes

### Annexe A — Modele declaration ANPDP

```
A l'attention de l'ANPDP
Centre commercial El Mohamadia - Alger

Objet : declaration prealable de traitement automatise (loi 18-07 art. 11)

Responsable du traitement :
Dendani SARL — RC ___ — NIF ___ — Adresse ___

Designation du traitement : "UBA OSINT — security monitoring"

Finalite : monitoring securite de l'infrastructure de l'entreprise et
detection de breach affectant les emails @dendani.dz.

Categories de DCP : adresses email professionnelles des employes Dendani.

Destinataires : equipe interne security.

Sub-processors : HaveIBeenPwned (US), Spycloud (US) — DPA en regle.

Mesures de securite : TLS 1.3, audit trail append-only, JWT 60min, rate
limiting.

Duree : illimitee tant que l'employe est present ; effacement a la sortie.

Base legale : interet legitime (art. 7).

Le ___, signature : ___
```

### Annexe B — `CONSENT_TEMPLATE.md` reproduit

(Contenu identique au fichier injecte dans chaque livrable. Voir
`backend/templates/deliverable/osint_self_audit/CONSENT_TEMPLATE.md.j2`.)

### Annexe C — Liste des sub-processors

| Sub-processor | Pays | Service | DPA signe |
|---------------|------|---------|-----------|
| Anthropic | US | LLM API | en attente |
| HaveIBeenPwned | US | breach API | n/a (free) puis enterprise |
| Spycloud | US | dark web | en attente si activation |
| AlienVault OTX | US | threat intel | n/a (free) |
| Hetzner | DE | hebergement futur | template prepare V6 |

### Annexe D — Glossaire

- **DCP** : Donnees a Caractere Personnel.
- **STAD** : Systeme de Traitement Automatise de Donnees.
- **ANPDP** : Autorite Nationale de Protection des DCP (Algerie).
- **CNIL** : Commission Nationale Informatique Liberte (France).
- **DPO** : Data Protection Officer.
- **DPA** : Data Processing Agreement.
- **OSINT** : Open Source Intelligence.
- **CVE** : Common Vulnerabilities and Exposures.
- **IOC** : Indicators of Compromise.
- **SCCs** : Standard Contractual Clauses (EU transfers).

### Annexe E — Liens utiles

- Loi 18-07 : https://www.joradp.dz/
- Loi 09-04 : https://www.joradp.dz/
- ANPDP : (creation en cours, voir publications officielles)
- HaveIBeenPwned : https://haveibeenpwned.com/API/v3
- NIST CVE Feed : https://services.nvd.nist.gov/
- AlienVault OTX : https://otx.alienvault.com/
- Spycloud : https://spycloud.com/

### Annexe F — Roadmap conformite

| Q | Action |
|---|--------|
| Q2 2026 | Declaration ANPDP des modules avec DCP |
| Q2 2026 | Signature DPA Anthropic |
| Q3 2026 | Audit conformite externe (cabinet juridique DZ) |
| Q3 2026 | Formation interne employes RGPD + 18-07 |
| Q4 2026 | Mise a jour documentation suivant retours ANPDP |

### Annexe G — Changelog

- **2026-04-26 — V1.0** : creation initiale lors deploiement V8.

---

**FIN DU DOCUMENT**

_Ce document est confidential. Usage interne Dendani SARL + auditeurs sous
NDA._

_Signature electronique de validite (a apposer apres revue cabinet juridique) :_

```
sha256(version 1.0): ____________________________________________________
date: 2026-04-26
auteur: UBA V8 OSINT
```
