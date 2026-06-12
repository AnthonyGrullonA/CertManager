"""Evaluación de alertas y notificadores (plataforma / correo / webhook).

`evaluate_alert(certificate, result)` se llama tras cada chequeo:
- estado saludable  -> resuelve alertas abiertas
- estado de riesgo  -> asegura una alerta abierta y dispara los envíos por los
  canales efectivos del certificado.

Los envíos son tolerantes a fallos: cada intento registra un AlertDelivery con su
estado (SENT/FAILED) y nunca interrumpe el ciclo de chequeo.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.core.enums import (
    AlertSeverity,
    AlertStatus,
    CertificateStatus,
    DeliveryStatus,
    NotificationChannel,
)

from .models import Alert, AlertDelivery, WebhookIntegration

logger = logging.getLogger("certmanager.alerts")

# Estados de certificado que ameritan alerta y su severidad equivalente.
RISK_STATUS_TO_SEVERITY = {
    CertificateStatus.POR_VENCER: AlertSeverity.POR_VENCER,
    CertificateStatus.CRITICO: AlertSeverity.CRITICO,
    CertificateStatus.VENCIDO: AlertSeverity.VENCIDO,
    CertificateStatus.ERROR: AlertSeverity.ERROR,
}

# Orden de gravedad para detectar "escalada" (por vencer → crítico/vencido).
_SEVERITY_RANK = {
    AlertSeverity.POR_VENCER: 1,
    AlertSeverity.ERROR: 2,
    AlertSeverity.CRITICO: 2,
    AlertSeverity.VENCIDO: 3,
}


def _due_for_renotify(alert) -> bool:
    """¿Toca re-notificar por tiempo? (último envío más viejo que N días)."""
    days = getattr(settings, "ALERT_RENOTIFY_DAYS", 7)
    if days <= 0:
        return True  # 0 o negativo = re-notifica siempre (comportamiento previo)
    last = alert.deliveries.order_by("-created_at").first()
    if last is None:
        return True
    return last.created_at <= timezone.now() - timedelta(days=days)


def evaluate_alert(certificate, result):
    """Crea/actualiza o resuelve alertas según el resultado del chequeo."""
    severity = RISK_STATUS_TO_SEVERITY.get(result.status)

    if severity is None:
        # Estado saludable -> cerrar pendientes.
        certificate.alerts.filter(status=AlertStatus.OPEN).update(
            status=AlertStatus.RESOLVED, resolved_at=timezone.now()
        )
        return None

    message = _build_message(certificate, result)

    alert = certificate.alerts.filter(status=AlertStatus.OPEN).first()
    if alert:
        # Ya hay una alerta abierta: solo re-notificamos si ESCALA de nivel
        # (por vencer→crítico→vencido) o si pasaron N días desde el último envío.
        escalated = _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(alert.severity, 0)
        alert.severity = severity
        alert.message = message
        alert.save(update_fields=["severity", "message", "updated_at"])
        should_notify = escalated or _due_for_renotify(alert)
    else:
        alert = Alert.objects.create(
            certificate=certificate,
            severity=severity,
            status=AlertStatus.OPEN,
            message=message,
        )
        should_notify = True  # alerta nueva: siempre notifica

    # Snooze: si el certificado está silenciado, la alerta se registra/actualiza
    # pero NO se notifica (correo/webhook/SMS/plataforma) hasta que expire.
    if should_notify and not certificate.is_snoozed:
        _dispatch(certificate, alert, message)
    return alert


def _build_message(certificate, result) -> str:
    if result.status == CertificateStatus.ERROR:
        return f"No se pudo evaluar {certificate.domain}: {result.error_message}"
    if result.status == CertificateStatus.VENCIDO:
        return f"El certificado de {certificate.domain} ha expirado."
    return (
        f"El certificado de {certificate.domain} vence en {result.days_left} días."
    )


def _dispatch(certificate, alert, message):
    channels = certificate.effective_channels

    # Plataforma: la propia Alert es la notificación in-app.
    if channels["platform"]:
        _record(alert, NotificationChannel.PLATFORM, "in-app", DeliveryStatus.SENT)

    if channels["email"]:
        for email in certificate.all_recipients:
            _send_email(alert, email, certificate, message)

    if channels["webhook"]:
        for hook in _webhooks_for(certificate):
            _send_webhook(alert, hook, message)

    if channels.get("sms"):
        _send_sms(alert, certificate, message)


def _send_sms(alert, certificate, message):
    """Envía un SMS por el gateway FTP si está habilitado. Registra el delivery."""
    from apps.alerts.sms import send_sms
    from apps.core.models import SmsGatewayConfig

    config = SmsGatewayConfig.load()
    if not config.enabled:
        return  # canal pedido pero gateway apagado: nada que hacer
    text = f"{certificate.domain}: {message}"[:160]
    ok, detail = send_sms(config, text)
    _record(
        alert,
        NotificationChannel.SMS,
        config.default_number or config.ftp_host,
        DeliveryStatus.SENT if ok else DeliveryStatus.FAILED,
        "" if ok else detail,
    )


def _webhooks_for(certificate):
    from django.db.models import Q

    # Webhooks del grupo del certificado + los globales (team nulo).
    return WebhookIntegration.objects.filter(is_active=True).filter(
        Q(team=certificate.team) | Q(team__isnull=True)
    )


def _send_email(alert, email, certificate, message):
    from django.core.mail import EmailMultiAlternatives

    from apps.core.mail import default_from_email, global_bcc, smtp_connection
    from apps.core.models import OrganizationSettings
    from apps.mailtemplates.render import render_email, resolve_template
    from apps.mailtemplates.variables import cert_context

    org = OrganizationSettings.load()
    default_subject = f"[CertManager] {certificate.domain} — {alert.get_severity_display()}"
    try:
        # Plantilla atada al cert (o la predeterminada del tipo). Sin plantilla =>
        # texto plano actual (100% compatible con los envíos existentes).
        rendered = None
        tpl = resolve_template(certificate.email_template, "CERT")
        if tpl is not None:
            ctx = cert_context(certificate)
            ctx["severidad"] = alert.get_severity_display()
            rendered = render_email(tpl, ctx, org=org)

        if rendered is not None:
            msg = EmailMultiAlternatives(
                subject=rendered.subject or default_subject,
                body=rendered.text,
                from_email=default_from_email(org),
                to=[email],
                bcc=global_bcc(org, exclude=[email]),
                connection=smtp_connection(org),
            )
            msg.attach_alternative(rendered.html, "text/html")
            msg.send(fail_silently=False)
        else:
            EmailMessage(
                subject=default_subject,
                body=message,
                from_email=default_from_email(org),
                to=[email],
                bcc=global_bcc(org, exclude=[email]),
                connection=smtp_connection(org),
            ).send(fail_silently=False)
        _record(alert, NotificationChannel.EMAIL, email, DeliveryStatus.SENT)
    except Exception as exc:  # noqa: BLE001 - tolerante a fallos por diseño
        _record(alert, NotificationChannel.EMAIL, email, DeliveryStatus.FAILED, str(exc))


def _send_webhook(alert, hook, message):
    try:
        import requests
        from urllib.parse import urlparse

        from apps.monitoring.services import SSRFValidationError, validate_public_host

        # Anti-SSRF: el host del webhook no puede resolver a una dirección
        # interna/metadata (169.254.169.254, loopback, rangos privados, etc.).
        host = urlparse(hook.url).hostname
        if not host:
            raise SSRFValidationError("URL de webhook sin host válido.")
        validate_public_host(host)

        payload = {"text": message}  # formato simple; adaptar por tipo si hace falta
        resp = requests.post(hook.url, json=payload, timeout=10)
        resp.raise_for_status()
        _record(alert, NotificationChannel.WEBHOOK, hook.url, DeliveryStatus.SENT)
    except Exception as exc:  # noqa: BLE001
        _record(alert, NotificationChannel.WEBHOOK, hook.url, DeliveryStatus.FAILED, str(exc))


def _record(alert, channel, target, status, error=""):
    AlertDelivery.objects.create(
        alert=alert,
        channel=channel,
        target=target[:500],
        status=status,
        sent_at=timezone.now() if status == DeliveryStatus.SENT else None,
        error=error,
    )
    # Espejo en el stream de logs de cada intento de entrega. Un fallo de entrega
    # (webhook caído, SMTP rechaza, SMS) es ERROR operativo: una notificación
    # configurada NO llegó y ops debe enterarse; un envío correcto queda en INFO.
    _extra = {
        "event": "alert_delivery",
        "channel": str(channel),
        "target": target[:200],
        "status": str(status),
        "cert_id": getattr(getattr(alert, "certificate", None), "pk", None),
    }
    if status == DeliveryStatus.FAILED:
        logger.error(
            "entrega %s a %s falló: %s", channel, target[:120], error,
            extra={**_extra, "error": error},
        )
    else:
        logger.info("entrega %s a %s ok", channel, target[:120], extra=_extra)
