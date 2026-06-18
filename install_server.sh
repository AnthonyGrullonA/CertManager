#!/usr/bin/env bash
# =============================================================================
# install_server.sh — Instala CertManager en un servidor Linux como SERVICIO,
#                      para PREPROD/STAGING (requiere root).
#
#   · Perfil SQLite/standalone (sin servidor de BD externo).
#   · Gunicorn (web) + run_scheduler (tareas) como unidades systemd
#     (arrancan tras reboot y se reinician si crashean).
#   · NGINX como reverse proxy en HTTP :8000, ABIERTO A TODA LA RED.
#   · Crea automáticamente el usuario Owner y los grupos/Teams desde cert.txt
#     (bootstrap idempotente data_update_certs_app).
#
#   NO es producción endurecida (SQLite + HTTP sin TLS). Si tienes MySQL/Postgres
#   externo, exporta DATABASE_URL y el perfil standalone lo usa sin tocar nada:
#     DATABASE_URL=mysql://user:pass@host:3306/certmanager sudo ./install_server.sh
#
#   ¿Sin permisos de root en el servidor? Usa ./levantamiento.sh (rootless).
#
# Requisitos: root en RHEL/Rocky/Debian/Ubuntu, python3 (3.11+), y cert.txt en la
# raíz para sembrar el monitoreo (si falta, crea solo Owner + grupo propio).
#
# Uso:
#   sudo ./install_server.sh
#   sudo CF_OWNER_PASSWORD=xxx ./install_server.sh           # sin prompt
#   sudo PORT=8080 ./install_server.sh                       # otro puerto
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${APP_USER:-certmanager}"
VENV="${VENV:-$APP_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8000}"                       # puerto público (NGINX), HTTP plano
GUNICORN_BIND="127.0.0.1:8001"             # interno: NGINX hace proxy aquí
WORKERS="${WORKERS:-3}"
DATA_DIR="${CERTFORGE_DATA_DIR:-$APP_DIR/data}"
LOG_DIR="${LOG_DIR:-/var/log/certmanager}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.preprod}"   # gitignored (.env.*)
CF_OWNER_EMAIL="${CF_OWNER_EMAIL:-jairol_grullon@claro.com.do}"
# Rutas del sistema (sobreescribibles solo para pruebas/sandbox).
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
NGINX_CONF_DIR="${NGINX_CONF_DIR:-/etc/nginx/conf.d}"

[ "$(id -u)" -eq 0 ] || { echo "ERROR: corre como root (sudo ./install_server.sh). Sin root usa ./levantamiento.sh." >&2; exit 1; }

echo "== CertManager — install_server.sh PREPROD/STG (SQLite, systemd+NGINX, HTTP :$PORT, abierto a todos) =="

# --- 1) Paquetes de sistema (SQLite: sin libs de MySQL) ---------------------
echo ">> [1/8] Instalando paquetes de sistema…"
if command -v apt-get >/dev/null; then
  apt-get update
  apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev build-essential pkg-config \
    nginx gettext curl
elif command -v dnf >/dev/null; then
  dnf install -y python3 python3-devel gcc make pkgconf-pkg-config nginx gettext curl
elif command -v yum >/dev/null; then
  yum install -y python3 python3-devel gcc make pkgconfig nginx gettext curl
else
  echo "ADVERTENCIA: gestor de paquetes no detectado; instala python3/venv, nginx, gcc y curl a mano." >&2
fi

# --- 2) Usuario de servicio -------------------------------------------------
if ! id "$APP_USER" >/dev/null 2>&1; then
  echo ">> [2/8] Creando usuario de servicio $APP_USER"
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER" 2>/dev/null \
    || useradd -r -d "$APP_DIR" -s /sbin/nologin "$APP_USER"
else
  echo ">> [2/8] Usuario de servicio $APP_USER ya existe"
fi

# --- 3) Virtualenv + dependencias (SQLite: base + gunicorn, sin MySQL) ------
echo ">> [3/8] Virtualenv y dependencias…"
[ -d "$VENV" ] || "$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
# Si exportaste DATABASE_URL apuntando a MySQL, añade el driver:
EXTRA_REQ=""
case "${DATABASE_URL:-}" in mysql://*) EXTRA_REQ="mysqlclient>=2.2" ;; esac
"$VENV/bin/pip" install -r "$APP_DIR/requirements/base.txt" "gunicorn>=21.2" $EXTRA_REQ

# --- 4) CSS (Tailwind): ya viene compilado; recompila solo si falta y hay npm
if [ ! -f "$APP_DIR/static/css/forge.css" ]; then
  if command -v npm >/dev/null; then
    echo ">> [4/8] Compilando CSS (Tailwind)…"
    ( cd "$APP_DIR" && npm ci && npm run build:css )
  else
    echo "ADVERTENCIA: no existe static/css/forge.css y no hay npm; la UI se verá sin estilos." >&2
  fi
else
  echo ">> [4/8] CSS ya compilado (static/css/forge.css)"
fi

