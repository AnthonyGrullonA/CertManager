#!/usr/bin/env bash
# =============================================================================
# owner.sh — Crea (o actualiza) usuarios Owner de CertManager.
#
#   Un Owner tiene acceso total (gestiona grupos, usuarios, certificados y
#   configuración de toda la organización). Es Owner de la APP, no superusuario
#   del admin de Django (is_owner=True, is_staff/is_superuser=False).
#
#   Idempotente: si el email ya existe, lo marca como Owner y (si das contraseña)
#   se la actualiza. Apunta a la MISMA base de datos del despliegue cargando
#   .env.preprod (el que generan levantamiento.sh / install_server.sh).
#
# Uso:
#   ./owner.sh                          # pregunta email y contraseña
#   ./owner.sh ana@claro.com.do         # un owner (pregunta su contraseña)
#   ./owner.sh ana@x.do beto@x.do       # varios (pregunta la contraseña de c/u)
#   CF_OWNER_PASSWORD=xxxx ./owner.sh ana@x.do   # sin prompt (misma clave a todos)
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR="$(pwd)"
VENV="${VENV:-$APP_DIR/.venv}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.preprod}"

# Python: usa el venv del despliegue si existe; si no, python3 del sistema.
if [ -x "$VENV/bin/python" ]; then PYTHON="$VENV/bin/python"; else PYTHON="${PYTHON:-python3}"; fi

# Carga el entorno del despliegue (apunta a la BD correcta: CERTFORGE_DATA_DIR,
# DATABASE_URL, DJANGO_SETTINGS_MODULE…). Prioridad: .env.preprod > CLARO_NECESIDAD/.env.
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
elif [ -f "CLARO_NECESIDAD/.env" ]; then
  set -a; . "CLARO_NECESIDAD/.env"; set +a
fi
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.standalone}"
# Tarea de un solo uso: nunca levantar el scheduler en-proceso (lo arrancaría el
# perfil standalone por defecto al hacer django.setup()).
export RUN_SCHEDULER=False

# --- Reúne los emails (de los argumentos o preguntando uno) -----------------
emails=("$@")
if [ "${#emails[@]}" -eq 0 ]; then
  read -r -p "Email del Owner: " _e
  emails=("$_e")
fi

# --- Reúne la contraseña de cada uno (CF_OWNER_PASSWORD aplica a todos) ------
i=0
for email in "${emails[@]}"; do
  case "$email" in
    *@*.*) : ;;  # validación mínima: algo@dominio.tld
    *) echo "ERROR: '$email' no parece un email válido." >&2; exit 1 ;;
  esac
  if [ -n "${CF_OWNER_PASSWORD:-}" ]; then
    pw="$CF_OWNER_PASSWORD"
  else
    pw=""; pw2="x"
    while [ -z "$pw" ] || [ "$pw" != "$pw2" ]; do
      read -r -s -p "Contraseña para $email: " pw; echo
      [ -z "$pw" ] && { echo "   La contraseña no puede estar vacía."; continue; }
      read -r -s -p "Confírmala: " pw2; echo
      [ "$pw" != "$pw2" ] && echo "   No coinciden, reintenta."
    done
  fi
  # Se pasan por ENTORNO (no por argv) para que no aparezcan en `ps`.
  export "OWNER_EMAIL_$i=$email"
  export "OWNER_PW_$i=$pw"
  i=$((i + 1))
done
export OWNER_N="$i"

# --- Crea/actualiza vía el ORM (mismo patrón que el bootstrap) --------------
"$PYTHON" - <<'PYEOF'
import os
import django

django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()
n = int(os.environ["OWNER_N"])
for i in range(n):
    email = os.environ[f"OWNER_EMAIL_{i}"].strip()
    pw = os.environ.get(f"OWNER_PW_{i}", "")
    user, created = User.objects.get_or_create(
        email=email,
        defaults={"is_owner": True, "is_staff": False, "is_superuser": False},
    )
    if not user.is_owner:
        user.is_owner = True
    if pw:
        user.set_password(pw)  # sella password_changed_at (política de expiración)
        user.save()
        print(f"Owner {'creado' if created else 'actualizado'}: {email} (contraseña fijada).")
    else:
        if created:
            user.set_unusable_password()
        user.save()
        print(f"Owner {'creado' if created else 'existente'}: {email} — SIN contraseña "
              "(exporta CF_OWNER_PASSWORD o vuelve a correr para fijarla).")
PYEOF

echo ">> Listo."
