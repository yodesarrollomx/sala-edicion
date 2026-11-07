#!/usr/bin/env bash
# Roast Room en Hermes (7-nov-2026). Lo corre el cron de Hermes cada hora como trabajo «sin agente»:
# este guion no gasta tokens; los jueces sí, y van contra las suscripciones vía la API local de Hermes.
#
# Hermes entrega el stdout tal cual. Por eso aquí sólo se imprime cuando el consejo decidió algo o
# cuando falló; una hora sin cartas queda en silencio. La bitácora completa va a ~/.local/state.
set -u
ENV_FILE="${SALA_CONSEJO_ENV:-$HOME/.config/sala-consejo/env}"
REPO="${SALA_CONSEJO_REPO:-$HOME/sala-edicion}"
LOG_DIR="$HOME/.local/state/sala-consejo"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"
CORRIDA="$(mktemp)"
trap 'cat "$CORRIDA" >>"$LOG"; rm -f "$CORRIDA"' EXIT

if [ ! -r "$ENV_FILE" ]; then
  echo "Roast Room: falta $ENV_FILE (corre nube/hermes/instalar_roast_room.sh)"; exit 2
fi
set -a; . "$ENV_FILE"; set +a

MODO="${1:-corrida}"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') · $MODO" >"$CORRIDA"
# Código al día con main, sólo avance rápido: nunca se pisa un cambio local.
git -C "$REPO" pull --ff-only --quiet >>"$CORRIDA" 2>&1 || echo "· aviso: no se pudo actualizar $REPO" >>"$CORRIDA"

python3 "$REPO/nube/sala_consejo.py" "$MODO" >>"$CORRIDA" 2>&1
CODIGO=$?

if [ "$CODIGO" -ne 0 ]; then
  echo "Roast Room falló (código $CODIGO). Últimas líneas:"
  tail -5 "$CORRIDA"
  exit "$CODIGO"
fi
# Silencio si la corrida no decidió nada; si decidió (o fue un ensayo/marcador a mano), el detalle.
if [ "$MODO" != "corrida" ] || grep -qE '^· ' "$CORRIDA"; then
  grep -E '^(·|Roast Room|Marcador)' "$CORRIDA" | grep -v 'por juzgar' || true
fi
exit 0
