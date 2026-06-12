"""Chequea los certificados activos y genera alertas.

Reemplazo del bucle de `certapp_old/valida.py`. Pensado para correr por cron:

    0 6 * * *  cd /app && python manage.py check_certificates

Opciones:
    --team <slug|id>   limita a un grupo
    --domain <texto>   limita a dominios que contengan el texto
    --dry-run          chequea sin generar/enviar alertas
"""
from django.core.management.base import BaseCommand

from apps.certificates.models import Certificate
from apps.monitoring.runner import run_check


class Command(BaseCommand):
    help = "Chequea el vencimiento de los certificados activos y dispara alertas."

    def add_arguments(self, parser):
        parser.add_argument("--team", help="Slug o ID del grupo a chequear.")
        parser.add_argument("--domain", help="Filtra por subcadena del dominio.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No genera ni envía alertas (solo chequea y persiste el resultado).",
        )

    def handle(self, *args, **options):
        qs = Certificate.objects.filter(is_active=True).select_related("team")

        if options.get("team"):
            team = options["team"]
            if team.isdigit():
                qs = qs.filter(team_id=int(team))
            else:
                qs = qs.filter(team__slug=team)
        if options.get("domain"):
            qs = qs.filter(domain__icontains=options["domain"])

        notify = not options["dry_run"]
        total = qs.count()
        self.stdout.write(f"Chequeando {total} certificado(s)…")

        ok = errors = 0
        for cert in qs.iterator():
            _, result = run_check(cert, notify=notify)
            if result.ok:
                ok += 1
                self.stdout.write(
                    f"  ✓ {cert.domain}:{cert.port} → {result.status} "
                    f"({result.days_left} días)"
                )
            else:
                errors += 1
                self.stdout.write(self.style.WARNING(
                    f"  ✗ {cert.domain}:{cert.port} → {result.error_message}"
                ))

        msg = f"Listo. {ok} ok, {errors} con error de {total}."
        self.stdout.write(self.style.SUCCESS(msg) if not errors else msg)
