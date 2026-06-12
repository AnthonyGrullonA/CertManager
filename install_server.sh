#!/usr/bin/env bash
# =============================================================================
# install_server.sh — Instala CertManager en un servidor Linux como SERVICIO.
#
#   · Gunicorn (web) + run_scheduler (tareas) como unidades systemd.
#   · NGINX como reverse proxy con terminación TLS (redirección 80->443).
#   · Solo el APLICATIVO: la base de datos MySQL es EXTERNA (la provee Claro,
#     vía las vars DB_* en CLARO_NECESIDAD/.env).
#
# Requisitos: ejecutar como root en RHEL/Rocky/Debian/Ubuntu. Completar antes el
# archivo CLARO_NECESIDAD/.env (copia de .env.example) y, si vas a terminar TLS
# aquí, tener el certificado del FQDN.
#
# Uso:   sudo ./install_server.sh
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${APP_USER:-certmanager}"
VENV="${VENV:-$APP_DIR/.venv}"
ENV_FILE="$APP_DIR/CLARO_NECESIDAD/.env"
PYTHON_BIN="${PYTHON_BIN:-python3}"
GUNICORN_BIND="127.0.0.1:8000"
WORKERS="${WORKERS:-3}"
# Certificado wildcard *.claro.com.do (colócalo en estas rutas antes de correr,
# o pásalas por entorno). Ver CLARO_NECESIDAD/04_aprovisionamiento_y_certificados.md
#   TLS_CERT = certificado + cadena intermedia (fullchain)
#   TLS_KEY  = clave privada
TLS_CERT="${TLS_CERT:-/etc/ssl/claro/claro-wildcard.crt}"
TLS_KEY="${TLS_KEY:-/etc/ssl/claro/claro-wildcard.key}"

[ "$(id -u)" -eq 0 ] || { echo "ERROR: corre como root (sudo)." >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "ERROR: falta $ENV_FILE. Copia CLARO_NECESIDAD/.env.example y complétalo." >&2; exit 1; }
if [ ! -f "$TLS_CERT" ] || [ ! -f "$TLS_KEY" ]; then
  echo "ADVERTENCIA: no se encuentra el certificado TLS:" >&2
  echo "   $TLS_CERT / $TLS_KEY" >&2
  echo "   Coloca el wildcard *.claro.com.do ahí (o exporta TLS_CERT/TLS_KEY) antes de" >&2
  echo "   exponer en 443. NGINX no arrancará en TLS hasta que existan." >&2
fi

# FQDN desde ALLOWED_HOSTS del .env (primer host).
FQDN="$(grep -E '^ALLOWED_HOSTS=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d ' ' | cut -d, -f1)"
FQDN="${FQDN:-certmanager.local}"
echo ">> FQDN: $FQDN"

# --- 1) Paquetes de sistema -------------------------------------------------
echo ">> Instalando paquetes de sistema…"
if command -v apt-get >/dev/null; then
  apt-get update
  apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev build-essential pkg-config \
    default-libmysqlclient-dev libmariadb3 nginx gettext curl
elif command -v dnf >/dev/null; then
  dnf install -y python3 python3-devel gcc make pkgconf-pkg-config \
    mysql-devel nginx gettext curl
elif command -v yum >/dev/null; then
  yum install -y python3 python3-devel gcc make pkgconfig \
    mysql-devel nginx gettext curl
else
  echo "ADVERTENCIA: gestor de paquetes no detectado; instala las deps manualmente." >&2
fi

# --- 2) Usuario de servicio -------------------------------------------------
if ! id "$APP_USER" >/dev/null 2>&1; then
  echo ">> Creando usuario de servicio $APP_USER"
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER" 2>/dev/null \
    || useradd -r -d "$APP_DIR" -s /sbin/nologin "$APP_USER"
fi

# --- 3) Virtualenv + dependencias ------------------------------------------
echo ">> Creando virtualenv y dependencias…"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
# obsforge vive en índice privado: si no lo tienes, usa requirements/docker.txt
REQ="requirements/prod.txt"
if [ -n "${PIP_EXTRA_INDEX_URL:-}" ]; then
  "$VENV/bin/pip" install -r "$APP_DIR/$REQ" --extra-index-url "$PIP_EXTRA_INDEX_URL"
else
  echo "   (sin PIP_EXTRA_INDEX_URL: instalando sin obsforge — requirements/docker.txt)"
  "$VENV/bin/pip" install -r "$APP_DIR/requirements/docker.txt"
fi

# --- 4) CSS (Tailwind): compilar si hay npm; si no, debe existir forge.css --
if [ ! -f "$APP_DIR/static/css/forge.css" ]; then
  if command -v npm >/dev/null; then
    echo ">> Compilando CSS (Tailwind)…"
    ( cd "$APP_DIR" && npm ci && npm run build:css )
  else
    echo "ADVERTENCIA: no existe static/css/forge.css y no hay npm." >&2
    echo "             Compílalo en otra máquina (npm run build:css) y cópialo." >&2
  fi
fi

# --- 5) Migraciones, estáticos, traducciones --------------------------------
echo ">> migrate / collectstatic / compilemessages…"
set -a; . "$ENV_FILE"; set +a
( cd "$APP_DIR"
  "$VENV/bin/python" manage.py migrate --no-input
  "$VENV/bin/python" manage.py collectstatic --no-input
  "$VENV/bin/python" manage.py compilemessages 2>/dev/null || echo "   (compilemessages omitido; el .mo ya viene compilado)"
)

# Permisos + dir de logs
mkdir -p "${LOG_DIR:-/var/log/certmanager}"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR" "${LOG_DIR:-/var/log/certmanager}"

# --- 6) Unidades systemd (web + scheduler) ----------------------------------
echo ">> Instalando unidades systemd…"
cat > /etc/systemd/system/certmanager.service <<UNIT
[Unit]
Description=CertManager (Gunicorn)
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

cat > /etc/systemd/system/certmanager-scheduler.service <<UNIT
[Unit]
Description=CertManager (Scheduler / tareas)
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

# --- 7) NGINX (reverse proxy + TLS) -----------------------------------------
echo ">> Configurando NGINX…"
NGINX_SITE="/etc/nginx/conf.d/certmanager.conf"
cat > "$NGINX_SITE" <<NGINX
server {
    listen 80;
    server_name $FQDN;
    return 301 https://\$host\$request_uri;
}
server {
    listen 443 ssl;
    server_name $FQDN;

    ssl_certificate     $TLS_CERT;
    ssl_certificate_key $TLS_KEY;

    client_max_body_size 10m;

    location / {
        proxy_pass http://$GUNICORN_BIND;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
    location = /health/ { proxy_pass http://$GUNICORN_BIND; access_log off; }
}
NGINX

# --- 8) Arranque ------------------------------------------------------------
echo ">> Habilitando y arrancando servicios…"
systemctl daemon-reload
systemctl enable --now certmanager certmanager-scheduler
nginx -t && systemctl enable --now nginx && systemctl reload nginx

echo ""
echo ">> Listo. Verifica:"
echo "     systemctl status certmanager certmanager-scheduler"
echo "     curl -fsS https://$FQDN/health/"
echo ""
echo ">> Bootstrap (Owner + configuración + certificados):"
echo "     coloca cert.txt en la raíz y corre:  sudo -u $APP_USER ./data_update_certs_app.sh"
