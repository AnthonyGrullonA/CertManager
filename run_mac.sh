#!/usr/bin/env bash
# ============================================================================
# run_mac.sh - Arranca CertManager en macOS accesible desde la RED.
#
#   Como `python manage.py runserver` pero escuchando en TODAS las interfaces
#   (0.0.0.0), para que otras maquinas de la red lo abran por la IP del equipo.
#   Perfil standalone (SQLite). Requiere haber corrido ./install_mac.sh antes
#   (venv + BD + Owner). NO instala nada: solo levanta el server.
#
#   Puerto: 8000 por defecto, o el que pongas en la variable PORT.
#   Uso:   ./run_mac.sh          o          PORT=9000 ./run_mac.sh
#
#   NOTA: es el server de DESARROLLO de Django (para pruebas internas, pocos
#   usuarios). Para produccion usa Linux/Docker/K8s (ver CLARO_NECESIDAD).
# ============================================================================
set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/activate" ]; then
  echo "ERROR: no existe el entorno .venv. Corre primero ./install_mac.sh"
  exit 1
fi
# shellcheck disable=SC1091
source ".venv/bin/activate"
if ! command -v python >/dev/null 2>&1 || ! python -c '' 2>/dev/null; then
  echo "ERROR: el .venv esta roto (ruta del repo cambiada?). Corre ./install_mac.sh"
  exit 1
fi

export DJANGO_SETTINGS_MODULE=config.settings.standalone
export CERTFORGE_DATA_DIR="$PWD/data"
export OBSFORGE_ENABLED=0
PORT="${PORT:-8000}"

echo "============================================================"
echo " CertManager accesible desde la RED (todas las interfaces)"
echo " Puerto: $PORT"
echo " Tu(s) IP(s) en la LAN:"
ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" {print "   " $2}'
echo " Desde otra maquina:  http://<TU-IP>:$PORT/"
echo " (macOS puede pedir permitir conexiones entrantes a Python: pulsa Permitir.)"
echo "============================================================"

python manage.py runserver 0.0.0.0:"$PORT"
