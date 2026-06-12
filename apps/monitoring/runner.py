"""Orquesta un chequeo y lo persiste.

Une el servicio puro (SSLChecker) con la base de datos: crea el CertificateCheck,
actualiza los campos denormalizados del Certificate y delega la generación de
alertas. Lo usan tanto el command `check_certificates` como la acción "Probar
ahora" de la API.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.certificates.models import Certificate, CertificateCheck

from .services import CheckResult, SSLChecker

logger = logging.getLogger("certmanager.monitoring")


def _monitoring_config() -> dict:
    """Parámetros de monitoreo desde OrganizationSettings (UI), con fallback a
    ``settings.MONITORING``. Fail-safe ante errores de BD.

    - ``timeout``: segundos antes de abortar un chequeo (Configuración → Monitoreo).
    - ``attempts``: intentos del chequeo antes de marcar error (campo "Reintentos";
      mínimo 1).
    """
    cfg = settings.MONITORING
    timeout, attempts = cfg["CONNECT_TIMEOUT"], 1
    try:
        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()
        timeout = org.connect_timeout or cfg["CONNECT_TIMEOUT"]
        attempts = max(1, org.retries or 1)
    except Exception:  # noqa: BLE001 - BD no lista / cualquier error -> defaults
        pass
    return {"timeout": timeout, "attempts": attempts}


def run_check(certificate: Certificate, *, notify: bool = True) -> tuple[CertificateCheck, CheckResult]:
    """Ejecuta el chequeo de un certificado, lo persiste y (opcional) notifica."""
    mon = _monitoring_config()
    checker = SSLChecker(
        timeout=mon["timeout"],
        allow_legacy_renegotiation=settings.MONITORING["ALLOW_LEGACY_RENEGOTIATION"],
    )
    # Reintenta SOLO ante fallo de conexión/verificación, hasta `attempts` intentos.
    result = None
    for _attempt in range(mon["attempts"]):
        result = checker.check(
            certificate.domain,
            certificate.port,
            certificate.effective_threshold,
            certificate.effective_critical,
        )
        if result.ok:
            break
    now = timezone.now()

    check = CertificateCheck.objects.create(
        certificate=certificate,
        checked_at=now,
        status=result.status,
        days_left=result.days_left,
        valid_from=result.valid_from,
        valid_to=result.valid_to,
        issuer=result.issuer,
        subject=result.subject,
        serial=result.serial,
        fingerprint_sha256=result.fingerprint_sha256,
        signature_algorithm=result.signature_algorithm,
        key_size=result.key_size,
        san=result.san,
        chain=result.chain,
        error_message=result.error_message,
        latency_ms=result.latency_ms,
    )

    # Actualiza el cache denormalizado del certificado.
    interval = settings.MONITORING["CHECK_INTERVAL_HOURS"]
    certificate.status = result.status
    certificate.days_left = result.days_left
    certificate.valid_from = result.valid_from
    certificate.valid_to = result.valid_to
    certificate.issuer = result.issuer
    certificate.subject = result.subject
    certificate.last_checked_at = now
    certificate.next_check_at = now + timedelta(hours=interval)
    certificate.last_error = result.error_message
    certificate.last_check = check
    certificate.save(update_fields=[
        "status", "days_left", "valid_from", "valid_to", "issuer", "subject",
        "last_checked_at", "next_check_at", "last_error", "last_check", "updated_at",
    ])

    # Log estructurado del resultado del chequeo (va a stdout/Loki). Un chequeo
    # fallido (conexión/verificación) es WARNING operativo; uno exitoso, INFO.
    _extra = {
        "event": "cert_check",
        "domain": certificate.domain,
        "port": certificate.port,
        "status": str(result.status),
        "days_left": result.days_left,
        "latency_ms": result.latency_ms,
        "cert_id": certificate.pk,
    }
    if not result.ok:
        logger.warning(
            "check %s:%s falló: %s",
            certificate.domain, certificate.port, result.error_message,
            extra={**_extra, "error": result.error_message},
        )
    else:
        logger.info(
            "check %s:%s ok (status=%s, days_left=%s)",
            certificate.domain, certificate.port, result.status, result.days_left,
            extra=_extra,
        )

    if notify:
        # Import diferido para evitar dependencia circular en tiempo de carga.
        from apps.alerts.services import evaluate_alert

        evaluate_alert(certificate, result)

    return check, result
