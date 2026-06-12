"""Genera y envía por correo los reportes programados que tocan hoy.

Pensado para correr por cron (MVP síncrono; Celery beat diferido):

    # cada hora, en punto
    0 * * * *  cd /app && python manage.py send_scheduled_reports

Recurrencia (``dateutil.rrule``):
- ``DAILY`` / ``WEEKLY`` / ``MONTHLY``: como antes (ancla = fecha de creación).
- ``EVERY_N_DAYS``: cada ``interval_days`` días a partir de ``start_date``.
- ``MONTHLY_DAY_1``: el día 1 de cada mes.

Días hábiles: si la fecha que toca cae **sábado o domingo**, el envío se difiere
al **lunes** siguiente (solo se envía de lunes a viernes).

Idempotente: no reenvía un reporte ya ejecutado en su ocurrencia (``last_run_at``).

Opciones: ``--force`` (ignora el "vencido"), ``--dry-run``, ``--id <pk>``.
"""
from datetime import datetime, time, timedelta

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, rrule
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.enums import CertificateStatus, ReportFrequency
from apps.core.mail import default_from_email, global_bcc, smtp_connection
from apps.reports.models import ScheduledReport
from apps.reports.services import ReportFilters, build_export, build_report

WEEKEND = {5, 6}  # sábado=5, domingo=6


def shift_weekend(d):
    """Difiere una fecha de fin de semana al lunes (lun–vie se mantienen)."""
    wd = d.weekday()
    if wd == 5:
        return d + timedelta(days=2)
    if wd == 6:
        return d + timedelta(days=1)
    return d


def _anchor(report):
    """Fecha ancla de la recurrencia: start_date o la fecha de creación."""
    if report.start_date:
        return report.start_date
    return timezone.localtime(report.created_at).date()


def _nominal_rule(report, anchor):
    """Regla rrule (sin ajuste de fin de semana) según la frecuencia."""
    dtstart = datetime.combine(anchor, time.min)
    freq = report.frequency
    if freq == ReportFrequency.EVERY_N_DAYS:
        return rrule(DAILY, interval=max(1, report.interval_days or 1), dtstart=dtstart)
    if freq == ReportFrequency.MONTHLY_DAY_1:
        return rrule(MONTHLY, bymonthday=1, dtstart=dtstart)
    if freq == ReportFrequency.WEEKLY:
        return rrule(WEEKLY, dtstart=dtstart)
    if freq == ReportFrequency.MONTHLY:
        return rrule(MONTHLY, dtstart=dtstart)
    # DAILY (y cualquier valor desconocido): a diario.
    return rrule(DAILY, dtstart=dtstart)


def _effective_due_today(report, today):
    """¿Hoy es una ocurrencia efectiva (tras el ajuste de fin de semana)?

    Miramos las ocurrencias nominales de una ventana corta alrededor de hoy
    (el salto de fin de semana es como mucho +2 días) y comprobamos si alguna,
    desplazada a día hábil, cae exactamente hoy.
    """
    anchor = _anchor(report)
    if today < anchor:
        return False
    rule = _nominal_rule(report, anchor)
    window_start = datetime.combine(today - timedelta(days=3), time.min)
    window_end = datetime.combine(today, time.max)
    for occ in rule.between(window_start, window_end, inc=True):
        if shift_weekend(occ.date()) == today:
            return True
    return False


def is_due(report, now):
    """¿El reporte debe enviarse ahora?"""
    local = timezone.localtime(now)
    today = local.date()
    if report.send_time and local.time() < report.send_time:
        return False
    if not _effective_due_today(report, today):
        return False
    last = report.last_run_at
    if last is None:
        return True
    return timezone.localtime(last).date() < today


