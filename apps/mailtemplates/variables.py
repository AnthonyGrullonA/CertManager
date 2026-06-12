"""Variables disponibles en las plantillas y cuáles son OBLIGATORIAS por tipo.

Un bloque ``data`` referencia una variable por su clave (``field``). Los campos
marcados ``mandatory`` deben estar presentes en la plantilla (lo valida
``EmailTemplate.clean``) y siempre se resuelven con datos reales al enviar.
"""
from __future__ import annotations

from django.utils import timezone

# kind -> {clave: {"label": str, "mandatory": bool}}
CERT_VARS = {
    "dominio": {"label": "Dominio", "mandatory": True},
    "estado": {"label": "Estado", "mandatory": True},
    "dias_restantes": {"label": "Días restantes", "mandatory": True},
    "vence_el": {"label": "Vence el", "mandatory": True},
    "puerto": {"label": "Puerto", "mandatory": False},
    "emisor": {"label": "Emisor", "mandatory": False},
    "grupo": {"label": "Grupo", "mandatory": False},
    "severidad": {"label": "Severidad", "mandatory": False},
    "frase_estado": {"label": "Frase de estado", "mandatory": False},
    "ultimo_chequeo": {"label": "Último chequeo", "mandatory": False},
}

REPORT_VARS = {
    "nombre_reporte": {"label": "Nombre del reporte", "mandatory": True},
    "total": {"label": "Total", "mandatory": True},
    "resumen_kpis": {"label": "Resumen de KPIs", "mandatory": True},
    "alcance": {"label": "Alcance", "mandatory": True},
    "generado_el": {"label": "Generado el", "mandatory": True},
    "rango_fechas": {"label": "Rango de fechas", "mandatory": False},
    "plantilla_label": {"label": "Plantilla", "mandatory": False},
}

VARS_BY_KIND = {"CERT": CERT_VARS, "REPORT": REPORT_VARS}


def variables_for(kind) -> dict:
    return VARS_BY_KIND.get(str(kind), {})


def mandatory_fields(kind) -> set:
    return {k for k, v in variables_for(kind).items() if v["mandatory"]}


def _status_phrase(cert) -> str:
    d = cert.days_left
    if d is None:
        return "está pendiente de chequeo"
    if d < 0:
        return f"venció hace {abs(d)} días"
    return f"vence en {d} días"


def cert_context(certificate, result=None) -> dict:
    """Valores reales de las variables de un certificado para el render."""
    days = certificate.days_left
    return {
        "dominio": certificate.domain,
        "puerto": str(certificate.port),
        "estado": certificate.get_status_display(),
        "dias_restantes": "sin chequear" if days is None else str(days),
        "vence_el": certificate.valid_to.strftime("%Y-%m-%d") if certificate.valid_to else "—",
        "emisor": certificate.issuer or "—",
        "grupo": certificate.team.name if certificate.team_id else "—",
        "severidad": (getattr(result, "status", None) or certificate.status or ""),
        "frase_estado": _status_phrase(certificate),
        "ultimo_chequeo": (
            certificate.last_checked_at.strftime("%Y-%m-%d %H:%M")
            if certificate.last_checked_at else "—"
        ),
    }


def report_context(report, result) -> dict:
    """Valores reales de las variables de un reporte para el render."""
    kpis = getattr(result, "kpis", None) or {}
    resumen = " · ".join(f"{k}: {v}" for k, v in kpis.items())
    return {
        "nombre_reporte": report.name,
        "total": str(getattr(result, "total", "")),
        "resumen_kpis": resumen,
        "alcance": getattr(result, "scope_label", "") or "",
        "generado_el": timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M"),
        "rango_fechas": getattr(getattr(result, "filters", None), "date_range_label", "") or "",
        "plantilla_label": getattr(result, "template_label", "") or "",
    }
