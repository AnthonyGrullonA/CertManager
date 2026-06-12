#!/bin/sh
# Entrypoint de CertManager. Aplica migraciones + collectstatic (solo cuando
# RUN_MIGRATIONS=1, que ponemos en el servicio `web`) y arranca el comando dado.
# El servicio `scheduler` corre con RUN_MIGRATIONS=0 y depende de `web` sano, así
# no compiten por migrar.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] migrate…"
    python manage.py migrate --no-input
    echo "[entrypoint] collectstatic…"
    python manage.py collectstatic --no-input
fi

exec "$@"