def _filters_for(report):
    """Construye ReportFilters desde el JSON guardado del reporte."""
    f = report.filters or {}
    teams = []
    for raw in f.get("teams", []):
        try:
            teams.append(int(raw))
        except (TypeError, ValueError):
            continue
    statuses = [s for s in f.get("statuses", []) if s in CertificateStatus.values]
    return ReportFilters(
        template=(report.template or f.get("template") or "INVENTORY"),
        date_range=str(f.get("date_range", "30")),
        teams=teams,
        statuses=statuses,
        expiry_window=str(f.get("expiry_window", "")),
        issuer=f.get("issuer", ""),
        recipient=f.get("recipient", ""),
    )


def generate_and_send(report, recipients, *, now=None, connection=None):
    """Genera el/los formato(s) del reporte y los envía por correo.

    Reutilizable por el cron y por la acción "Enviar prueba" de la UI. Devuelve
    el ``ReportResult`` generado. Lanza si el envío falla.
    """
    now = now or timezone.now()
    filters = _filters_for(report)
    result = build_report(report.created_by, filters)
    formats = report.formats or [report.output_format]
    content, content_type, filename = build_export(result, formats)

    default_subject = f"CertManager — {report.name}"
    default_body = (
        f"Adjunto el reporte programado '{report.name}'.\n"
        f"Generado: {timezone.localtime(now):%d/%m/%Y %H:%M}."
    )

    # Plantilla atada al reporte (o la predeterminada del tipo). Sin plantilla =>
    # cuerpo de texto plano actual. El adjunto se conserva en ambos casos.
    from apps.mailtemplates.render import render_email, resolve_template
    from apps.mailtemplates.variables import report_context

    tpl = resolve_template(getattr(report, "email_template", None), "REPORT")
    rendered = render_email(tpl, report_context(report, result)) if tpl else None

    if rendered is not None:
        from django.core.mail import EmailMultiAlternatives

        msg = EmailMultiAlternatives(
            subject=rendered.subject or default_subject,
            body=rendered.text,
            from_email=default_from_email(),
            to=list(recipients),
            bcc=global_bcc(exclude=recipients),
            connection=connection,
        )
        msg.attach_alternative(rendered.html, "text/html")
    else:
        msg = EmailMessage(
            subject=default_subject,
            body=default_body,
            from_email=default_from_email(),
            to=list(recipients),
            bcc=global_bcc(exclude=recipients),
            connection=connection,
        )
    msg.attach(filename, content, content_type)
    msg.send(fail_silently=False)
    return result


class Command(BaseCommand):
    help = "Genera y envía por correo los reportes programados que tocan hoy."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Ignora la comprobación de vencimiento.")
        parser.add_argument("--dry-run", action="store_true", help="No envía ni marca last_run_at.")
        parser.add_argument("--id", type=int, help="Limita a un reporte programado por ID.")

    def handle(self, *args, **options):
        now = timezone.now()
        qs = ScheduledReport.objects.filter(is_active=True).select_related("created_by", "team")
        if options.get("id"):
            qs = qs.filter(pk=options["id"])

        sent = skipped = errors = 0
        connection = None if options["dry_run"] else smtp_connection()

        for report in qs:
            if not options["force"] and not is_due(report, now):
                skipped += 1
                continue

            recipients = [r for r in (report.recipients or []) if r]
            if not recipients:
                self.stdout.write(self.style.WARNING(f"  '{report.name}': sin destinatarios, omitido."))
                skipped += 1
                continue

            try:
                if options["dry_run"]:
                    filters = _filters_for(report)
                    result = build_report(report.created_by, filters)
                    self.stdout.write(
                        f"  (dry-run) '{report.name}' → {result.total} certs a {', '.join(recipients)}"
                    )
                    sent += 1
                    continue

                generate_and_send(report, recipients, now=now, connection=connection)
                report.last_run_at = now
                report.save(update_fields=["last_run_at", "updated_at"])
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ '{report.name}' enviado a {len(recipients)} destinatario(s)."))
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self.stdout.write(self.style.ERROR(f"  ✗ '{report.name}': {exc}"))

        self.stdout.write(f"Listo. {sent} enviados, {skipped} omitidos, {errors} con error.")
