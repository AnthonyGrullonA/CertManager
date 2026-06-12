"""Vistas transversales del núcleo (health check)."""
from django.db import connection
from django.http import JsonResponse


def health(request):
    """Healthcheck sin autenticación: verifica la conexión a la BD (SELECT 1).

    Devuelve 200 si la BD responde, 503 si no. Lo usa el HEALTHCHECK de Docker y
    cualquier orquestador para saber si el contenedor está sano.
    """
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - el healthcheck nunca debe lanzar
        db_ok = False
    return JsonResponse(
        {"status": "ok" if db_ok else "degraded", "database": db_ok},
        status=200 if db_ok else 503,
    )