# --- 5) Archivo de entorno del servicio (SQLite + HTTP plano + abierto) -----
echo ">> [5/8] Generando ${ENV_FILE}…"
mkdir -p "$DATA_DIR" "$LOG_DIR"
cat > "$ENV_FILE" <<ENV
# Generado por install_server.sh — perfil PREPROD/STG (SQLite, HTTP :$PORT).
DJANGO_SETTINGS_MODULE=config.settings.standalone
DEBUG=False
CERTFORGE_DATA_DIR=$DATA_DIR
LOG_DIR=$LOG_DIR
ALLOWED_HOSTS=*
# HTTP PLANO: sin redirección TLS ni cookies Secure (no rompe el login en :$PORT).
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=0
# El scheduler corre en su propio servicio (run_scheduler); que NO arranque
# también dentro de cada worker de gunicorn (evita tareas duplicadas).
RUN_SCHEDULER=False
OBSFORGE_ENABLED=False
ENV
# Si exportaste DATABASE_URL (MySQL/Postgres externos), lo respeta el perfil standalone.
[ -n "${DATABASE_URL:-}" ] && echo "DATABASE_URL=$DATABASE_URL" >> "$ENV_FILE"
chmod 600 "$ENV_FILE"

# --- 6) migrate / collectstatic / compilemessages + Owner & grupos ----------
echo ">> [6/8] migrate / collectstatic / compilemessages…"
set -a; . "$ENV_FILE"; set +a
( cd "$APP_DIR"
  "$VENV/bin/python" manage.py migrate --no-input
  "$VENV/bin/python" manage.py collectstatic --no-input
  "$VENV/bin/python" manage.py compilemessages 2>/dev/null || echo "   (compilemessages omitido; el .mo ya viene compilado)"
)

echo ">> [6/8] Creando el Owner y los grupos/Teams (bootstrap idempotente)…"
export CF_OWNER_EMAIL
while [ -z "${CF_OWNER_PASSWORD:-}" ]; do
  read -r -s -p "   Contraseña para el Owner ($CF_OWNER_EMAIL): " CF_OWNER_PASSWORD
  echo
  [ -z "$CF_OWNER_PASSWORD" ] && echo "      La contraseña no puede estar vacía. Intenta de nuevo."
done
export CF_OWNER_PASSWORD
( cd "$APP_DIR"
  if [ -f "cert.txt" ]; then
    echo "   cert.txt encontrado: Owner + grupos (sp_*) + certificados…"
    "$VENV/bin/python" manage.py data_update_certs_app --source cert.txt
  else
    echo "   Sin cert.txt: Owner + grupo propio (coloca cert.txt y reejecuta para los demás grupos)."
    "$VENV/bin/python" manage.py data_update_certs_app --skip-certs
  fi
)

# Permisos: lo que el servicio debe poder escribir (SQLite/WAL, media, logs).
chown -R "$APP_USER":"$APP_USER" "$APP_DIR" "$DATA_DIR" "$LOG_DIR"

# --- 7) Unidades systemd (web + scheduler) ----------------------------------
echo ">> [7/8] Instalando unidades systemd…"
cat > "$SYSTEMD_DIR/certmanager.service" <<UNIT
[Unit]
Description=CertManager (Gunicorn — preprod/stg SQLite)
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/gunicorn config.wsgi:application \\
  --bind $GUNICORN_BIND --workers $WORKERS \\
  --access-logfile - --error-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

cat > "$SYSTEMD_DIR/certmanager-scheduler.service" <<UNIT
[Unit]
Description=CertManager (Scheduler — monitoreo/reportes/backup)
After=certmanager.service
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python manage.py run_scheduler
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

# --- 8) NGINX (:$PORT HTTP) -> gunicorn (127.0.0.1:8001) --------------------
echo ">> [8/8] Configurando NGINX en :$PORT (HTTP plano)…"
NGINX_SITE="$NGINX_CONF_DIR/certmanager.conf"
cat > "$NGINX_SITE" <<NGINX
# CertManager preprod/stg — HTTP plano en :$PORT, proxy a gunicorn local.
server {
    listen $PORT default_server;
    listen [::]:$PORT default_server;
    server_name _;

    client_max_body_size 10m;

    location / {
        proxy_pass http://$GUNICORN_BIND;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    location = /health/ {
        access_log off;
        proxy_pass http://$GUNICORN_BIND;
        proxy_set_header Host              \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX
# Si PORT=80 hay que quitar el sitio default de Debian/Ubuntu (evita duplicar default_server).
[ "$PORT" = "80" ] && rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# SELinux (RHEL/Rocky): permite que NGINX haga proxy a un socket local.
if command -v getenforce >/dev/null && [ "$(getenforce)" = "Enforcing" ]; then
  command -v setsebool >/dev/null && setsebool -P httpd_can_network_connect 1 || true
fi
# Firewall: abre el puerto público para que acceda toda la red.
if command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port="$PORT"/tcp && firewall-cmd --reload || true
elif command -v ufw >/dev/null && ufw status >/dev/null 2>&1; then
  ufw allow "$PORT"/tcp || true
fi

# --- Arranque ---------------------------------------------------------------
systemctl daemon-reload
systemctl enable --now certmanager certmanager-scheduler
nginx -t && systemctl enable --now nginx && systemctl reload nginx

IPS="$(hostname -I 2>/dev/null || true)"
echo ""
echo ">> ¡Listo! CertManager accesible a toda la red en HTTP :$PORT (Owner: $CF_OWNER_EMAIL)."
for ip in $IPS; do echo "     http://$ip:$PORT/"; done
echo ""
echo ">> Verificar:"
echo "     systemctl status certmanager certmanager-scheduler nginx"
echo "     curl -fsS http://127.0.0.1:$PORT/health/"
