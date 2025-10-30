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

## 🔑 3. Créer des identifiants OAuth 2.0

1. Dans le menu latéral, allez dans :  
   **API et services → Identifiants**
2. Cliquez sur **Créer des identifiants → Identifiant OAuth 2.0**
3. Sélectionnez :
- **Type d’application : Application de bureau**
- **Nom** : `ExchangeSyncLocal`
4. Cliquez sur **Créer**

---

## 💾 4. Télécharger le fichier `credentials.json`

Une fois la clé créée :
1. Cliquez sur le bouton **Télécharger le fichier JSON** à droite de la clé créée.
2. Renommez-le si besoin en : credentials.json
3. Placez-le dans le dossier racine du projet : ex: /home/<user>/Project/python/py-exchange/credentials.json

> ⚠️ **Ne pas le mettre sur GitHub !**
>
> Ce fichier contient votre `client_id` et `client_secret`.  
> Ajoutez-le toujours dans votre `.gitignore`.

---

## 🧠 5. Premier lancement du script

Lors du premier lancement :
```bash
python3 exchange_sync.py
```

Une fenêtre de navigateur va s’ouvrir pour vous demander de :
- Vous connecter à votre compte Google
- Autoriser l’accès à Google Calendar

Le script créera automatiquement un fichier : token.json.
Ce fichier stocke le jeton d’accès OAuth, pour éviter de devoir se reconnecter à chaque fois.