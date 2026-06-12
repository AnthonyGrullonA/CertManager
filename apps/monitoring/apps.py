import os
import sys

from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.monitoring"
    label = "monitoring"
    verbose_name = "Monitoreo"

    def ready(self):
        """Auto-arranca el scheduler en el proceso web si RUN_SCHEDULER=True.

        Guardas para no arrancarlo donde no corresponde:
        - solo si el flag está activo;
        - nunca en comandos que no son el servidor (migrate, test, shell,
          run_scheduler —que arranca el suyo—, etc.);
        - con runserver --reload, solo en el proceso hijo (RUN_MAIN=true), no en
          el watcher padre (evita doble scheduler).
        """
        from django.conf import settings

        if not getattr(settings, "RUN_SCHEDULER", False):
            return

        argv = sys.argv
        blocked = {"migrate", "makemigrations", "test", "shell", "shell_plus",
                   "collectstatic", "run_scheduler", "createsuperuser", "loaddata",
                   "dumpdata", "check_certificates", "send_scheduled_reports"}
        if any(cmd in argv for cmd in blocked):
            return
        if "runserver" in argv and os.environ.get("RUN_MAIN") != "true":
            return

        from apps.monitoring.scheduler import start_background

        start_background()
