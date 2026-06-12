"""Auditoría de acciones (OWASP A09 — Security Logging & Alerting Failures).

Registra QUIÉN hizo QUÉ sobre los recursos sensibles (certificados, grupos,
membresías, plantillas, reportes, integraciones, usuarios) y eventos de
autenticación (login OK/fallido, bloqueo). El actor se obtiene de un thread-local
que pone ``AuditContextMiddleware`` por petición; las señales de modelo leen ese
contexto sin tener que pasar el request a mano por todas las vistas.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger("certmanager.audit")

_ctx = threading.local()


def set_request(request):
    _ctx.request = request


def clear_request():
    _ctx.request = None


def _current_request():
    return getattr(_ctx, "request", None)


def current_actor():
    """Usuario autenticado de la petición en curso, o None (shell/cron/sistema)."""
    req = _current_request()
    user = getattr(req, "user", None) if req is not None else None
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def client_ip(request=None):
    request = request or _current_request()
    if request is None:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def record(action, *, model="", object_id="", object_repr="", changes=None,
           actor=None, actor_email="", ip="", request=None):
    """Escribe una entrada de auditoría. Tolerante a fallos: nunca rompe la
    petición (un fallo de logging no debe tumbar la acción del usuario)."""
    # Import diferido: evita ciclos con models en el arranque.
    from apps.core.models import AuditLog

    actor = actor or current_actor()
    if actor is not None and not actor_email:
        actor_email = getattr(actor, "email", "") or str(actor)
    ip = ip or client_ip(request)

    # Síntesis a la observabilidad (obsforge/Loki) + fichero: una línea por
    # evento de auditoría, además de la fila en la tabla AuditLog (BD).
    logger.info(
        "audit:%s", action,
        extra={
            "event": "audit",
            "action": action,
            "model": model or "",
            "object_id": str(object_id),
            "object_repr": str(object_repr)[:255],
            "actor_email": actor_email,
            "ip": ip or "",
        },
    )

    try:
        AuditLog.objects.create(
            actor=actor if (actor is not None and getattr(actor, "pk", None)) else None,
            actor_email=actor_email[:254],
            action=action[:32],
            model=model[:64],
            object_id=str(object_id)[:64],
            object_repr=str(object_repr)[:255],
            changes=changes or {},
            ip=(ip[:45] if ip else None),
        )
    except Exception:  # noqa: BLE001 — auditoría nunca debe romper el flujo
        logger.exception("No se pudo registrar auditoría (%s %s)", action, model)


def log_event(action, *, object_repr="", request=None, actor=None, actor_email="", changes=None):
    """Atajo para eventos que no son mutaciones de modelo (login, lockout)."""
    record(
        action,
        model="auth",
        object_repr=object_repr,
        changes=changes,
        actor=actor,
        actor_email=actor_email,
        request=request,
    )
