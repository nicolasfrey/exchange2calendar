# 🔄 Exchange to Google Calendar Sync

Ce projet permet de **synchroniser automatiquement les événements du calendrier Exchange (Outlook Pro)** vers Google Calendar depuis un PC Linux à l'aide de la bibliothèque **`exchangelib`**. Il fonctionne sans Outlook installé, tant que ton compte Exchange est accessible (via EWS, comme Thunderbird avec le plugin Chouette).

---

## ✨ Fonctionnalités

- 📥 **Synchronisation unidirectionnelle** : d'Exchange vers Google Calendar
- 🔄 **Mise à jour automatique** des événements modifiés
- 🗑️ **Suppression des événements** qui n'existent plus dans Exchange
- 🕒 **Gestion des fuseaux horaires**
- 📅 **Support des événements sur la journée entière**
- 🔍 **Mode simulation** pour tester sans modifier le calendrier Google
- 🔔 **Notifications de bureau** en cas d'erreur

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

2. Installer des dépendances
```bash
pip install -r requirements.txt

4. Configuration des accès
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
   ```
    - Pour configurer l'accès à Google Calendar, suivez les instructions détaillées dans le fichier `GOOGLE_SETUP.md`

---

## ▶️ Exécution

1. Activer l'environnement virtuel :
```bash
source venv/bin/activate
```

2. Lancer le script :
```bash
python3 exchange_sync.py
```bash
deactivate
```

---

## 🧪 Tests unitaires

Pour exécuter les tests unitaires du projet :

1. Activer l'environnement virtuel :
```bash
source venv/bin/activate
```

2. Lancer les tests :
```bash
python3 -m unittest test_exchange_sync.py
```

Pour plus de détails et un affichage amélioré, vous pouvez utiliser pytest :
```bash
pip install pytest
pytest test_exchange_sync.py -v
```

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
- `test_exchange_sync.py` - Tests unitaires
- `run_sync.sh` - Script d'automatisation
- `requirements.txt` - Dépendances Python
- `.env` - Configuration (identifiants, etc.)
- `GOOGLE_SETUP.md` - Guide de configuration de l'API Google Calendar
- `.env.sample` - Modèle pour le fichier de configuration
- `notify.py` - Module de notifications de bureau (optionnel)

---

## 🛠️ Dépannage

- Vérifiez les logs dans `sync.log` pour identifier les erreurs
- Exécutez avec l'option `--dry-run` pour simuler sans modifier le calendrier
- Pour plus de détails, utilisez `python3 exchange_sync.py --help`