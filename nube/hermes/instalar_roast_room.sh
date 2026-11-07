#!/usr/bin/env bash
# Instala el Roast Room en Hermes, en la Chromebook (7-nov-2026). Lo puede correr un agente de Hermes
# desde su terminal; no pide nada si las dos llaves de la Sala ya están en el .env del perfil.
#
#   bash ~/sala-edicion/nube/hermes/instalar_roast_room.sh [perfil] [puerto]
#
# Qué hace, y nada más:
#   1. Deja ~/sala-edicion al día con main (sólo avance rápido).
#   2. Enciende la API local de Hermes en el perfil (por omisión «sol», puerto 8642) con una llave
#      nueva generada aquí, si no estaba encendida. Nunca imprime llaves.
#   3. Reescribe ~/.config/sala-consejo/env (permiso 600) con la liga de la Sala, la API de Hermes y
#      las llaves SALA_CLAVE_AGENTE y SALA_CLAVE_CONSEJO que ya traiga ese archivo, el .env del
#      perfil o, si se corre a mano, las que se peguen.
#   4. Copia roast_room.sh a los scripts del perfil para el cron «sin agente» de cada hora.
# Reiniciar el gateway del perfil y crear el cron se hacen después (el guion dice cómo).
set -euo pipefail
PERFIL="${1:-sol}"
PUERTO="${2:-8642}"
REPO="$HOME/sala-edicion"
if [ "$PERFIL" = "default" ]; then PH="$HOME/.hermes"; else PH="$HOME/.hermes/profiles/$PERFIL"; fi
PENV="$PH/.env"
CONF_DIR="$HOME/.config/sala-consejo"
CONF="$CONF_DIR/env"
SALA_GAS_EXEC='https://script.google.com/macros/s/AKfycbx61UWsEYCL_dHzi0JrUv3GuAUFSDWW4iCmlNmbDDvWBIYY4Hhqkf6sYmt4d8UGIlk7MA/exec'

[ -d "$PH" ] || { echo "No existe el perfil de Hermes: $PH"; exit 1; }
touch "$PENV"; chmod 600 "$PENV"

# 1 · código
if [ -d "$REPO/.git" ]; then git -C "$REPO" pull --ff-only --quiet
else git clone --depth 1 --quiet https://github.com/yodesarrollomx/sala-edicion "$REPO"; fi

# Que no exista el archivo o la línea es normal (primera corrida): con pipefail, grep sin
# coincidencia tumbaba el guion antes de leer el .env del perfil (Chromebook, 7-nov).
valor() { { grep -E "^$1=" "$2" 2>/dev/null || true; } | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }

# 2 · API local de Hermes en el perfil
if [ "$(valor API_SERVER_ENABLED "$PENV")" != "true" ]; then
  {
    echo ""
    echo "# 7-nov-2026 · Roast Room de la Sala: API local para los jueces (sólo 127.0.0.1)"
    echo "API_SERVER_ENABLED=true"
    echo "API_SERVER_HOST=127.0.0.1"
    echo "API_SERVER_PORT=$PUERTO"
    echo "API_SERVER_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
  } >>"$PENV"
  REINICIAR=1
else
  REINICIAR=0
fi
PUERTO_REAL="$(valor API_SERVER_PORT "$PENV")"; PUERTO_REAL="${PUERTO_REAL:-8642}"
LLAVE_API="$(valor API_SERVER_KEY "$PENV")"
[ -n "$LLAVE_API" ] || { echo "El perfil tiene API_SERVER_ENABLED pero no API_SERVER_KEY; agrégala y vuelve a correr."; exit 1; }

# 3 · llaves de la Sala: primero las que Alejandro pegó en ~/.config/sala-consejo/env (desde Files
# del panel de Hermes), luego las del .env del perfil y, si se corre a mano, se piden.
AG="$(valor SALA_CLAVE_AGENTE "$CONF")"; CO="$(valor SALA_CLAVE_CONSEJO "$CONF")"
[ -n "$AG" ] || AG="$(valor SALA_CLAVE_AGENTE "$PENV")"
[ -n "$CO" ] || CO="$(valor SALA_CLAVE_CONSEJO "$PENV")"
if [ -z "$AG" ] && [ -t 0 ]; then read -rsp "Pega la llave del agente (CONFIG, fila clave_agente) y Enter: " AG; echo; fi
if [ -z "$CO" ] && [ -t 0 ]; then read -rsp "Pega la llave del consejo (CONFIG, fila clave_consejo) y Enter: " CO; echo; fi
[ -n "$AG" ] && [ -n "$CO" ] || { echo "Faltan SALA_CLAVE_AGENTE y/o SALA_CLAVE_CONSEJO en $PENV"; exit 1; }
mkdir -p "$CONF_DIR"; chmod 700 "$CONF_DIR"
umask 077
cat >"$CONF" <<EOF
SALA_GAS_EXEC=$SALA_GAS_EXEC
SALA_CLAVE_AGENTE=$AG
SALA_CLAVE_CONSEJO=$CO
HERMES_API_URL=http://127.0.0.1:$PUERTO_REAL
HERMES_API_KEY=$LLAVE_API
EOF
chmod 600 "$CONF"

# 4 · guion del cron
mkdir -p "$PH/scripts"
cp "$REPO/nube/hermes/roast_room.sh" "$PH/scripts/roast_room.sh"
chmod 700 "$PH/scripts/roast_room.sh"

echo "✓ Roast Room instalado en el perfil «$PERFIL» (API en 127.0.0.1:$PUERTO_REAL)."
if [ "$REINICIAR" = 1 ]; then
  echo "→ Reinicia el gateway del perfil para encender la API:  hermes -p $PERFIL gateway restart"
fi
echo "→ Comprueba:  curl -s -H \"Authorization: Bearer \$(grep ^API_SERVER_KEY= $PENV | cut -d= -f2-)\" http://127.0.0.1:$PUERTO_REAL/health"
echo "→ Ensayo sin decidir:  bash $PH/scripts/roast_room.sh ensayo"
echo "→ Cron de cada hora, sin agente:  hermes -p $PERFIL cron create \"every 1h\" \"Roast Room de la Sala\" --no-agent --script roast_room.sh"
