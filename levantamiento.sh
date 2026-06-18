#!/usr/bin/env bash
# =============================================================================
# levantamiento.sh — Levanta CertManager en un servidor Linux SIN privilegios.
#
#   Para un servidor CONTROLADO donde NO eres admin (sin sudo/root):
#   · NO instala paquetes de sistema (usa el python3 que ya exista).
#   · NO usa systemd ni nginx ni puertos privilegiados.
#   · Gunicorn sirve DIRECTO en 0.0.0.0:8000 (HTTP plano, abierto a la red),
#     con WhiteNoise sirviendo los estáticos → no hace falta proxy delante.
#   · El scheduler (monitoreo/reportes/backup) corre como proceso aparte.
#   · Procesos en segundo plano (setsid/nohup): sobreviven al cierre del SSH.
#     PID files + logs en ./run y ./logs. Persistencia tras reboot: crontab.
#
#   Perfil: config.settings.standalone (SQLite con WAL; sin MySQL).
#
# Requisitos: python3 (3.11+) en el PATH y permiso de escritura en este repo.
#             El puerto 8000 debe estar abierto en el firewall del servidor
#             (si no lo está, pídeselo al admin: es lo único que necesitas de él).
#
# Uso:
#   ./levantamiento.sh                 # setup (idempotente) + arranca todo
#   ./levantamiento.sh stop            # detiene web + scheduler
#   ./levantamiento.sh restart         # reinicia (sin re-setup)
#   ./levantamiento.sh status          # estado + health
#   ./levantamiento.sh logs            # sigue los logs
#   PORT=8080 ./levantamiento.sh       # otro puerto (>1024, sin root)
#   CF_OWNER_PASSWORD=xxx ./levantamiento.sh   # sin prompt de contraseña
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# --- Parámetros (sobreescribibles por entorno) ------------------------------
APP_DIR="$(pwd)"
VENV="${VENV:-$APP_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"                    # accesible a toda la red
PORT="${PORT:-8000}"                       # HTTP plano, puerto NO privilegiado
WORKERS="${WORKERS:-3}"
DATA_DIR="${CERTFORGE_DATA_DIR:-$APP_DIR/data}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"
RUN_DIR="${RUN_DIR:-$APP_DIR/run}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.preprod}"   # gitignored (.env.*)
CF_OWNER_EMAIL="${CF_OWNER_EMAIL:-jairol_grullon@claro.com.do}"
PID_WEB="$RUN_DIR/gunicorn.pid"
PID_SCH="$RUN_DIR/scheduler.pid"

# --- Subcomandos de control (stop/status/logs/restart) ----------------------
is_running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

do_stop() {
  local stopped=0
  for pf in "$PID_WEB" "$PID_SCH"; do
    if is_running "$pf"; then
      kill -TERM "$(cat "$pf")" 2>/dev/null || true   # gunicorn master baja sus workers
      stopped=1
    fi
    rm -f "$pf"
  done
  # Respaldo: barre cualquier huérfano de ESTE despliegue (mismo venv y puerto).
  if command -v pkill >/dev/null; then
    pkill -f "$VENV/bin/gunicorn config.wsgi:application --bind $HOST:$PORT" 2>/dev/null && stopped=1 || true
    pkill -f "$VENV/bin/python manage.py run_scheduler" 2>/dev/null && stopped=1 || true
  fi
  [ "$stopped" = "1" ] && echo ">> Detenido." || echo ">> No había procesos corriendo."
}

do_status() {
  is_running "$PID_WEB" && echo "web (gunicorn):   CORRIENDO (pid $(cat "$PID_WEB"))" || echo "web (gunicorn):   detenido"
  is_running "$PID_SCH" && echo "scheduler:        CORRIENDO (pid $(cat "$PID_SCH"))" || echo "scheduler:        detenido"
  echo -n "health http://127.0.0.1:$PORT/health/ -> "
  curl -fsS -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:$PORT/health/" 2>/dev/null || echo "sin respuesta"
}

start_services() {
  [ -f "$ENV_FILE" ] || { echo "ERROR: falta $ENV_FILE. Corre primero el setup: ./levantamiento.sh" >&2; exit 1; }
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  set -a; . "$ENV_FILE"; set +a
  # nohup → ignora SIGHUP (sobrevive al cierre del SSH) y, al hacer exec, el PID
  # capturado es el del proceso real (no un subshell intermedio).
  if is_running "$PID_WEB"; then
    echo ">> web ya está corriendo (pid $(cat "$PID_WEB")). Usa restart para reiniciar."
  else
    echo ">> Arrancando gunicorn en $HOST:$PORT (workers=$WORKERS)…"
    # gunicorn escribe su propio PID master con --pid (fuente autoritativa).
    nohup "$VENV/bin/gunicorn" config.wsgi:application \
      --bind "$HOST:$PORT" --workers "$WORKERS" --pid "$PID_WEB" \
      --access-logfile "$LOG_DIR/access.log" --error-logfile "$LOG_DIR/error.log" \
      >> "$LOG_DIR/gunicorn.out" 2>&1 &
  fi
  if is_running "$PID_SCH"; then
    echo ">> scheduler ya está corriendo (pid $(cat "$PID_SCH"))."
  else
    echo ">> Arrancando el scheduler (run_scheduler)…"
    nohup "$VENV/bin/python" manage.py run_scheduler >> "$LOG_DIR/scheduler.out" 2>&1 &
    echo $! > "$PID_SCH"
  fi
}

