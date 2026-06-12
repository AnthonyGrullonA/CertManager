"""Middlewares transversales de CertManager."""
from __future__ import annotations

import logging
import time
import uuid

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse

# Prefijo donde está montado el admin de Django (config/urls.py: ``admin/``).
ADMIN_PREFIX = "/admin/"

request_logger = logging.getLogger("certmanager.request")


class RequestLogMiddleware:
    """Log estructurado por CADA request (independiente de obsforge).

    Registra método, ruta, status, latencia (ms), IP, usuario (si hay sesión web)
    y el ``reference_id`` de correlación — datos que el access-log de gunicorn no
    trae (sin latencia, sin identidad, sin id de correlación). La identidad de la
    API key la añade ``ApiKeyAuthentication`` (logger ``certmanager.api``); aquí
    queda el "sobre" con status y latencia para TODO request (web y ``/api/``).

    Va JUSTO DESPUÉS de ``AuthenticationMiddleware`` para poder leer
    ``request.user``. Salta health/static para no inundar el stream.
    """

    SKIP_PREFIXES = ("/health", "/static/", "/favicon")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self.SKIP_PREFIXES):
            return self.get_response(request)
        start = time.monotonic()
        status = 500  # si la vista revienta antes de responder, queda registrado
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            user = getattr(request, "user", None)
            actor = user.email if (user is not None and user.is_authenticated) else "anon"
            xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
            ip = (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")) or ""
            request_logger.info(
                "%s %s -> %s (%sms)",
                request.method,
                request.path,
                status,
                duration_ms,
                extra={
                    "event": "request",
                    "method": request.method,
                    "path": request.path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "actor_email": actor,
                    "ip": ip,
                    "reference_id": getattr(request, "reference_id", ""),
                },
            )


class RequestIDMiddleware:
    """Fija ``request.reference_id`` TEMPRANO y expone ``X-Request-ID``.

    Reusa el ``correlation_id`` que obsforge ya bindeó (si está activo) para que el
    id del card de soporte COINCIDA con el de los logs (``api.request.completed``);
    si no, cae a un header entrante o genera un uuid. Fail-open total: nunca rompe
    aunque obsforge no esté instalado. Debe ir justo DESPUÉS del middleware de
    obsforge (ver config/settings/base.py).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.reference_id = self._resolve(request)
        response = self.get_response(request)
        try:
            response.setdefault("X-Request-ID", request.reference_id)
        except Exception:  # noqa: BLE001
            pass
        return response

    @staticmethod
    def _resolve(request) -> str:
        try:
            from obsforge.propagation.correlation import CorrelationManager

            ctx = CorrelationManager().get_correlation()
            if ctx is not None and getattr(ctx, "correlation_id", None):
                return str(ctx.correlation_id)
        except Exception:  # noqa: BLE001 - obsforge ausente o sin contexto
            pass
        rid = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID")
        return str(rid) if rid else uuid.uuid4().hex[:16]


class MaintenanceMiddleware:
    """Modo mantenimiento opcional: si ``settings.MAINTENANCE_MODE`` está activo,
    devuelve la página 503 'maintenance' para todo el tráfico, excepto /health,
    /admin y los superusuarios (para poder operar). Va después de Auth (usa
    ``request.user``)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "MAINTENANCE_MODE", False):
            path = request.path
            user = getattr(request, "user", None)
            is_super = bool(user and user.is_authenticated and user.is_superuser)
            if not path.startswith("/health") and not path.startswith("/admin") and not is_super:
                from apps.core.errors import render_status

                return render_status(request, "maintenance", 503)
        return self.get_response(request)


