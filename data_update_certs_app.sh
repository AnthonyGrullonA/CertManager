#!/usr/bin/env bash
# =============================================================================
# data_update_certs_app.sh — bootstrap de PRODUCCIÓN.
#
# Carga, de forma idempotente:
#   1. El usuario Owner de la organización.
#   2. La configuración global con los defaults de producción (+ SMTP).
#   3. Los certificados desde ./cert.txt (formato dominio|correo|umbral|puerto),
#      con ubicación (ntp/ntt -> Servidor, claro.com.do -> netscaler), monitoreo
#      por plataforma + correo y grupos de soporte (sp*).
#
# NO versiona secretos: el repo es público. Los valores sensibles (contraseña del
# Owner, credenciales SMTP) van en `data_update_certs_app.env` (gitignored).
# Copia `data_update_certs_app.env.example` -> `data_update_certs_app.env` y
# complétalo, coloca tu `cert.txt` en la raíz y corre:
#
#     ./data_update_certs_app.sh
#
# Opciones extra se pasan tal cual al management command, p.ej.:
#     ./data_update_certs_app.sh --dry-run
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# Carga el archivo de entorno (secretos) si existe. Prioridad:
#   1) data_update_certs_app.env (específico del bootstrap)
#   2) CLARO_NECESIDAD/.env (el mismo de producción que usan los install_*.sh)
# En Docker no hace falta: el env ya viene inyectado por env_file.
if [ -f data_update_certs_app.env ]; then
  echo ">> Cargando data_update_certs_app.env"
  set -a; . ./data_update_certs_app.env; set +a
elif [ -f CLARO_NECESIDAD/.env ]; then
  echo ">> Cargando CLARO_NECESIDAD/.env"
  set -a; . ./CLARO_NECESIDAD/.env; set +a
fi

PYTHON="${PYTHON:-python}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.standalone}"
SOURCE="${CF_CERT_SOURCE:-cert.txt}"

# ¿Solo Owner + configuración? (--skip-certs no requiere cert.txt)
SKIP_CERTS=0
for a in "$@"; do [ "$a" = "--skip-certs" ] && SKIP_CERTS=1; done

if [ "$SKIP_CERTS" = "0" ] && [ ! -f "$SOURCE" ]; then
  echo "ERROR: no se encuentra '$SOURCE'. Coloca tu cert.txt en la raíz (o exporta" >&2
  echo "       CF_CERT_SOURCE), o usa --skip-certs para cargar solo Owner + configuración." >&2
  exit 1
fi

echo ">> Aplicando migraciones…"
"$PYTHON" manage.py migrate --no-input

echo ">> Cargando Owner + configuración$([ "$SKIP_CERTS" = "0" ] && echo " + certificados") (idempotente)…"
if [ "$SKIP_CERTS" = "1" ]; then
  "$PYTHON" manage.py data_update_certs_app "$@"
else
  "$PYTHON" manage.py data_update_certs_app --source "$SOURCE" "$@"
fi

# Chequeo real de los certificados (opcional: lento y requiere conectividad).
if [ "${CF_RUN_CHECK:-0}" = "1" ]; then
  echo ">> Poblando el estado real (check_certificates)…"
  "$PYTHON" manage.py check_certificates || echo "   (chequeo falló/sin conectividad; córrelo luego)"
fi

echo ">> Listo."