case "${1:-up}" in
  stop)    do_stop; exit 0 ;;
  status)  do_status; exit 0 ;;
  logs)    exec tail -n 50 -F "$LOG_DIR"/error.log "$LOG_DIR"/scheduler.out 2>/dev/null ;;
  restart) do_stop; sleep 1; start_services
           echo ">> Reiniciado."; exit 0 ;;
  up|"")   : ;;   # continúa al setup completo abajo
  *) echo "Uso: $0 [up|stop|restart|status|logs]" >&2; exit 1 ;;
esac

echo "== CertManager — levantamiento PREPROD/STG sin root (SQLite, HTTP :$PORT, abierto a todos) =="

# --- 1) Python disponible (no se instala nada de sistema) -------------------
if ! command -v "$PYTHON_BIN" >/dev/null; then
  echo "ERROR: no encuentro '$PYTHON_BIN' en el PATH." >&2
  echo "       Sin admin: pídele a tu administrador python3 (3.11+), o usa un" >&2
  echo "       python de usuario (pyenv/conda) y reexporta PYTHON_BIN." >&2
  exit 1
fi

# --- 2) Virtualenv + dependencias (SQLite: base + gunicorn, sin MySQL) ------
echo ">> [1/5] Virtualenv y dependencias…"
[ -d "$VENV" ] || "$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
"$VENV/bin/pip" install -r "$APP_DIR/requirements/base.txt" "gunicorn>=21.2"

# --- 3) CSS (Tailwind): ya viene compilado; recompila solo si falta y hay npm
if [ ! -f "$APP_DIR/static/css/forge.css" ]; then
  if command -v npm >/dev/null; then
    echo ">> [2/5] Compilando CSS (Tailwind)…"
    npm ci && npm run build:css
  else
    echo "ADVERTENCIA: no existe static/css/forge.css y no hay npm; la UI se verá sin estilos." >&2
  fi
else
  echo ">> [2/5] CSS ya compilado (static/css/forge.css)"
fi

# --- 4) Archivo de entorno (SQLite + HTTP plano + abierto a la red) ---------
echo ">> [3/5] Generando ${ENV_FILE}…"
mkdir -p "$DATA_DIR" "$LOG_DIR" "$RUN_DIR"
cat > "$ENV_FILE" <<ENV
# Generado por levantamiento.sh — preprod/stg sin root (SQLite, HTTP :$PORT).
DJANGO_SETTINGS_MODULE=config.settings.standalone
DEBUG=False
# Datos persistentes: BD SQLite, media y secret_key (autogenerado/persistido).
CERTFORGE_DATA_DIR=$DATA_DIR
LOG_DIR=$LOG_DIR
# Abierto a toda la red (preprod/stg en la intranet).
ALLOWED_HOSTS=*
# HTTP PLANO: sin redirección TLS ni cookies Secure (no rompe el login en :$PORT).
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0
# El scheduler corre como proceso aparte; que NO arranque también dentro de cada
# worker de gunicorn (evita tareas duplicadas).
RUN_SCHEDULER=False
# obsforge es opcional (índice privado); apagado para un instalable mínimo.
OBSFORGE_ENABLED=False
ENV
chmod 600 "$ENV_FILE"

# --- 5) migrate / collectstatic / compilemessages + bootstrap del Owner -----
echo ">> [4/5] migrate / collectstatic / compilemessages…"
set -a; . "$ENV_FILE"; set +a
"$VENV/bin/python" manage.py migrate --no-input
"$VENV/bin/python" manage.py collectstatic --no-input
"$VENV/bin/python" manage.py compilemessages 2>/dev/null || echo "   (compilemessages omitido; el .mo ya viene compilado)"

echo ">> [4/5] Bootstrap del Owner + configuración (idempotente)…"
export CF_OWNER_EMAIL
while [ -z "${CF_OWNER_PASSWORD:-}" ]; do
  read -r -s -p "   Contraseña para el Owner ($CF_OWNER_EMAIL): " CF_OWNER_PASSWORD
  echo
  [ -z "$CF_OWNER_PASSWORD" ] && echo "      La contraseña no puede estar vacía. Intenta de nuevo."
done
export CF_OWNER_PASSWORD
if [ -f "cert.txt" ]; then
  echo "   Encontrado cert.txt: migrando Owner + configuración + certificados…"
  "$VENV/bin/python" manage.py data_update_certs_app --source cert.txt
else
  echo "   Sin cert.txt: cargando solo Owner + configuración (coloca cert.txt y reejecuta para migrar el monitoreo)."
  "$VENV/bin/python" manage.py data_update_certs_app --skip-certs
fi

# --- 6) Arranque de los procesos --------------------------------------------
echo ">> [5/5] Arrancando servicios en segundo plano…"
start_services
sleep 2

IPS="$(hostname -I 2>/dev/null || true)"
echo ""
echo ">> ¡Listo! CertManager accesible a toda la red en HTTP :$PORT."
for ip in $IPS; do echo "     http://$ip:$PORT/"; done
echo "     (Owner: $CF_OWNER_EMAIL)"
echo ""
echo ">> Control:"
echo "     ./levantamiento.sh status      # estado + health"
echo "     ./levantamiento.sh logs        # ver logs en vivo"
echo "     ./levantamiento.sh restart     # reiniciar"
echo "     ./levantamiento.sh stop        # detener"
echo ""
echo ">> Para que arranque solo tras un reboot (sin root), añade a tu crontab"
echo "   (\`crontab -e\`) esta línea:"
echo "     @reboot cd $APP_DIR && ./levantamiento.sh restart >> $LOG_DIR/boot.log 2>&1"
echo ""
echo ">> Si no puedes acceder desde otra máquina, el puerto $PORT podría estar"
echo "   cerrado en el firewall: es lo único que debes pedirle al admin."
