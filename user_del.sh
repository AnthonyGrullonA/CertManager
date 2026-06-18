#!/usr/bin/env bash
# =============================================================================
# user_del.sh — Elimina un usuario de CertManager (sea Owner o no).
#
#   Lista los usuarios en una lista numerada y te pide el NÚMERO del que quieres
#   borrar. Muestra qué se verá afectado y pide confirmación. Es DESTRUCTIVO.
#
#   Qué pasa con lo relacionado (definido por el modelo):
#     · Certificados y grupos/Teams creados por él  -> SE CONSERVAN (created_by=NULL).
#     · Sus membresías de grupo, API keys, alertas, preferencias y 2FA -> se borran.
#
#   Salvaguarda: si es el ÚNICO Owner, NO lo elimina (dejaría la app sin
#   administrador). Para forzarlo: FORCE=1 ./user_del.sh
#
# Uso:
#   ./user_del.sh           # lista y pregunta el número
#   FORCE=1 ./user_del.sh   # salta la confirmación y la salvaguarda del único Owner
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR="$(pwd)"
VENV="${VENV:-$APP_DIR/.venv}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.preprod}"

if [ -x "$VENV/bin/python" ]; then PYTHON="$VENV/bin/python"; else PYTHON="${PYTHON:-python3}"; fi

# Apunta a la BD del despliegue (igual que owner.sh).
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
elif [ -f "CLARO_NECESIDAD/.env" ]; then
  set -a; . "CLARO_NECESIDAD/.env"; set +a
fi
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.standalone}"
export RUN_SCHEDULER=False   # tarea de un solo uso: no levantar el scheduler

# --- Listado de usuarios (una línea por usuario: email<TAB>OWNER/-<TAB>nombre) -
EMAILS=(); OWNER=(); NAMES=()
while IFS=$'\t' read -r _em _ow _nm; do
  [ -z "$_em" ] && continue
  EMAILS+=("$_em"); OWNER+=("$_ow"); NAMES+=("$_nm")
done < <("$PYTHON" - <<'PYEOF'
import django
django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()
for u in User.objects.order_by("-is_owner", "email"):
    print(f"{u.email}\t{'OWNER' if u.is_owner else '-'}\t{u.get_full_name() or ''}")
PYEOF
)

COUNT=${#EMAILS[@]}
[ "$COUNT" -gt 0 ] || { echo "No hay usuarios en la base de datos."; exit 0; }

echo "Usuarios registrados:"
i=0
while [ "$i" -lt "$COUNT" ]; do
  tag=""; [ "${OWNER[$i]}" = "OWNER" ] && tag="  [OWNER]"
  nm=""; [ -n "${NAMES[$i]}" ] && nm="  — ${NAMES[$i]}"
  printf "  %2d) %s%s%s\n" "$((i + 1))" "${EMAILS[$i]}" "$tag" "$nm"
  i=$((i + 1))
done

# --- Selección por número ---------------------------------------------------
read -r -p "Número del usuario a eliminar (0 para cancelar): " NUM
case "$NUM" in
  ''|*[!0-9]*) echo "Entrada inválida. Cancelado."; exit 1 ;;
esac
[ "$NUM" = "0" ] && { echo "Cancelado."; exit 0; }
if [ "$NUM" -lt 1 ] || [ "$NUM" -gt "$COUNT" ]; then
  echo "Número fuera de rango (1–$COUNT). Cancelado."; exit 1
fi
EMAIL="${EMAILS[$((NUM - 1))]}"
export DEL_EMAIL="$EMAIL"

# --- Fase A: inspección + salvaguarda (exit 4 = único Owner) ----------------
rc=0
"$PYTHON" - <<'PYEOF' || rc=$?
import os
import django

django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ["DEL_EMAIL"]
u = User.objects.get(email__iexact=email)
owners = User.objects.filter(is_owner=True).count()
print("")
print("Se eliminará el usuario:")
print(f"   email      : {u.email}")
print(f"   is_owner   : {u.is_owner}   activo: {u.is_active}   membresías: {u.memberships.count()}")
print("   (sus certificados y grupos creados SE CONSERVAN; created_by quedará en NULL)")
if u.is_owner and owners <= 1:
    print("\nSALVAGUARDA: es el ÚNICO Owner. Eliminarlo dejaría la app sin administrador.")
    raise SystemExit(4)
PYEOF

if [ "$rc" = "4" ]; then
  if [ "${FORCE:-0}" = "1" ]; then
    echo ">> FORCE=1: se omite la salvaguarda del único Owner."
  else
    echo ">> Cancelado. Crea otro Owner antes (./owner.sh) o usa FORCE=1 para forzar." >&2
    exit 1
  fi
elif [ "$rc" != "0" ]; then
  echo "ERROR inesperado durante la inspección (rc=$rc)." >&2; exit "$rc"
fi

# --- Confirmación (salvo FORCE=1) -------------------------------------------
if [ "${FORCE:-0}" != "1" ]; then
  read -r -p "¿Eliminar definitivamente a $EMAIL? escribe 'si' para confirmar: " CONFIRM
  case "$CONFIRM" in
    si|SI|Si|s|S) : ;;
    *) echo ">> Cancelado (no se borró nada)."; exit 1 ;;
  esac
fi

# --- Fase B: borrado --------------------------------------------------------
"$PYTHON" - <<'PYEOF'
import os
import django

django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ["DEL_EMAIL"]
u = User.objects.get(email__iexact=email)
total, detail = u.delete()
print(f">> Eliminado: {email}. Objetos borrados: {total}")
for model, n in sorted(detail.items()):
    print(f"     {model}: {n}")
PYEOF

echo ">> Listo."
