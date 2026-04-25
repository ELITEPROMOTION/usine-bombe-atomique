# UBA Local-Prod — SSL self-signed (notice utilisateur)

## Pourquoi un certificat self-signed ?

UBA est deploye en **mode local-production** sur votre machine, accessible via
`https://uba.localhost`. Aucune autorite de certification publique (Let's Encrypt,
DigiCert, etc.) ne peut emettre un certificat pour `uba.localhost` parce que ce
nom n'est pas un domaine resolvable depuis Internet.

UBA genere donc son propre certificat (operation faite une seule fois, valide
365 jours). C'est **normal et sans risque** dans un contexte local.

## Comment trust le certificat (recommande, supprime le warning navigateur)

### Automatique (Windows)
Le script `deploy/local/start-local-prod.ps1` execute :

```powershell
certutil -addstore -f Root deploy\local\ssl\cert.pem
```

Cette commande importe le certificat dans le **Trusted Root Certification
Authorities** de Windows. Tous les navigateurs qui utilisent ce store
(Chrome, Edge, IE) feront ensuite confiance a `uba.localhost`.

### Manuel (Firefox)
Firefox utilise son propre store, pas celui de Windows :
1. `https://uba.localhost` → page de warning
2. Cliquer **Avance** → **Accepter le risque et continuer**
3. (Optionnel) Aller dans Parametres → Certificats → Voir les certificats →
   Onglet **Serveurs** → **Ajouter une exception** → URL `https://uba.localhost`

### Manuel (autres OS)
- macOS : `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain deploy/local/ssl/cert.pem`
- Linux Debian/Ubuntu : `sudo cp deploy/local/ssl/cert.pem /usr/local/share/ca-certificates/uba-local.crt && sudo update-ca-certificates`

## Si vous laissez le warning navigateur

C'est une option valide. Le warning ne cache pas une vulnerabilite, juste le
fait que le certificat n'est pas signe par une autorite publique. Cliquez
**Avance** puis **Continuer vers uba.localhost (non securise)**.

Le trafic est **toujours chiffre** (TLS 1.3). Le warning indique uniquement que
le navigateur ne peut pas verifier l'identite du serveur via une chaine PKI
standard — mais ici, le serveur **c'est votre propre machine**, donc l'identite
est triviale.

## Limitations vs vrai certificat de production

| Aspect | Self-signed local | Cert prod (Let's Encrypt) |
|--------|-------------------|---------------------------|
| Chiffrement TLS | Oui (TLS 1.3) | Oui (TLS 1.3) |
| Browser trust auto | Non (warning) | Oui |
| Validite | 365 jours | 90 jours auto-renouvele |
| Domaine | `uba.localhost` only | Domaine public |
| Cout | Gratuit | Gratuit |

Pour un deploiement public futur (Hetzner, AWS, GCP), UBA basculera sur
Let's Encrypt via certbot ou Traefik (deja prepare dans `deploy/config/`).

## Renouveler le certificat self-signed

```bash
cd deploy/local/ssl
openssl req -x509 -nodes -newkey rsa:4096 -keyout key.pem -out cert.pem \
  -days 365 -config openssl.cnf
```

Puis re-trust :
```powershell
certutil -addstore -f Root deploy\local\ssl\cert.pem
```

Et relancer la stack :
```powershell
.\deploy\local\start-local-prod.ps1
```

## Fichiers concernes

- `deploy/local/ssl/cert.pem` : certificat public
- `deploy/local/ssl/key.pem` : cle privee (NE JAMAIS COMMITER — `.gitignore` couvre `*.pem` et `*.key`)
- `deploy/local/ssl/openssl.cnf` : config de generation (CN, SAN)
- `deploy/local/nginx-local.conf` : configuration nginx qui consomme le cert
