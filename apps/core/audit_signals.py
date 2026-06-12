"""Señales que alimentan el AuditLog (OWASP A09).

Se registran SOLO las mutaciones iniciadas por un usuario autenticado (hay
``current_actor()``). Las escrituras automáticas (scheduler de chequeos,
data_update_certs_app, shell, migraciones) no tienen actor de petición y se omiten, así
el log queda limpio de ruido y refleja acciones humanas auditables.

``connect()`` se llama desde ``CoreConfig.ready()`` y engancha post_save/
post_delete SOLO en los modelos auditados (no en todos los del proyecto).
"""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save

from apps.core.audit import current_actor, record


def _tracked_models():
    from apps.alerts.models import WebhookIntegration
    from apps.certificates.models import Certificate
    from apps.core.models import (
        LdapConfiguration,
        OrganizationSettings,
        SmsGatewayConfig,
    )
    from apps.mailtemplates.models import EmailTemplate
    from apps.reports.models import ScheduledReport
    from apps.teams.models import Membership, Team

    return [
        Certificate, Team, Membership, EmailTemplate, ScheduledReport,
        WebhookIntegration, SmsGatewayConfig, OrganizationSettings,
        LdapConfiguration,
    ]


def _on_save(sender, instance, created, **kwargs):
    if current_actor() is None:
        return
    record(
        "create" if created else "update",
        model=instance._meta.model_name,
        object_id=getattr(instance, "pk", ""),
        object_repr=str(instance),
    )


def _on_delete(sender, instance, **kwargs):
    if current_actor() is None:
        return
    record(
        "delete",
        model=instance._meta.model_name,
        object_id=getattr(instance, "pk", ""),
        object_repr=str(instance),
    )


def connect():
    for model in _tracked_models():
        uid = f"audit_{model._meta.label_lower}"
        post_save.connect(_on_save, sender=model, dispatch_uid=uid + "_save", weak=False)
        post_delete.connect(_on_delete, sender=model, dispatch_uid=uid + "_del", weak=False)
