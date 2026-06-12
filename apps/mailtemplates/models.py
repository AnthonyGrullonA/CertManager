"""Plantillas de correo (uso global; edición Owner/Admin/creador).

Una ``EmailTemplate`` describe el asunto y un cuerpo por BLOQUES (salida del
builder, en ``blocks`` JSON) para dos propósitos (``kind``): correos de
certificado (monitoreo/alerta) y correos de reporte. Cualquier usuario
autenticado puede ver y adjuntar plantillas; sólo Owner, un Admin de grupo o el
``created_by`` puede editarlas/borrarlas (ver ``permissions.can_edit_template``).

``team`` es sólo una ETIQUETA organizativa (no controla acceso). Los campos de
datos obligatorios del tipo deben estar presentes en ``blocks`` (``clean``).
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.enums import TemplateKind
from apps.core.models import TimeStampedModel

from .managers import EmailTemplateManager
from .variables import mandatory_fields


class EmailTemplate(TimeStampedModel):
    name = models.CharField("Nombre", max_length=120)
    kind = models.CharField("Tipo", max_length=8, choices=TemplateKind.choices)
    team = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_templates",
        help_text="Etiqueta organizativa opcional (no controla acceso).",
    )
    subject = models.CharField("Asunto", max_length=255)
    blocks = models.JSONField("Bloques", default=list, blank=True)
    is_default = models.BooleanField("Predeterminada", default=False)
    is_active = models.BooleanField("Activa", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_templates_created",
    )

    objects = EmailTemplateManager()

    class Meta:
        verbose_name = "Plantilla de correo"
        verbose_name_plural = "Plantillas de correo"
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    def clean(self):
        present = {
            b.get("field")
            for b in (self.blocks or [])
            if isinstance(b, dict) and b.get("type") == "data"
        }
        missing = mandatory_fields(self.kind) - present
        if missing:
            # Error de modelo (no de campo): "blocks" no es un campo del form del
            # builder, así que se reporta como error general.
            raise ValidationError(
                "Faltan campos de datos obligatorios: " + ", ".join(sorted(missing))
            )

    def save(self, *args, **kwargs):
        # Un único predeterminado por tipo (el último marcado gana).
        if self.is_default:
            EmailTemplate.objects.filter(kind=self.kind, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)