class AdminAccessMiddleware:
    """Restringe el admin de Django al superusuario real.

    Regla de negocio: el ÚNICO que entra al admin de Django es el usuario creado
    por ``createsuperuser`` (``is_superuser=True``). Los Owner/Admin de la
    aplicación gestionan todo desde la propia UI y NO deben ver el admin.

    - Petición a ``/admin/...`` sin autenticar → al login con ``?next=``.
    - Autenticado pero no superusuario → al dashboard (ni siquiera se expone el
      login del admin).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path == ADMIN_PREFIX.rstrip("/") or path.startswith(ADMIN_PREFIX):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not user.is_superuser:
                return redirect("dashboard")
        return self.get_response(request)


class AuditContextMiddleware:
    """Expone la petición en curso al módulo de auditoría (thread-local) para que
    las señales sepan QUIÉN ejecuta la acción. Limpia siempre al terminar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from apps.core import audit

        audit.set_request(request)
        try:
            return self.get_response(request)
        finally:
            audit.clear_request()


# Rutas exentas de la exigencia de 2FA (enrolamiento, logout, estáticos, salud).
_2FA_EXEMPT_PREFIXES = ("/perfil/2fa/", "/accounts/logout", "/static/", "/media/", "/health")


class Require2FAMiddleware:
    """Si la organización exige 2FA (OrganizationSettings.require_2fa) y el usuario
    autenticado no lo tiene activo, lo redirige a enrolar antes de seguir usando
    la app. El superusuario y las rutas de enrolamiento quedan exentos para no
    crear un bucle. (OWASP A07 — Authentication Failures.)"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path_info
        if (
            user is not None
            and user.is_authenticated
            and not user.is_superuser
            and not path.startswith(_2FA_EXEMPT_PREFIXES)
            and not path.startswith(ADMIN_PREFIX)
        ):
            from apps.accounts.models import user_has_2fa
            from apps.core.models import OrganizationSettings

            if OrganizationSettings.load().require_2fa and not user_has_2fa(user):
                return redirect("two-factor-setup")
        return self.get_response(request)


# Rutas exentas de la expiración: el propio perfil (donde se cambia la clave),
# login/logout y recursos sin sesión. Evita el bucle de redirección.
_PWEXPIRY_EXEMPT_PREFIXES = (
    "/perfil/",
    "/accounts/login",
    "/accounts/logout",
    "/static/",
    "/media/",
    "/health",
)


class PasswordExpiryMiddleware:
    """Si la organización activa la expiración de contraseñas
    (``OrganizationSettings.password_expiry_enabled``) y la contraseña local del
    usuario superó la vigencia, lo redirige a su perfil a cambiarla antes de
    seguir usando la app. Exime al superusuario (acceso de emergencia), las rutas
    de perfil/login/logout y los usuarios LDAP/SSO (sin contraseña local usable).
    (OWASP A07 — Authentication Failures.)"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path_info
        if (
            user is not None
            and user.is_authenticated
            and not user.is_superuser
            and not path.startswith(_PWEXPIRY_EXEMPT_PREFIXES)
            and not path.startswith(ADMIN_PREFIX)
        ):
            from apps.core.models import OrganizationSettings

            org = OrganizationSettings.load()
            if org.password_expiry_enabled and user.password_expired(org):
                return redirect(f"{reverse('profile')}?password_expired=1")
        return self.get_response(request)


# Rutas exentas del timeout de sesión (no tiene sentido cerrar sesión ahí).
_SESSION_EXEMPT_PREFIXES = ("/accounts/login", "/accounts/logout", "/static/", "/media/", "/health")


class SessionTimeoutMiddleware:
    """Cierra la sesión tras N minutos de **inactividad**
    (``OrganizationSettings.session_timeout``; 0 = sin límite). Solo afecta a
    usuarios autenticados. Va después de ``AuthenticationMiddleware``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path_info
        if (
            user is not None
            and user.is_authenticated
            and not path.startswith(_SESSION_EXEMPT_PREFIXES)
        ):
            try:
                from apps.core.models import OrganizationSettings

                timeout_min = OrganizationSettings.load().session_timeout or 0
            except Exception:  # noqa: BLE001
                timeout_min = 0
            if timeout_min and timeout_min > 0:
                now = int(time.time())
                last = request.session.get("_last_activity")
                if last and (now - last) > timeout_min * 60:
                    from django.contrib.auth import logout

                    logout(request)
                    return redirect_to_login(request.get_full_path())
                request.session["_last_activity"] = now
        return self.get_response(request)
