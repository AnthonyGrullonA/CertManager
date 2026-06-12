"""Planificador en-proceso (APScheduler) para CertManager.

Dispara los comandos de monitoreo/reportes en intervalos, SIN depender de cron del
sistema ni de Celery (que está diferido). Dos formas de uso:

- ``python manage.py run_scheduler`` → proceso dedicado (BlockingScheduler).
- ``RUN_SCHEDULER=True`` → arranca en background dentro del proceso web
  (runserver/gunicorn) vía ``MonitoringConfig.ready``.

Cada job corre ``call_command`` aislando errores (un fallo no tumba el scheduler)
y cerrando conexiones viejas (los jobs corren en hilos aparte).
"""
from __future__ import annotations

import logging
import os
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections

logger = logging.getLogger("certmanager.scheduler")

# Evita doble arranque dentro del MISMO proceso (p.ej. ready() llamado dos veces).
_started = False
# Mantiene vivo el lock entre procesos (si se cierra, se libera el flock).
_lock_handle = None


def _acquire_singleton_lock() -> bool:
    """Lock exclusivo entre procesos para que el scheduler corra UNA sola vez.

    Con RUN_SCHEDULER y varios workers de gunicorn, cada worker ejecuta ready();
    sin esto, los jobs se dispararían N veces. El primer worker toma el flock; los
    demás lo encuentran tomado y NO arrancan su scheduler. POSIX-only (contenedores
    Linux/Mac); si fcntl no está, degradamos al guard por-proceso (_started).
    """
    global _lock_handle
    try:
        import fcntl
    except ImportError:  # p.ej. Windows: sin lock entre procesos
        return True
    path = os.path.join(tempfile.gettempdir(), "certforge-scheduler.lock")
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _lock_handle = handle  # se conserva para no liberar el lock
    return True


def _run(command: str):
    """Ejecuta un management command de forma segura para un hilo del scheduler."""
    close_old_connections()
    try:
        logger.info("scheduler: ejecutando %s", command)
        call_command(command)
    except Exception:  # noqa: BLE001
        logger.exception("scheduler: fallo en %s", command)
    finally:
        close_old_connections()


def _org_settings():
    """OrganizationSettings.load() o None (fail-safe ante BD no lista)."""
    try:
        from apps.core.models import OrganizationSettings

        return OrganizationSettings.load()
    except Exception:  # noqa: BLE001
        return None


def _check_window_start():
    """Hora de inicio de la ventana de chequeo (OrganizationSettings) o None.

    Fail-safe: ante cualquier error (BD no lista, etc.) devuelve None y el chequeo
    cae al modo intervalo.
    """
    org = _org_settings()
    return org.preferred_check_window_start if org else None


def _check_interval_hours():
    """Frecuencia de chequeo (Configuración → Monitoreo) o el default de settings."""
    org = _org_settings()
    if org and org.check_interval_hours and org.check_interval_hours > 0:
        return org.check_interval_hours
    return settings.SCHEDULER["CERT_CHECK_HOURS"]


def _build(scheduler):
    cfg = settings.SCHEDULER
    tz = getattr(settings, "TIME_ZONE", "UTC")
    # Chequeo de certificados: si hay ventana horaria preferida, se agenda como un
    # CRON diario a la hora de inicio (los chequeos masivos corren en horario valle,
    # p.ej. 02:00). Sin ventana, corre por INTERVALO (SCHEDULER.CERT_CHECK_HOURS).
    window_start = _check_window_start()
    if window_start is not None:
        scheduler.add_job(
            _run, "cron", args=["check_certificates"],
            hour=window_start.hour, minute=window_start.minute,
            id="check_certificates", max_instances=1, coalesce=True,
            replace_existing=True, timezone=tz,
        )
    else:
        scheduler.add_job(
            _run, "interval", args=["check_certificates"],
            hours=_check_interval_hours(), id="check_certificates",
            max_instances=1, coalesce=True, replace_existing=True, timezone=tz,
        )
    scheduler.add_job(
        _run, "interval", args=["send_scheduled_reports"],
        minutes=cfg["REPORTS_MINUTES"], id="send_scheduled_reports",
        max_instances=1, coalesce=True, replace_existing=True, timezone=tz,
    )
    backup_hours = cfg.get("BACKUP_HOURS", 0)
    if backup_hours and backup_hours > 0:
        scheduler.add_job(
            _run, "interval", args=["backup_db"],
            hours=backup_hours, id="backup_db",
            max_instances=1, coalesce=True, replace_existing=True, timezone=tz,
        )
    return scheduler


def start_background():
    """Arranca un BackgroundScheduler (hilos) dentro del proceso actual.

    Idempotente por proceso (_started) y singleton entre procesos (flock): si otro
    worker de gunicorn ya tomó el scheduler, este no arranca (evita jobs duplicados).
    """
    global _started
    if _started:
        return None
    if not _acquire_singleton_lock():
        logger.info("scheduler: ya hay otro proceso ejecutándolo; este no arranca.")
        _started = True  # no reintentar en este proceso
        return None
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = _build(BackgroundScheduler(timezone=getattr(settings, "TIME_ZONE", "UTC")))
    scheduler.start()
    _started = True
    logger.info(
        "scheduler: background iniciado (certs cada %sh, reportes cada %smin)",
        settings.SCHEDULER["CERT_CHECK_HOURS"], settings.SCHEDULER["REPORTS_MINUTES"],
    )
    return scheduler


def run_blocking():
    """Arranca un BlockingScheduler (para el comando dedicado run_scheduler)."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = _build(BlockingScheduler(timezone=getattr(settings, "TIME_ZONE", "UTC")))
    logger.info(
        "scheduler: bloqueante iniciado (certs cada %sh, reportes cada %smin)",
        settings.SCHEDULER["CERT_CHECK_HOURS"], settings.SCHEDULER["REPORTS_MINUTES"],
    )
    scheduler.start()  # bloquea
