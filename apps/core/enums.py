"""Enumeraciones compartidas en todo CertManager.

Los estados de certificado están alineados con la paleta de Forge UI (ui.md).
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class ApiKeyScope(models.TextChoices):
    FULL = "full", _("Acceso total (lectura y escritura)")
    READ_ONLY = "read_only", _("Solo lectura")


class CertificateStatus(models.TextChoices):
    VIGENTE = "VIGENTE", _("Vigente")            # días restantes >= umbral
    POR_VENCER = "POR_VENCER", _("Por vencer")   # 0 <= días < umbral
    CRITICO = "CRITICO", _("Crítico")            # días < umbral crítico
    VENCIDO = "VENCIDO", _("Vencido")            # días < 0
    ERROR = "ERROR", _("Error")                  # no conecta / no verifica
    SIN_CHEQUEAR = "SIN_CHEQUEAR", _("Sin chequear")  # nunca evaluado


class MembershipRole(models.TextChoices):
    VIEWER = "VIEWER", _("Visualizador")           # ve certs + genera/recibe reportes
    CONTRIBUTOR = "CONTRIBUTOR", _("Colaborador")  # + crea/edita/borra certs en sus grupos
    ADMIN = "ADMIN", _("Admin de grupo")           # + plantillas, miembros, alertas compartidas


class TemplateKind(models.TextChoices):
    CERT = "CERT", _("Certificado (monitoreo)")
    REPORT = "REPORT", _("Reporte")


class BlockType(models.TextChoices):
    HEADING = "heading", _("Encabezado")
    TEXT = "text", _("Texto")
    DATA = "data", _("Campo de dato")
    BUTTON = "button", _("Botón/enlace")
    DIVIDER = "divider", _("Separador")
    SPACER = "spacer", _("Espaciador")
    FOOTER = "footer", _("Pie")
    LOGO = "logo", _("Logo")


class AlertSeverity(models.TextChoices):
    POR_VENCER = "POR_VENCER", _("Por vencer")
    CRITICO = "CRITICO", _("Crítico")
    VENCIDO = "VENCIDO", _("Vencido")
    ERROR = "ERROR", _("Error")


class AlertStatus(models.TextChoices):
    OPEN = "OPEN", _("Abierta")
    RESOLVED = "RESOLVED", _("Resuelta")
    SNOOZED = "SNOOZED", _("Pospuesta")


class NotificationChannel(models.TextChoices):
    PLATFORM = "PLATFORM", _("Plataforma")
    EMAIL = "EMAIL", _("Correo")
    WEBHOOK = "WEBHOOK", _("Webhook")
    SMS = "SMS", _("SMS")


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", _("Pendiente")
    SENT = "SENT", _("Enviada")
    FAILED = "FAILED", _("Fallida")


class WebhookType(models.TextChoices):
    TEAMS = "TEAMS", _("Microsoft Teams")
    SLACK = "SLACK", _("Slack")
    GENERIC = "GENERIC", _("Genérico")


class ReportTemplate(models.TextChoices):
    INVENTORY = "INVENTORY", _("Inventario de certificados")
    EXPIRING = "EXPIRING", _("Próximos a vencer")
    EXPIRED = "EXPIRED", _("Vencidos / con error")
    HISTORY = "HISTORY", _("Historial de chequeos")
    BY_GROUP = "BY_GROUP", _("Resumen por grupo")


class ReportFrequency(models.TextChoices):
    DAILY = "DAILY", _("Diario")
    WEEKLY = "WEEKLY", _("Semanal")
    MONTHLY = "MONTHLY", _("Mensual")
    EVERY_N_DAYS = "EVERY_N_DAYS", _("Cada N días (desde una fecha)")
    MONTHLY_DAY_1 = "MONTHLY_DAY_1", _("El día 1 de cada mes")


class ReportFormat(models.TextChoices):
    PDF = "PDF", _("PDF")
    EXCEL = "EXCEL", _("Excel")
    CSV = "CSV", _("CSV")
