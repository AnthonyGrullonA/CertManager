"""Reportes programados que se envían por correo periódicamente."""
from django.conf import settings
from django.db import models

from apps.core.enums import ReportFormat, ReportFrequency, ReportTemplate
from apps.core.models import TimeStampedModel
from apps.teams.models import Team


class ScheduledReport(TimeStampedModel):
    """Definición de un reporte recurrente (plantilla + filtros + frecuencia + destino)."""

    name = models.CharField("Nombre", max_length=160)
    template = models.CharField("Plantilla", max_length=15, choices=ReportTemplate.choices)
    filters = models.JSONField(
        "Filtros",
        default=dict,
        blank=True,
        help_text="Filtros del reporte (grupo, estado, ventana de vencimiento, etc.).",
    )
    frequency = models.CharField("Frecuencia", max_length=15, choices=ReportFrequency.choices)
    # Multi-formato: se CONSERVA `output_format` (formato principal/compatibilidad)
    # y se añade `formats`, lista de formatos a generar simultáneamente
    # (PDF+Excel+CSV, decisión congelada nº 6 del plan). Cuando `formats` está
    # vacío se asume [output_format]. Valores válidos: ReportFormat.values.
    output_format = models.CharField("Formato principal", max_length=10, choices=ReportFormat.choices, default=ReportFormat.PDF)
    formats = models.JSONField(
        "Formatos a generar",
        default=list,
        blank=True,
        help_text="Lista de formatos simultáneos (PDF/EXCEL/CSV). Vacío = solo el formato principal.",
    )
    send_time = models.TimeField("Hora de envío", null=True, blank=True)
    # Programación por calendario (frequency EVERY_N_DAYS / MONTHLY_DAY_1):
    # `start_date` ancla la recurrencia; `interval_days` es el N de "cada N días".
    start_date = models.DateField(
        "Fecha de inicio", null=True, blank=True,
        help_text="Ancla de la recurrencia. Para 'cada N días' la cuenta arranca aquí.",
    )
    interval_days = models.PositiveIntegerField(
        "Intervalo (días)", null=True, blank=True,
        help_text="Solo para 'Cada N días' (p.ej. 15 o 30).",
    )
    recipients = models.JSONField("Destinatarios", default=list, blank=True)

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="scheduled_reports",
        help_text="Vacío = todos los grupos (solo Owner).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_created",
    )
    is_active = models.BooleanField("Activo", default=True)
    last_run_at = models.DateTimeField("Última ejecución", null=True, blank=True)
    # Plantilla de correo (kind=REPORT) para el envío. Null => default del tipo o
    # el cuerpo de texto plano actual.
    email_template = models.ForeignKey(
        "mailtemplates.EmailTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Reporte programado"
        verbose_name_plural = "Reportes programados"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"
