# 🔄 Exchange to Google Calendar Sync

Ce projet permet de **synchroniser automatiquement les événements du calendrier Exchange (Outlook Pro)** vers Google Calendar depuis un PC Linux à l'aide de la bibliothèque **`exchangelib`**. Il fonctionne sans Outlook installé, tant que ton compte Exchange est accessible (via EWS, comme Thunderbird avec le plugin Chouette).

---

## ✨ Fonctionnalités

- 📥 **Synchronisation unidirectionnelle** : d'Exchange vers Google Calendar
- 🔄 **Mise à jour automatique** des événements modifiés
- 🗑️ **Suppression des événements** qui n'existent plus dans Exchange
- 🕒 **Gestion des fuseaux horaires**
- 📅 **Support des événements sur la journée entière**
- ⛔ **Filtrage des réunions annulées** : elles ne sont pas poussées, et leur
  copie Google est supprimée. Les réunions que vous avez *refusées* sont en
  revanche conservées, pour garder la visibilité sur ce qui se passe sans vous.
- 🔍 **Mode simulation** (`--dry-run`) : calcule le diff réel sans rien écrire
- 🔔 **Notifications de bureau** en cas d'erreur
- 🧱 **Résilience** : réessai des lectures réseau, cache de l'endpoint EWS,
  verrou anti-recouvrement, rotation du journal

---

## 🧩 Installation

1. Créer un environnement virtuel Python
```bash
python3 -m venv venv
source venv/bin/activate
```
> 💡 Si tu n'as pas le module `venv`, installe-le avec :
```bash
sudo apt install python3-venv python3-pip -y
```

2. Installer les dépendances
```bash
pip install -r requirements.txt
```

3. Configuration des accès
    - Copiez le fichier `.env.sample` vers `.env` et remplissez vos identifiants :
   ```bash
   cp .env.sample .env
   nano .env
   ```
    - Exemple de contenu du fichier `.env` :
   ```
   EXCHANGE_USERNAME=votre_nom_utilisateur
   EXCHANGE_EMAIL=votre_email@domaine.com
   EXCHANGE_PASSWORD=votre_mot_de_passe
   GOOGLE_CALENDAR_ID=votre_id_calendrier_google
   TIMEZONE=Europe/Paris
   DAYS_AHEAD=60
   ENABLE_NOTIFICATIONS=true
   HEALTHCHECK_URL=https://hc-ping.com/votre-uuid
   VERIFY_SSL=true
   CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
   ```

    - `CA_BUNDLE` : à renseigner si le réseau passe par un proxy TLS d'entreprise
      qui réémet les certificats. `requests` utilise par défaut le bundle de
      `certifi`, qui ne contient pas les CA installées sur le système ; pointer
      le magasin système permet de garder la vérification TLS **active**.
    - `VERIFY_SSL=false` désactive complètement la vérification. À n'utiliser
      qu'en dernier recours : préférer `CA_BUNDLE`.
4. Pour configurer l'accès à Google Calendar, suivez les instructions détaillées
   dans le fichier `GOOGLE_SETUP.md`. **Le premier lancement doit se faire à la
   main dans un terminal** : il ouvre un navigateur pour l'autorisation OAuth.

---

## ▶️ Exécution

1. Activer l'environnement virtuel :
```bash
source venv/bin/activate
```

2. Lancer le script :
```bash
python3 exchange_sync.py
```

3. Quitter l'environnement virtuel :
```bash
deactivate
```

### Options

| Option | Effet |
|---|---|
| `--days N` | Nombre de jours à synchroniser vers le futur (défaut : `DAYS_AHEAD`, soit 60) |
| `--dry-run` | Calcule et affiche le diff sans rien écrire dans Google Calendar |
| `--no-notify` | Désactive les notifications de bureau |
| `--no-healthcheck` | Désactive les pings healthchecks.io |

Pour vérifier l'effet d'un changement sans risque :
```bash
python3 exchange_sync.py --dry-run --no-healthcheck --no-notify
```

---

## 🧪 Tests unitaires

Pour exécuter les tests unitaires du projet :

1. Activer l'environnement virtuel :
```bash
source venv/bin/activate
```

2. Lancer toute la suite :
```bash
python3 -m unittest discover -p "test_*.py"   # logique de synchronisation
./test_run_sync.sh                            # script de lancement (bash)
```

Pour un seul module :
```bash
python3 -m unittest test_synchronizer -v
```

⚠️ `test_exchange_service.py` verrouille un détail de sémantique d'exchangelib :
pour les journées entières, `start` et `end` sont **inclusifs** et `end` est
décalé de -1 jour à la lecture, alors que Google Calendar attend un `end`
**exclusif**. Ne pas changer de version majeure d'exchangelib sans relancer ces
tests.

---

## 🤖 Automatisation

### Script d'exécution automatique

Le projet inclut un script `run_sync.sh` qui simplifie l'exécution et génère des logs :

