# 🔧 Configuration Google Cloud — `credentials.json`

Ce guide explique comment créer un **fichier `credentials.json`** pour permettre à l’application  
de se connecter à l’API Google Calendar via OAuth2.

> ⚠️ Ce fichier est personnel. **Ne le partagez jamais** ni ne le versionnez sur GitHub.

---

## 🧩 1. Créer un projet Google Cloud

1. Rendez-vous sur 👉 [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Connectez-vous avec votre compte Google.
3. En haut à gauche, cliquez sur **Sélectionner un projet** → **Nouveau projet**.
4. Donnez-lui un nom, par exemple :  
   **Exchange Sync Calendar**
5. Cliquez sur **Créer**.

---

## ⚙️ 2. Activer l’API Google Calendar

1. Dans la barre de recherche, tapez : Google Calendar API
2. Cliquez sur le résultat puis sur **Activer**.

---

## 🪪 3. Configurer l'écran de consentement OAuth

Google exige cette étape **avant** de pouvoir créer un identifiant.

1. Dans le menu latéral : **API et services → Écran de consentement OAuth**
2. Type d'utilisateur : **Externe** (ou **Interne** si votre organisation le permet)
3. Renseignez le nom de l'application et votre adresse e-mail de contact.
4. Ajoutez votre propre compte Google dans **Utilisateurs de test**.

> ⚠️ **Statut de publication.** Laissé en **« Test »**, le jeton de
> rafraîchissement expire au bout de **7 jours** : il faudrait réautoriser
> l'application chaque semaine, et la synchronisation s'arrêterait entre-temps.
> Passez le projet en **« Production »** (ou utilisez le type **« Interne »**)
> pour obtenir un jeton durable.

---

## 🔑 4. Créer des identifiants OAuth 2.0

1. Dans le menu latéral, allez dans :  
   **API et services → Identifiants**
2. Cliquez sur **Créer des identifiants → Identifiant OAuth 2.0**
3. Sélectionnez :
- **Type d’application : Application de bureau**
- **Nom** : `ExchangeSyncLocal`
4. Cliquez sur **Créer**

---

## 💾 5. Télécharger le fichier `credentials.json`

Une fois la clé créée :
1. Cliquez sur le bouton **Télécharger le fichier JSON** à droite de la clé créée.
2. Renommez-le si besoin en : credentials.json
3. Placez-le dans le dossier racine du projet : ex: /home/<user>/Project/python/py-exchange/credentials.json

> ⚠️ **Ne pas le mettre sur GitHub !**
>
> Ce fichier contient votre `client_id` et `client_secret`.  
> Ajoutez-le toujours dans votre `.gitignore`.

---

## 🧠 6. Premier lancement du script

⚠️ **À faire à la main, dans un terminal** — pas via le cron : cette étape ouvre
un navigateur, et sous cron le script resterait bloqué à l'attendre.

```bash
source venv/bin/activate
python3 exchange_sync.py
```

Une fenêtre de navigateur va s'ouvrir pour vous demander de :
- Vous connecter à votre compte Google
- Autoriser l'accès à Google Calendar

Le script créera automatiquement un fichier `token.json`, qui stocke le jeton
OAuth et évite de devoir se reconnecter à chaque exécution. Il est rafraîchi
automatiquement par la suite ; s'il devient invalide, supprimez-le et relancez
cette même étape à la main.
