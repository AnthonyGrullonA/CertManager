#!/usr/bin/env bash
# ============================================================================
# install_mac.sh - CertManager para PRUEBAS / MIGRACION local en macOS (SQLite).
#
#   Espejo de install_windows.bat:
#   - Perfil standalone (SQLite automatico, sin MySQL).
#   - venv + dependencias + migra la BD SQLite.
#   - Carga Owner + configuracion por defecto Y MIGRA EL MONITOREO desde el
#     cert.txt si esta en la raiz (data_update_certs_app).
#   - Arranca el server de desarrollo accesible desde la RED (0.0.0.0:8000).
#   - NO usar en produccion: es para validar/migrar localmente.
#
# Requisitos: Python 3.11+ (python3 en el PATH). (Node.js opcional, para el CSS.)
# Coloca tu cert.txt en la raiz ANTES de correr para migrar todo el monitoreo.
# Uso:   ./install_mac.sh
#        CF_OWNER_PASSWORD=xxx ./install_mac.sh     # sin prompt de contrasena
# ============================================================================
set -e
cd "$(dirname "$0")"
echo "== CertManager - prueba local en macOS (SQLite) =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 no esta en el PATH."
  echo "  SIN ADMIN: instala Python para tu usuario:"
  echo "    - python.org/downloads -> instalador oficial de macOS (per-usuario), o"
  echo "    - brew install python (si tienes Homebrew)."
  echo "  Reabre la terminal y vuelve a correr ./install_mac.sh"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo ">> Creando entorno virtual .venv ..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source ".venv/bin/activate"

# Si el venv quedo roto (p.ej. se renombro la carpeta del repo y el activate
# apunta a la ruta vieja), se recrea desde cero.
if ! command -v python >/dev/null 2>&1 || ! python -c '' 2>/dev/null; then
  echo ">> El .venv esta roto (ruta del repo cambiada?): recreandolo ..."
  deactivate 2>/dev/null || true
  rm -rf .venv
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

echo ">> Instalando dependencias (sin MySQL) ..."
python -m pip install --upgrade pip
pip install -r requirements/base.txt || { echo "ERROR instalando dependencias."; exit 1; }

# Configuracion de entorno para SQLite / standalone
export DJANGO_SETTINGS_MODULE=config.settings.standalone
export CERTFORGE_DATA_DIR="$PWD/data"
export OBSFORGE_ENABLED=0

# CSS (Tailwind): se compila si hay npm; si no, la UI puede verse sin estilos.
if command -v npm >/dev/null 2>&1; then
  if [ ! -f "static/css/forge.css" ]; then
    echo ">> Compilando CSS con npm ..."
    npm ci
    npm run build:css
  fi
else
  echo "(Aviso: no hay npm; si no existe static/css/forge.css la UI se vera sin estilos.)"
fi

echo ">> Aplicando migraciones (crea la BD SQLite) ..."
python manage.py migrate --no-input || { echo "ERROR en migrate."; exit 1; }

echo ">> Recolectando estaticos ..."
python manage.py collectstatic --no-input

# --- Owner + configuracion (+ migracion del monitoreo desde cert.txt) -------
: "${CF_OWNER_EMAIL:=jairol_grullon@claro.com.do}"
export CF_OWNER_EMAIL

# Pide la contrasena del Owner y NO continua hasta que no este vacia
# (si viene por entorno CF_OWNER_PASSWORD, no pregunta).
while [ -z "${CF_OWNER_PASSWORD:-}" ]; do
  read -r -s -p "Contrasena para el Owner ($CF_OWNER_EMAIL): " CF_OWNER_PASSWORD
  echo
  [ -z "$CF_OWNER_PASSWORD" ] && echo "   La contrasena no puede estar vacia. Intenta de nuevo."
done
export CF_OWNER_PASSWORD

if [ -f "cert.txt" ]; then
  echo ">> Migrando el monitoreo desde cert.txt (Owner + configuracion + certificados) ..."
  python manage.py data_update_certs_app --source cert.txt || { echo "ERROR cargando datos."; exit 1; }
else
  echo ">> No hay cert.txt en la raiz: cargo solo Owner + configuracion."
  echo "   Coloca tu cert.txt en la raiz y vuelve a correr para MIGRAR el monitoreo."
  python manage.py data_update_certs_app --skip-certs || { echo "ERROR cargando datos."; exit 1; }
fi

echo
echo ">> Listo. Owner: $CF_OWNER_EMAIL"
echo ">> Accesible desde la RED (todas las interfaces). Tu(s) IP(s) en la LAN:"
ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" {print "   " $2}'
echo "   Local:    http://127.0.0.1:8000/"
echo "   Red:      http://<TU-IP>:8000/"
echo "   (macOS puede pedir permitir conexiones entrantes a Python: pulsa Permitir.)"
echo ">> Arrancando (Ctrl+C para detener) ..."
python manage.py runserver 0.0.0.0:8000
