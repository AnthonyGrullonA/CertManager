#!/usr/bin/env bash
# =============================================================================
# fix_smtp_openssl.sh — Reactiva los providers de OpenSSL 3 (default + legacy)
#                       para el proceso de CertManager, SIN root.
#
#   Síntoma que arregla: al enviar correo el SMTP falla con
#       "[digital envelope routines] ... unsupported"
#   Causa: OpenSSL 3 del servidor tiene deshabilitado algún algoritmo (provider
#   default/legacy no activo). Se le pasa a OpenSSL un openssl.cnf propio vía la
#   variable de entorno OPENSSL_CONF (no toca /etc, no necesita admin).
#
#   Qué hace:
#     1) crea ./openssl-legacy.cnf (activa providers default + legacy)
#     2) añade OPENSSL_CONF=<ruta absoluta> al .env.preprod del despliegue
#     3) verifica que con ese cnf vuelven los algoritmos
#     4) reinicia el servicio (./levantamiento.sh restart) para que gunicorn lo tome
#
#   Es aditivo (mantiene 'default' y suma 'legacy'); no rompe el resto del TLS.
#   Idempotente: se puede correr varias veces.
#
# Uso:
#   ./fix_smtp_openssl.sh
#   SKIP_RESTART=1 ./fix_smtp_openssl.sh   # aplica sin reiniciar (reinicia tú luego)
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR="$(pwd)"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.preprod}"
CNF="${CNF:-$APP_DIR/openssl-legacy.cnf}"
VENV="${VENV:-$APP_DIR/.venv}"
if [ -x "$VENV/bin/python" ]; then PYTHON="$VENV/bin/python"; else PYTHON="${PYTHON:-python3}"; fi

echo "== Fix SMTP: reactivar OpenSSL providers (default+legacy) sin root =="

# --- 1) openssl.cnf propio --------------------------------------------------
cat > "$CNF" <<'CNF'
# CertManager — reactiva los providers de OpenSSL 3 para este proceso.
openssl_conf = openssl_init

[openssl_init]
providers = provider_sect

[provider_sect]
default = default_sect
legacy = legacy_sect

[default_sect]
activate = 1

[legacy_sect]
activate = 1
CNF
echo ">> [1/4] Escrito $CNF"

# --- 2) Apuntar OPENSSL_CONF en el .env del servicio (idempotente) ----------
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: no existe $ENV_FILE. Corre primero el instalador (./levantamiento.sh)." >&2
  echo "       (El fix necesita ese archivo de entorno para inyectar OPENSSL_CONF en gunicorn.)" >&2
  exit 1
fi
# Quita cualquier OPENSSL_CONF previo y añade el actual (ruta absoluta).
tmp="$ENV_FILE.tmp.$$"
grep -v '^OPENSSL_CONF=' "$ENV_FILE" > "$tmp" || true
echo "OPENSSL_CONF=$CNF" >> "$tmp"
mv "$tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo ">> [2/4] $ENV_FILE -> OPENSSL_CONF=$CNF"

# --- 3) Verificación con el nuevo cnf ---------------------------------------
echo ">> [3/4] Verificando algoritmos con el nuevo OPENSSL_CONF:"
OPENSSL_CONF="$CNF" "$PYTHON" - <<'PY' || true
import ssl, hashlib
print("   openssl:", ssl.OPENSSL_VERSION)
for algo in ("md5", "md4", "sha256"):
    try:
        hashlib.new(algo, b"x")
        print(f"   {algo:7}: OK")
    except Exception as e:
        print(f"   {algo:7}: FALLA -> {e}")
PY
echo "   (md5 es del provider 'default'; md4 confirma que 'legacy' quedó activo.)"

# --- 4) Reinicio del servicio -----------------------------------------------
if [ "${SKIP_RESTART:-0}" = "1" ]; then
  echo ">> [4/4] SKIP_RESTART=1: no reinicio. Aplica luego: ./levantamiento.sh restart"
elif [ -x "$APP_DIR/levantamiento.sh" ]; then
  echo ">> [4/4] Reiniciando el servicio (gunicorn tomará OPENSSL_CONF)…"
  "$APP_DIR/levantamiento.sh" restart
else
  echo ">> [4/4] No encuentro levantamiento.sh ejecutable; reinicia el servicio a mano." >&2
fi

echo ""
echo ">> Listo. Prueba el SMTP ahora (botón 'Probar envío', o el diagnóstico con"
echo "   smtplib.set_debuglevel). Si AÚN falla con el mismo error, probablemente es"
echo "   FIPS u otra causa: corre el diagnóstico y compartimos el traceback."
