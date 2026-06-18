"""Conexión de correo construida desde OrganizationSettings.

El sistema permite configurar el SMTP desde la UI (OrganizationSettings) en vez de
depender solo de las variables EMAIL_* de settings. Este helper construye una
conexión Django a partir de esa configuración para envíos reales (prueba de SMTP,
reportes programados, etc.). Si no hay host configurado, cae a la conexión por
defecto de Django (settings.EMAIL_*).
"""
from __future__ import annotations

from django.core.mail import get_connection


def smtp_connection(org=None):
    """Devuelve una conexión de email basada en OrganizationSettings.

    Si `org` no trae host SMTP, usa la conexión por defecto de Django.
    """
    if org is None:
        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()

    if not org.smtp_host:
        return get_connection()  # backend por defecto (settings.EMAIL_*)

    # Backend propio: evita CRAM-MD5 (HMAC-MD5), que falla en hosts con OpenSSL
    # en modo FIPS. Usa AUTH PLAIN/LOGIN sobre STARTTLS. Ver apps/core/email_backends.
    return get_connection(
        backend="apps.core.email_backends.FipsSafeEmailBackend",
        host=org.smtp_host,
        port=org.smtp_port or 587,
        username=org.smtp_user or "",
        password=org.smtp_password or "",
        use_tls=bool(org.smtp_use_tls),
    )


def default_from_email(org=None):
    """Remitente preferido: el de OrganizationSettings o el de settings."""
    from django.conf import settings as dj_settings

    if org is None:
        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()
    return org.smtp_from or org.smtp_user or dj_settings.DEFAULT_FROM_EMAIL


def global_bcc(org=None, *, exclude=None):
    """Copia global de auditoría para correos salientes de CertManager."""
    if org is None:
        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()

    address = (org.email_copy_address or "").strip()
    if not org.email_copy_enabled or not address:
        return []

    excluded = {email.lower() for email in (exclude or []) if email}
    if address.lower() in excluded:
        return []
    return [address]