```bash
chmod +x run_sync.sh  # Rendre le script exécutable (une seule fois)
./run_sync.sh         # Lancer la synchronisation
```

### Configuration du CRON

Pour automatiser la synchronisation, ajoutez cette ligne à votre crontab (`crontab -e`) :

```
2 8-20 * * 1-5 cd /chemin/vers/votre/projet && ./run_sync.sh
```

Cette configuration lance la synchronisation à la 2ème minute de chaque heure entre 8h et 20h, du lundi au vendredi.

---

## 📝 Fichiers du projet

- `exchange_sync.py` - Script principal de synchronisation
- `src/synchronizer.py` - Logique de rapprochement Exchange ↔ Google
- `src/exchange_service.py` - Lecture Exchange, clé de synchro, cache d'endpoint
- `src/google_service.py` - Authentification Google Calendar
- `src/utils/datetime_utils.py` - Conversions de dates Exchange ↔ Google
- `src/utils/retry_utils.py` - Réessai des erreurs réseau transitoires
- `src/utils/logging_utils.py` - Journal horodaté (une date et un niveau par ligne)
- `src/utils/healthchecks_utils.py` - Pings de supervision healthchecks.io
- `src/utils/notification_utils.py` - Notifications de bureau (`notify-send`)
- `test_*.py` / `test_run_sync.sh` - Tests unitaires
- `run_sync.sh` - Script d'automatisation (verrou + rotation du journal)
- `.exchange_endpoint.json` - Endpoint EWS mémorisé (généré, ignoré par git)
- `sync.log`, `sync.log.1`..`.5` - Journal et ses archives (5 Mo par génération)
- `requirements.txt` - Dépendances Python
- `.env` - Configuration (identifiants, etc.)
- `GOOGLE_SETUP.md` - Guide de configuration de l'API Google Calendar
- `.env.sample` - Modèle pour le fichier de configuration
- `credentials.json` - Identifiants OAuth Google (personnel, ignoré par git)
- `token.json` - Jeton OAuth généré au premier lancement (ignoré par git)

---

## 📖 Lecture du journal

Chaque ligne de `sync.log` porte sa date et son niveau :

```
2026-09-07 12:30:57 INFO    ➖ Supprimé : Annulé: Réunion (2026-09-14)
2026-09-07 12:30:58 INFO    ✅ Synchronisation terminée : 0 créés, 0 mis à jour, 1 supprimés.
```

Les bibliothèques tierces (googleapiclient, urllib3, exchangelib) sont limitées
au niveau `WARNING` : leurs messages d'information noieraient le journal.

Le fichier tourne à 5 Mo sur 5 générations (`sync.log.1` … `sync.log.5`). Ces
deux seuils sont lus par `run_sync.sh` dans l'environnement du shell — pas dans
`.env`, que le script n'interprète pas. Pour les changer, adaptez la ligne de
crontab :

```
2 8-20 * * 1-5 cd /chemin/vers/projet && MAX_LOG_BYTES=20971520 LOG_GENERATIONS=3 ./run_sync.sh
```

---

## 🛠️ Dépannage

- Vérifiez les logs dans `sync.log` pour identifier les erreurs
- Exécutez avec l'option `--dry-run` pour simuler sans modifier le calendrier
- Pour plus de détails, utilisez `python3 exchange_sync.py --help`

### Cas fréquents

**`Erreur d'authentification Google Calendar`**
Le jeton a expiré ou été révoqué. Supprimez `token.json` puis relancez le script
**à la main dans un terminal** : la ré-autorisation ouvre un navigateur, ce qui
ne peut pas fonctionner depuis le cron.

> ⚠️ Si l'écran de consentement OAuth du projet Google Cloud est resté en statut
> **« Test »**, le jeton de rafraîchissement expire au bout de 7 jours. Passez le
> projet en « Production » (ou « Interne ») pour éviter d'avoir à réautoriser
> chaque semaine.

**`Synchronisation déjà en cours, run ignoré`**
Un run précédent tient encore le verrou `.run_sync.lock`. C'est normal si une
synchronisation est réellement en cours. Si le message persiste d'heure en heure,
un run est bloqué : identifiez-le avec `fuser .run_sync.lock` et terminez-le.

**`All steps in the autodiscover protocol failed`**
Réseau indisponible, typiquement au réveil de la machine. Le script réessaie
trois fois avec un délai croissant ; si cela échoue quand même, le run suivant
repartira normalement. L'endpoint EWS résolu est mémorisé dans
`.exchange_endpoint.json` — supprimez ce fichier pour forcer un nouvel
autodiscover (par exemple après une migration de serveur).

**`SSLCertVerificationError` sur les pings healthchecks.io**
Le réseau passe par un proxy TLS qui réémet les certificats. Renseignez
`CA_BUNDLE` (voir Installation) plutôt que de désactiver la vérification.

**Aucune alerte alors qu'un run a échoué**
Vérifiez que `HEALTHCHECK_URL` est renseignée et que le script n'est pas lancé
avec `--no-healthcheck`.
