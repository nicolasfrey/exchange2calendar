#!/usr/bin/env bash
# ================================================
# 🚀 Script de lancement de la synchro Exchange → Google Calendar
# ================================================
# À exécuter depuis le dossier racine du projet
# Exemple :
#   ./run_sync.sh
# ================================================

# Variables locales
VENV_DIR="./venv"
LOG_FILE="./sync.log"
LOCK_FILE="./.run_sync.lock"
PYTHON_SCRIPT="./exchange_sync.py"
NOW=$(date '+%Y-%m-%d %H:%M:%S')

# Rotation du journal : 5 Mo par génération, 5 générations conservées.
MAX_LOG_BYTES="${MAX_LOG_BYTES:-5242880}"
LOG_GENERATIONS="${LOG_GENERATIONS:-5}"

rotate_log() {
  [ -f "$LOG_FILE" ] || return 0

  local size
  size=$(stat -c%s "$LOG_FILE" 2>/dev/null) || return 0
  [ "$size" -lt "$MAX_LOG_BYTES" ] && return 0

  rm -f "${LOG_FILE}.${LOG_GENERATIONS}"

  local i
  for (( i = LOG_GENERATIONS - 1; i >= 1; i-- )); do
    [ -f "${LOG_FILE}.${i}" ] && mv "${LOG_FILE}.${i}" "${LOG_FILE}.$(( i + 1 ))"
  done

  mv "$LOG_FILE" "${LOG_FILE}.1"
  echo "[$NOW] 🗃️ Journal archivé dans ${LOG_FILE}.1 (${size} octets)." >> "$LOG_FILE"
}

rotate_log

# Verrou : un run qui traîne (timeout Exchange de 120 s) ne doit pas être
# recouvert par le run de l'heure suivante, sinon les deux comparent le même
# état et peuvent créer des doublons.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$NOW] ⏭️ Synchronisation déjà en cours, run ignoré." >> "$LOG_FILE"
  exit 0
fi

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
