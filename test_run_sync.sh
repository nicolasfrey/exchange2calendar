#!/usr/bin/env bash
# Tests du script de lancement : rotation du log et verrou anti-recouvrement.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0; FAIL=0

setup() {
  WORK="$(mktemp -d)"
  mkdir -p "$WORK/venv/bin"
  printf '#!/usr/bin/env bash\n:\n' > "$WORK/venv/bin/activate"
  # Faux script de synchro : n'appelle aucun service.
  printf '#!/usr/bin/env bash\necho "synchro simulée"\n' > "$WORK/exchange_sync.py"
  chmod +x "$WORK/exchange_sync.py"
  cp "$SCRIPT_DIR/run_sync.sh" "$WORK/"
  # `python3 ./exchange_sync.py` doit exécuter notre stub.
  mkdir -p "$WORK/stubbin"
  printf '#!/usr/bin/env bash\nexec bash "$@"\n' > "$WORK/stubbin/python3"
  chmod +x "$WORK/stubbin/python3"
}

teardown() { rm -rf "$WORK"; }

check() {
  local label="$1" condition="$2"
  if eval "$condition"; then
    echo "  ok   $label"; PASS=$((PASS+1))
  else
    echo "  FAIL $label   [$condition]"; FAIL=$((FAIL+1))
  fi
}

# --- 1. rotation quand le log dépasse la taille maximale ------------------- #
setup
head -c 2000 /dev/zero | tr '\0' 'x' > "$WORK/sync.log"
( cd "$WORK" && PATH="$WORK/stubbin:$PATH" MAX_LOG_BYTES=1000 ./run_sync.sh >/dev/null 2>&1 )
check "le log trop gros est archivé en .1" "[ -f '$WORK/sync.log.1' ]"
check "le log courant est repartir de zéro" "[ \$(stat -c%s '$WORK/sync.log') -lt 1000 ]"
check "l'archive contient l'ancien contenu" "[ \$(stat -c%s '$WORK/sync.log.1') -eq 2000 ]"
teardown

# --- 2. pas de rotation sous le seuil ------------------------------------- #
setup
head -c 100 /dev/zero | tr '\0' 'x' > "$WORK/sync.log"
( cd "$WORK" && PATH="$WORK/stubbin:$PATH" MAX_LOG_BYTES=1000 ./run_sync.sh >/dev/null 2>&1 )
check "un log sous le seuil n'est pas archivé" "[ ! -f '$WORK/sync.log.1' ]"
teardown

# --- 3. le verrou empêche deux runs simultanés ---------------------------- #
setup
# `flock <fichier> <commande>` garde le verrou pendant toute la commande ;
# une simple redirection 9> ne survivrait pas à la commande flock elle-même.
( cd "$WORK" && flock -n ./.run_sync.lock sleep 5 ) &
HOLDER=$!
sleep 0.5
( cd "$WORK" && PATH="$WORK/stubbin:$PATH" ./run_sync.sh >/dev/null 2>&1 )
check "le run concurrent est ignoré" "grep -q 'déjà en cours' '$WORK/sync.log'"
check "le run concurrent n'a pas lancé la synchro" "! grep -q 'synchro simulée' '$WORK/sync.log'"
kill $HOLDER 2>/dev/null; wait $HOLDER 2>/dev/null
teardown

# --- 4. un run normal s'exécute ------------------------------------------- #
setup
( cd "$WORK" && PATH="$WORK/stubbin:$PATH" ./run_sync.sh >/dev/null 2>&1 )
check "un run seul s'exécute bien" "grep -q 'synchro simulée' '$WORK/sync.log'"
teardown

echo ""
echo "Résultat : $PASS ok, $FAIL échec(s)"
[ "$FAIL" -eq 0 ]
