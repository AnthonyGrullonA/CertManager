"""Alertas, sus envíos por canal e integraciones webhook."""
from django.conf import settings
from django.db import models

from apps.certificates.models import Certificate
from apps.core.enums import (
    AlertSeverity,
    AlertStatus,
    DeliveryStatus,
    NotificationChannel,
    WebhookType,
)
from apps.core.models import TimeStampedModel
from apps.teams.models import Team


class Alert(TimeStampedModel):
    """Evento de alerta sobre un certificado (por vencer / crítico / vencido / error)."""

    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    severity = models.CharField("Severidad", max_length=15, choices=AlertSeverity.choices)
    status = models.CharField(
        "Estado",
        max_length=10,
        choices=AlertStatus.choices,
        default=AlertStatus.OPEN,
    )
    message = models.CharField("Mensaje", max_length=500)

    # DEPRECADO: el estado personal "leída" migró a AlertUserState.read_at.
    # Se conserva la columna para reversibilidad de la migración de datos; ya no
    # se escribe desde la aplicación. Eliminar en una etapa posterior.
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="read_alerts",
        blank=True,
    )
    resolved_at = models.DateTimeField("Resuelta", null=True, blank=True)
    snoozed_until = models.DateTimeField("Pospuesta hasta", null=True, blank=True)

    class Meta:
        verbose_name = "Alerta"
        verbose_name_plural = "Alertas"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "severity"]),
        ]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.certificate}"


class AlertUserState(TimeStampedModel):
    """Estado personal de un usuario frente a una alerta (compartida).

    Separa el evento compartido (`Alert`, fuente de verdad, nunca se borra) del
    estado por usuario: `read_at` (resaltado de no-leídas) y `dismissed_at`
    ('limpiada' del panel, presentación, nunca borra el registro histórico).
    """

    alert = models.ForeignKey(
        Alert,
        on_delete=models.CASCADE,
        related_name="user_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alert_states",
    )
    read_at = models.DateTimeField("Leída", null=True, blank=True)
    dismissed_at = models.DateTimeField("Limpiada del panel", null=True, blank=True)

    class Meta:
        verbose_name = "Estado de alerta por usuario"
        verbose_name_plural = "Estados de alerta por usuario"
        constraints = [
            models.UniqueConstraint(
                fields=["alert", "user"],
                name="unique_alert_user_state",
            ),
        ]

    def __str__(self):
        return f"{self.user} · {self.alert} (read={self.read_at is not None})"


class AlertDelivery(TimeStampedModel):
    """Intento de envío de una alerta por un canal concreto."""

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField("Canal", max_length=10, choices=NotificationChannel.choices)
    target = models.CharField("Destino", max_length=500, blank=True)  # correo o URL
    status = models.CharField(
        "Estado",
        max_length=10,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )
    sent_at = models.DateTimeField("Enviada", null=True, blank=True)
    error = models.TextField("Error", blank=True)

    class Meta:
        verbose_name = "Envío de alerta"
        verbose_name_plural = "Envíos de alerta"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_channel_display()} → {self.target} ({self.get_status_display()})"


class WebhookIntegration(TimeStampedModel):
    """Webhook de destino para alertas (Teams/Slack/genérico). Global o por grupo."""

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="webhooks",
        help_text="Vacío = integración global (todos los grupos).",
    )
    webhook_type = models.CharField("Tipo", max_length=10, choices=WebhookType.choices)
    name = models.CharField("Nombre", max_length=120)
    url = models.URLField("URL del webhook", max_length=500)
    is_active = models.BooleanField("Activo", default=True)
    rich_format = models.BooleanField(
        "Formato enriquecido",
        default=False,
        help_text="Envía tarjetas/bloques con formato (Teams/Slack) en vez de texto plano.",
    )

    class Meta:
        verbose_name = "Integración webhook"
        verbose_name_plural = "Integraciones webhook"

    def __str__(self):
        scope = self.team.name if self.team else "Global"
        return f"{self.name} ({self.get_webhook_type_display()} · {scope})"
