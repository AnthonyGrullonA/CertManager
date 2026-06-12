"""Siembra plantillas de ejemplo PREDETERMINADAS (CERT y REPORT).

Al ser ``is_default=True``, los envíos de alertas/reportes sin plantilla explícita
las usan automáticamente (HTML+texto) en vez del texto plano. Idempotente
(get_or_create por nombre) y reversible.
"""
from django.db import migrations

CERT_NAME = "Aviso de certificado (ejemplo)"
REPORT_NAME = "Reporte programado (ejemplo)"

CERT_BLOCKS = [
    {"type": "heading", "props": {"text": "Estado de tu certificado"}},
    {"type": "text", "props": {"text": "El certificado de {{dominio}} {{frase_estado}}. Revisa el detalle a continuación."}},
    {"type": "data", "field": "dominio"},
    {"type": "data", "field": "estado"},
    {"type": "data", "field": "dias_restantes"},
    {"type": "data", "field": "vence_el"},
    {"type": "data", "field": "emisor"},
    {"type": "divider", "props": {}},
    {"type": "footer", "props": {"text": "CertManager · notificación automática de monitoreo"}},
]

REPORT_BLOCKS = [
    {"type": "heading", "props": {"text": "{{nombre_reporte}}"}},
    {"type": "text", "props": {"text": "Adjuntamos el reporte programado. Resumen del periodo {{rango_fechas}}."}},
    {"type": "data", "field": "nombre_reporte"},
    {"type": "data", "field": "total"},
    {"type": "data", "field": "resumen_kpis"},
    {"type": "data", "field": "alcance"},
    {"type": "data", "field": "generado_el"},
    {"type": "divider", "props": {}},
    {"type": "footer", "props": {"text": "CertManager · reporte programado"}},
]


def seed(apps, schema_editor):
    EmailTemplate = apps.get_model("mailtemplates", "EmailTemplate")
    EmailTemplate.objects.get_or_create(
        name=CERT_NAME, kind="CERT",
        defaults={
            "subject": "[CertManager] {{dominio}} — {{estado}}",
            "blocks": CERT_BLOCKS, "is_default": True, "is_active": True,
        },
    )
    EmailTemplate.objects.get_or_create(
        name=REPORT_NAME, kind="REPORT",
        defaults={
            "subject": "CertManager — {{nombre_reporte}}",
            "blocks": REPORT_BLOCKS, "is_default": True, "is_active": True,
        },
    )


def unseed(apps, schema_editor):
    EmailTemplate = apps.get_model("mailtemplates", "EmailTemplate")
    EmailTemplate.objects.filter(name__in=[CERT_NAME, REPORT_NAME]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mailtemplates", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
