"""Corre el planificador en-proceso (APScheduler) como proceso dedicado.

Uso (local o producción):

    python manage.py run_scheduler

Bloquea el proceso y dispara periódicamente ``check_certificates`` (cada
SCHEDULER.CERT_CHECK_HOURS) y ``send_scheduled_reports`` (cada
SCHEDULER.REPORTS_MINUTES). Es la forma recomendada en producción (un único
proceso, sin riesgo de duplicados entre workers de gunicorn).
"""
from django.core.management.base import BaseCommand

from apps.monitoring.scheduler import run_blocking


class Command(BaseCommand):
    help = "Corre el planificador (monitoreo de certificados + reportes) en bucle."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Scheduler iniciado. Ctrl+C para detener."))
        try:
            run_blocking()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write("Scheduler detenido.")
