"""Siembra la configuración/integraciones migradas del aplicativo legacy.

Carga en la base de datos los valores que en `certapp_old` estaban embebidos en el
código: SMTP (SocketLabs), remitente, destinatario por defecto y el gateway SMS por
FTP (desactivado). Las credenciales quedan en BD y se muestran enmascaradas en la
UI; **se recomienda rotarlas tras la migración**.

Idempotente: por defecto solo rellena lo que esté vacío. Usa --force para sobrescribir.

    python manage.py seed_integrations [--force]

SEGURIDAD: las credenciales NO viven en el código (este repo es público). Se leen
de variables de entorno ``CF_SEED_*`` en tiempo de ejecución del seeding. Si una
variable no está presente, ese campo simplemente no se siembra (queda como esté).
Ejemplo (.env del operador):

    CF_SEED_SMTP_HOST=smtp.tu-proveedor.com
    CF_SEED_SMTP_USER=...
    CF_SEED_SMTP_PASSWORD=...           # secreto: solo en el entorno, nunca en git
    CF_SEED_SMTP_FROM=alertas@tu-dominio
    CF_SEED_SMS_FTP_HOST=...
    CF_SEED_SMS_FTP_PASSWORD=...        # secreto
"""
import os

from django.core.management.base import BaseCommand

from apps.core.models import OrganizationSettings, SmsGatewayConfig
from apps.teams.models import Team


def _env(name, default=""):
    return (os.environ.get(name) or default).strip()


def _legacy_from_env():
    """Lee los valores de integración del entorno EN TIEMPO DE EJECUCIÓN (no al
    importar), para que sea testeable y reaccione al entorno del operador."""
    return {
        "smtp_host": _env("CF_SEED_SMTP_HOST"),
        "smtp_port": int(_env("CF_SEED_SMTP_PORT", "587") or "587"),
        "smtp_user": _env("CF_SEED_SMTP_USER"),
        "smtp_password": _env("CF_SEED_SMTP_PASSWORD"),
        "smtp_from": _env("CF_SEED_SMTP_FROM"),
        "smtp_use_tls": True,
        "email_copy_enabled": bool(_env("CF_SEED_EMAIL_COPY_ADDRESS")),
        "email_copy_address": _env("CF_SEED_EMAIL_COPY_ADDRESS"),
        "default_recipient": _env("CF_SEED_DEFAULT_RECIPIENT"),
        "sms_ftp_host": _env("CF_SEED_SMS_FTP_HOST"),
        "sms_ftp_user": _env("CF_SEED_SMS_FTP_USER"),
        "sms_ftp_password": _env("CF_SEED_SMS_FTP_PASSWORD"),
        "sms_default_number": _env("CF_SEED_SMS_DEFAULT_NUMBER"),
    }


class Command(BaseCommand):
    help = "Siembra la config/integraciones migradas del legacy (SMTP, remitente, SMS/FTP)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Sobrescribe valores existentes.")

    def handle(self, *args, **options):
        force = options["force"]
        LEGACY = _legacy_from_env()

        def setval(obj, field, value):
            # Solo siembra valores presentes (no pisa con vacíos si no hay env).
            if value in ("", None):
                return
            if force or not getattr(obj, field):
                setattr(obj, field, value)

        # --- SMTP (OrganizationSettings) ---
        org = OrganizationSettings.load()
        setval(org, "smtp_host", LEGACY["smtp_host"])
        if LEGACY["smtp_host"] and (force or not org.smtp_port or org.smtp_port == 587):
            org.smtp_port = LEGACY["smtp_port"]
        setval(org, "smtp_user", LEGACY["smtp_user"])
        setval(org, "smtp_password", LEGACY["smtp_password"])
        setval(org, "smtp_from", LEGACY["smtp_from"])
        setval(org, "email_copy_address", LEGACY["email_copy_address"])
        if LEGACY["smtp_host"]:
            org.smtp_use_tls = True
        if LEGACY["email_copy_address"]:
            org.email_copy_enabled = True
        org.save()
        self.stdout.write(self.style.SUCCESS(f"SMTP: {org.smtp_host or '(sin sembrar)'} (remitente {org.smtp_from or '—'})"))

        # --- Gateway SMS por FTP (desactivado) ---
        sms = SmsGatewayConfig.load()
        setval(sms, "ftp_host", LEGACY["sms_ftp_host"])
        setval(sms, "ftp_user", LEGACY["sms_ftp_user"])
        setval(sms, "ftp_password", LEGACY["sms_ftp_password"])
        setval(sms, "default_number", LEGACY["sms_default_number"])
        sms.save()  # enabled queda False por defecto (reactivable desde la UI)
        self.stdout.write(self.style.SUCCESS(f"Gateway SMS: {sms.ftp_host or '(sin sembrar)'} (desactivado)"))

        # --- Destinatario por defecto en el grupo 'Sin asignar' ---
        team = Team.objects.filter(name="Sin asignar").first()
        if team is not None and LEGACY["default_recipient"]:
            recips = list(team.default_recipients or [])
            if LEGACY["default_recipient"] not in recips:
                recips.append(LEGACY["default_recipient"])
                team.default_recipients = recips
                team.save(update_fields=["default_recipients", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"Destinatario por defecto en 'Sin asignar': {LEGACY['default_recipient']}"))
        elif team is None and LEGACY["default_recipient"]:
            self.stdout.write(self.style.WARNING("Grupo 'Sin asignar' no existe aún; corre data_update_certs_app primero."))

        self.stdout.write(self.style.WARNING(
            "Credenciales vía CF_SEED_* (entorno). Rótalas tras la puesta en producción."
        ))
