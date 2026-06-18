#!/usr/bin/env bash
# =============================================================================
# reload_withfixs.sh — Recarga CertManager CONSERVANDO la BD SQLite existente.
#
#   Para cuando reemplazas el código (nuevo checkout con los fixes) pero quieres
#   mantener tu base de datos actual. NO re-siembra Owner/grupos/certificados:
#   tus datos quedan intactos.
#
#   Pasos:
#     1) detiene el servicio (libera la BD)
#     2) respalda data/certforge.sqlite3 (+ -wal/-shm) por seguridad
#     3) venv + dependencias (idempotente)
#     4) conserva el .env.preprod existente; si falta, lo genera (SQLite/HTTP :PORT)
#     5) migrate (idempotente, NO borra datos) + collectstatic
#     6) reinicia el servicio
#
#   Requisitos: rootless (sin sudo). Coloca tu data/certforge.sqlite3 ANTES de correr.
#
# Uso:
#   ./reload_withfixs.sh
#   PORT=8080 ./reload_withfixs.sh
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR="$(pwd)"
VENV="${VENV:-$APP_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8000}"
DATA_DIR="${CERTFORGE_DATA_DIR:-$APP_DIR/data}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"
RUN_DIR="${RUN_DIR:-$APP_DIR/run}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.preprod}"
DB="$DATA_DIR/certforge.sqlite3"
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "== CertManager — reload_withfixs.sh (conserva la BD SQLite) =="

# --- 1) Detener el servicio (libera la BD antes de migrar) ------------------
if [ -x "$APP_DIR/levantamiento.sh" ]; then
  echo ">> [1/6] Deteniendo el servicio…"
  "$APP_DIR/levantamiento.sh" stop || true
else
  echo ">> [1/6] (levantamiento.sh no encontrado; omito el stop)"
fi

# --- 2) Respaldo de la BD ---------------------------------------------------
mkdir -p "$DATA_DIR" "$LOG_DIR" "$RUN_DIR"
if [ -f "$DB" ]; then
  BK="$DATA_DIR/backups"; mkdir -p "$BK"
  echo ">> [2/6] Respaldando BD en $BK/certforge.sqlite3.$STAMP"
  for ext in "" "-wal" "-shm"; do
    [ -f "$DB$ext" ] && cp -p "$DB$ext" "$BK/certforge.sqlite3$ext.$STAMP"
  done
else
  echo ">> [2/6] AVISO: no existe $DB. Si querías conservar tu BD, cópiala AHÍ y reejecuta."
  echo "          (Si continúas, se creará una BD nueva y vacía al migrar.)"
fi

# --- 3) Virtualenv + dependencias -------------------------------------------
echo ">> [3/6] Virtualenv y dependencias…"
[ -d "$VENV" ] || "$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
"$VENV/bin/pip" install -r "$APP_DIR/requirements/base.txt" "gunicorn>=21.2"

# --- 4) Entorno: conservar el existente; generarlo solo si falta ------------
if [ -f "$ENV_FILE" ]; then
  echo ">> [4/6] Conservo el $ENV_FILE existente."
else
  echo ">> [4/6] No hay $ENV_FILE: generándolo (SQLite, HTTP :$PORT, abierto)…"
  cat > "$ENV_FILE" <<ENV
# Generado por reload_withfixs.sh — preprod/stg (SQLite, HTTP :$PORT).
DJANGO_SETTINGS_MODULE=config.settings.standalone
DEBUG=False
CERTFORGE_DATA_DIR=$DATA_DIR
LOG_DIR=$LOG_DIR
ALLOWED_HOSTS=*
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0
RUN_SCHEDULER=False
OBSFORGE_ENABLED=False
ENV
  chmod 600 "$ENV_FILE"
fi

# --- 5) migrate (idempotente) + collectstatic -------------------------------
echo ">> [5/6] migrate / collectstatic…"
set -a; . "$ENV_FILE"; set +a
"$VENV/bin/python" manage.py migrate --no-input
"$VENV/bin/python" manage.py collectstatic --no-input

# --- 6) Reinicio ------------------------------------------------------------
if [ -x "$APP_DIR/levantamiento.sh" ]; then
  echo ">> [6/6] Reiniciando el servicio…"
  "$APP_DIR/levantamiento.sh" restart
else
  echo ">> [6/6] levantamiento.sh no encontrado; arranca el servicio a mano." >&2
fi

echo ""
echo ">> Listo. BD conservada (respaldo en $DATA_DIR/backups si existía)."
echo ">> Verifica el correo (fix FIPS/SMTP ya aplicado): botón 'Probar envío'."
