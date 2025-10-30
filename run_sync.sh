#!/usr/bin/env bash
# ================================================
# 🚀 Script de lancement de la synchro Exchange → Google Calendar
# ================================================
# À exécuter depuis le dossier racine du projet
# Exemple :
#   cd /home/nfrey/Project/python/py-exchange && ./run_sync.sh
# ================================================

# Variables locales
VENV_DIR="./venv"
LOG_FILE="./sync.log"
PYTHON_SCRIPT="./exchange_sync.py"
NOW=$(date '+%Y-%m-%d %H:%M:%S')

# Vérifie que le venv existe
if [ ! -d "$VENV_DIR" ]; then
  echo "[$NOW] ❌ Environnement virtuel introuvable : $VENV_DIR" >> "$LOG_FILE"
  exit 1
fi

# Active le venv
source "$VENV_DIR/bin/activate"

# Exécute la synchro
echo "[$NOW] 🔁 Démarrage de la synchronisation Exchange → Google Calendar..." >> "$LOG_FILE"
python3 "$PYTHON_SCRIPT" >> "$LOG_FILE" 2>&1
STATUS=$?

# Log du résultat
if [ $STATUS -eq 0 ]; then
  echo "[$NOW] ✅ Synchronisation terminée avec succès." >> "$LOG_FILE"
else
  echo "[$NOW] ⚠️ Erreur pendant la synchronisation (code $STATUS)." >> "$LOG_FILE"
fi

# Désactive le venv
deactivate 2>/dev/null || true
