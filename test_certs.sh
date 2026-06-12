#!/usr/bin/env bash
# ============================================================================
# test_certs.sh — Prueba con curl los certificados listados en cert.txt
#
# Lee el cert.txt legado (formato: dominio|correo|umbral|puerto — el mismo
# que consume `manage.py data_update_certs_app`), deduplica por dominio:puerto
# y valida el certificado TLS de cada host con curl. Al final imprime un
# recuento: cuántos se probaron, cuántos validaron bien, cuántos fallaron y
# cuál fue el error más recurrente.
#
# Uso:
#   ./test_certs.sh [archivo]            # por defecto ./cert.txt
#   TIMEOUT=15 PARALLEL=20 ./test_certs.sh cert.txt
#
# Variables:
#   TIMEOUT   segundos máximos por host (default 10)
#   PARALLEL  chequeos simultáneos      (default 10)
# ============================================================================
set -u

SOURCE="${1:-cert.txt}"
TIMEOUT="${TIMEOUT:-10}"
PARALLEL="${PARALLEL:-10}"
DEFAULT_PORT=443

if [ ! -f "$SOURCE" ]; then
  echo "ERROR: no encuentro '$SOURCE'. Coloca el cert.txt en la raíz o pásalo como argumento." >&2
  exit 1
fi

RESULTS="$(mktemp)"
TARGETS="$(mktemp)"
trap 'rm -f "$RESULTS" "$TARGETS"' EXIT

# --- 1) Parsear cert.txt: dominio|correo|umbral|puerto ----------------------
# Mismas reglas que el importador: líneas vacías/incompletas se ignoran,
# puerto vacío o inválido => 443. Se deduplica por dominio:puerto.
# tr -d '\r' por si el archivo viene de Windows.
tr -d '\r' < "$SOURCE" \
  | awk -F'|' -v defport="$DEFAULT_PORT" '
      {
        gsub(/^[ \t]+|[ \t]+$/, "", $1)
        domain = tolower($1)
        sub(/^[a-z0-9+.-]+:\/\//, "", domain)   # quita esquema de URL
        sub(/[\/#?].*$/, "", domain)            # quita ruta/fragmento
        port = defport
        if (match(domain, /:[0-9]+$/)) {        # puerto embebido host:puerto
          port = substr(domain, RSTART + 1, RLENGTH - 1)
          domain = substr(domain, 1, RSTART - 1)
        }
        if (domain == "" || domain ~ /^#/) next
        if (NF >= 4) {
          gsub(/^[ \t]+|[ \t]+$/, "", $4)
          if ($4 ~ /^[0-9]+$/) port = $4
        }
        print domain ":" port
      }' \
  | sort -u > "$TARGETS"

TOTAL=$(wc -l < "$TARGETS" | tr -d ' ')
if [ "$TOTAL" -eq 0 ]; then
  echo "ERROR: '$SOURCE' no tiene líneas válidas (formato esperado: dominio|correo|umbral|puerto)." >&2
  exit 1
fi

echo ">> Probando $TOTAL certificados de '$SOURCE' (timeout ${TIMEOUT}s, ${PARALLEL} en paralelo)..."
echo

# --- 2) Chequear cada host con curl -----------------------------------------
# El handshake TLS ocurre antes del HTTP, así que cualquier respuesta HTTP
# (incluso 404/500) significa que el certificado validó bien.
check_one() {
  target="$1"
  err=$(curl -sS -o /dev/null \
        --connect-timeout 5 --max-time "$TIMEOUT" \
        "https://$target/" 2>&1 >/dev/null)
  rc=$?

  if [ "$rc" -eq 0 ]; then
    printf 'OK|%s|\n' "$target" >> "$RESULTS"
    printf '  [OK]    %s\n' "$target"
    return
  fi

  # Clasificar el error por el código de salida de curl
  case "$rc" in
    60) reason="certificado invalido (expirado / no confiable / autofirmado)" ;;
    51|53|54|58|59) reason="fallo de verificacion SSL" ;;
    35) reason="fallo en el handshake TLS" ;;
    6)  reason="no resuelve DNS" ;;
    7)  reason="conexion rechazada" ;;
    28) reason="timeout de conexion" ;;
    52|56) reason="conexion cortada por el servidor" ;;
    *)  reason="error curl $rc" ;;
  esac

  # Detalle fino para los fallos de certificado (expirado vs. autofirmado, etc.)
  detail=$(printf '%s' "$err" | grep -o 'SSL certificate problem: [^"]*' | head -1)
  case "$detail" in
    *"certificate has expired"*)           reason="certificado expirado" ;;
    *"self-signed certificate"*|*"self signed"*) reason="certificado autofirmado" ;;
    *"unable to get local issuer"*)        reason="cadena incompleta / CA no confiable" ;;
  esac
  if printf '%s' "$err" | grep -qi "doesn't match\|does not match\|hostname mismatch\|no alternative certificate subject name matches"; then
    reason="el certificado no corresponde al dominio (mismatch)"
  fi

  printf 'FAIL|%s|%s\n' "$target" "$reason" >> "$RESULTS"
  printf '  [FALLO] %-45s %s\n' "$target" "$reason"
}
export -f check_one
export RESULTS TIMEOUT

xargs -P "$PARALLEL" -n 1 -I {} bash -c 'check_one "$@"' _ {} < "$TARGETS"

# --- 3) Recuento -------------------------------------------------------------
OK=$(grep -c '^OK|' "$RESULTS" || true)
FAIL=$(grep -c '^FAIL|' "$RESULTS" || true)

echo
echo "==================== RESUMEN ===================="
echo "  Se probaron               : $TOTAL certificados"
echo "  Validados correctamente   : $OK"
echo "  No se pudieron validar    : $FAIL"

if [ "$FAIL" -gt 0 ]; then
  TOP=$(grep '^FAIL|' "$RESULTS" | cut -d'|' -f3 | sort | uniq -c | sort -rn | head -1)
  TOP_N=$(echo "$TOP" | awk '{print $1}')
  TOP_REASON=$(echo "$TOP" | sed 's/^ *[0-9]* //')
  echo "  Error mas recurrente      : \"$TOP_REASON\" ($TOP_N de $FAIL)"
  echo
  echo "  Desglose de errores:"
  grep '^FAIL|' "$RESULTS" | cut -d'|' -f3 | sort | uniq -c | sort -rn | sed 's/^/   /'
  echo
  echo "  Hosts fallidos:"
  grep '^FAIL|' "$RESULTS" | awk -F'|' '{printf "    %-45s %s\n", $2, $3}' | sort
fi
echo "================================================="

# Código de salida: 0 si todos validaron, 1 si hubo fallos
[ "$FAIL" -eq 0 ]
