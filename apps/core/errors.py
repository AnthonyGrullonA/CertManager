"""Sistema centralizado de páginas de estado/error (catálogo + render + handlers).

Un único ``ERROR_CATALOG`` (HTTP 4xx/5xx + negocio + operacional + multi-tenant +
UX) renderizado por unos pocos componentes Forge UI reutilizables. Cada página
muestra el código y un card "code" copiable con el ``reference_id`` (== el
``correlation_id`` que obsforge emite en sus logs, con fallback uuid), para que
soporte lo pegue en Grafana/Loki y encuentre el log exacto.

Obsforge-OPCIONAL y fail-open: funciona con y sin obsforge. El render nunca
propaga (fallback a texto plano) para no romper la cadena de errores de Django.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from django.http import HttpResponse
from django.template.loader import render_to_string

# tone: familia de estado de forge.css → ok|warn|crit|exp|err|none
# category: http|business|operational|tenant|ux
# icon: SOLO claves existentes en FORGE_ICON_PATHS (apps/web/templatetags/forge_icons.py)
ERROR_CATALOG: dict[str, dict] = {
    # ---------------- HTTP 4xx ----------------
    "http-400": {"http_status": 400, "category": "http", "title": "Solicitud inválida", "message": "No pudimos procesar la solicitud porque los datos enviados no son válidos.", "icon": "circle-alert", "tone": "warn"},
    "http-401": {"http_status": 401, "category": "http", "title": "No autenticado", "message": "Necesitas iniciar sesión para acceder a este recurso.", "icon": "lock", "tone": "exp", "cta": {"label": "Iniciar sesión", "href": "/accounts/login/"}},
    "http-402": {"http_status": 402, "category": "http", "title": "Pago requerido", "message": "Este recurso requiere una suscripción activa.", "icon": "file-text", "tone": "crit"},
    "http-403": {"http_status": 403, "category": "http", "title": "Acceso denegado", "message": "No tienes permiso para acceder a este recurso.", "icon": "shield-alert", "tone": "exp"},
    "http-404": {"http_status": 404, "category": "http", "title": "Página no encontrada", "message": "La página que buscas no existe o fue movida.", "icon": "search", "tone": "warn", "cta": {"label": "Ir al inicio", "href": "/"}},
    "http-405": {"http_status": 405, "category": "http", "title": "Método no permitido", "message": "La operación solicitada no está permitida en este recurso.", "icon": "circle-x", "tone": "warn"},
    "http-406": {"http_status": 406, "category": "http", "title": "No aceptable", "message": "No podemos entregar el contenido en el formato solicitado.", "icon": "circle-alert", "tone": "warn"},
    "http-408": {"http_status": 408, "category": "http", "title": "Tiempo de espera agotado", "message": "La solicitud tardó demasiado. Inténtalo de nuevo.", "icon": "clock", "tone": "warn", "retry": True},
    "http-409": {"http_status": 409, "category": "http", "title": "Conflicto", "message": "El recurso fue modificado por otra operación. Refresca e intenta otra vez.", "icon": "layers", "tone": "warn", "retry": True},
    "http-410": {"http_status": 410, "category": "http", "title": "Recurso eliminado", "message": "Este recurso ya no está disponible de forma permanente.", "icon": "trash-2", "tone": "none"},
    "http-411": {"http_status": 411, "category": "http", "title": "Longitud requerida", "message": "La solicitud no incluye la longitud de contenido requerida.", "icon": "circle-alert", "tone": "warn"},
    "http-412": {"http_status": 412, "category": "http", "title": "Precondición fallida", "message": "No se cumplieron las condiciones previas de la solicitud.", "icon": "circle-alert", "tone": "warn"},
    "http-413": {"http_status": 413, "category": "http", "title": "Contenido demasiado grande", "message": "El archivo o los datos enviados superan el límite permitido.", "icon": "triangle-alert", "tone": "warn"},
    "http-414": {"http_status": 414, "category": "http", "title": "URL demasiado larga", "message": "La dirección solicitada excede la longitud máxima.", "icon": "circle-alert", "tone": "warn"},
    "http-415": {"http_status": 415, "category": "http", "title": "Tipo de medio no soportado", "message": "El formato del archivo enviado no es compatible.", "icon": "file-text", "tone": "warn"},
    "http-416": {"http_status": 416, "category": "http", "title": "Rango no satisfactible", "message": "El rango solicitado no es válido para este recurso.", "icon": "circle-alert", "tone": "warn"},
    "http-417": {"http_status": 417, "category": "http", "title": "Expectativa fallida", "message": "No pudimos cumplir la expectativa indicada en la solicitud.", "icon": "circle-alert", "tone": "warn"},
    "http-418": {"http_status": 418, "category": "http", "title": "Soy una tetera", "message": "Solicitud no procesable por este servidor.", "icon": "info", "tone": "none"},
    "http-421": {"http_status": 421, "category": "http", "title": "Solicitud mal dirigida", "message": "Esta solicitud no puede ser atendida por este servidor.", "icon": "server", "tone": "warn"},
    "http-422": {"http_status": 422, "category": "http", "title": "Entidad no procesable", "message": "Los datos son válidos pero no pudieron procesarse.", "icon": "circle-alert", "tone": "warn"},
    "http-423": {"http_status": 423, "category": "http", "title": "Recurso bloqueado", "message": "Este recurso está bloqueado temporalmente.", "icon": "lock", "tone": "exp"},
    "http-424": {"http_status": 424, "category": "http", "title": "Dependencia fallida", "message": "La operación falló porque dependía de otra que no se completó.", "icon": "layers", "tone": "warn"},
    "http-425": {"http_status": 425, "category": "http", "title": "Demasiado pronto", "message": "La solicitud se envió antes de tiempo. Inténtalo de nuevo.", "icon": "clock", "tone": "warn", "retry": True},
    "http-426": {"http_status": 426, "category": "http", "title": "Actualización requerida", "message": "Debes actualizar el protocolo o cliente para continuar.", "icon": "refresh-cw", "tone": "warn"},
    "http-428": {"http_status": 428, "category": "http", "title": "Precondición requerida", "message": "La solicitud debe incluir una condición previa.", "icon": "circle-alert", "tone": "warn"},
    "http-429": {"http_status": 429, "category": "http", "title": "Demasiadas solicitudes", "message": "Hiciste demasiadas solicitudes. Espera un momento e intenta de nuevo.", "icon": "clock", "tone": "crit", "retry": True},
    "http-431": {"http_status": 431, "category": "http", "title": "Cabeceras demasiado grandes", "message": "Las cabeceras de la solicitud superan el límite permitido.", "icon": "triangle-alert", "tone": "warn"},
    "http-451": {"http_status": 451, "category": "http", "title": "No disponible por motivos legales", "message": "Este contenido no está disponible por razones legales.", "icon": "shield-alert", "tone": "exp"},
    # ---------------- HTTP 5xx ----------------
    "http-500": {"http_status": 500, "category": "http", "title": "Error interno del servidor", "message": "Ocurrió un error inesperado de nuestro lado. Ya estamos revisando.", "icon": "triangle-alert", "tone": "err", "retry": True},
    "http-501": {"http_status": 501, "category": "http", "title": "No implementado", "message": "Esta funcionalidad aún no está disponible.", "icon": "circle-x", "tone": "err"},
    "http-502": {"http_status": 502, "category": "http", "title": "Puerta de enlace incorrecta", "message": "Un servicio intermedio respondió de forma inválida. Inténtalo de nuevo.", "icon": "server", "tone": "err", "retry": True},
    "http-503": {"http_status": 503, "category": "http", "title": "Servicio no disponible", "message": "El servicio no está disponible temporalmente. Vuelve en unos minutos.", "icon": "server", "tone": "crit", "retry": True},
    "http-504": {"http_status": 504, "category": "http", "title": "Tiempo de espera de la puerta de enlace", "message": "Un servicio tardó demasiado en responder. Inténtalo de nuevo.", "icon": "clock", "tone": "err", "retry": True},
    "http-505": {"http_status": 505, "category": "http", "title": "Versión HTTP no soportada", "message": "La versión del protocolo usada no es compatible.", "icon": "server", "tone": "err"},
    "http-506": {"http_status": 506, "category": "http", "title": "Negociación de variante", "message": "Error de configuración en la negociación de contenido.", "icon": "settings", "tone": "err"},
    "http-507": {"http_status": 507, "category": "http", "title": "Almacenamiento insuficiente", "message": "El servidor no tiene espacio suficiente para completar la operación.", "icon": "server", "tone": "err"},
    "http-508": {"http_status": 508, "category": "http", "title": "Bucle detectado", "message": "Se detectó un bucle al procesar la solicitud.", "icon": "refresh-cw", "tone": "err"},
    "http-510": {"http_status": 510, "category": "http", "title": "No extendido", "message": "La solicitud requiere extensiones que el servidor no soporta.", "icon": "circle-alert", "tone": "err"},
    "http-511": {"http_status": 511, "category": "http", "title": "Autenticación de red requerida", "message": "Necesitas autenticarte en la red para acceder.", "icon": "globe", "tone": "crit"},
    # ---------------- NEGOCIO ----------------
    "account-disabled": {"http_status": 403, "category": "business", "title": "Cuenta deshabilitada", "message": "Tu cuenta está deshabilitada. Contacta al administrador para reactivarla.", "icon": "user", "tone": "exp"},
    "account-locked": {"http_status": 423, "category": "business", "title": "Cuenta bloqueada", "message": "Tu cuenta se bloqueó por intentos fallidos. Inténtalo más tarde o restablece tu contraseña.", "icon": "lock", "tone": "exp"},
    "account-suspended": {"http_status": 403, "category": "business", "title": "Cuenta suspendida", "message": "Tu cuenta está suspendida. Contacta a soporte para más información.", "icon": "shield-alert", "tone": "exp"},
    "account-deleted": {"http_status": 410, "category": "business", "title": "Cuenta eliminada", "message": "Esta cuenta fue eliminada y ya no está disponible.", "icon": "trash-2", "tone": "none"},
    "account-pending-verification": {"http_status": 403, "category": "business", "title": "Verifica tu correo", "message": "Confirma tu dirección de correo para activar tu cuenta.", "icon": "mail", "tone": "warn", "cta": {"label": "Ir al perfil", "href": "/perfil/"}},
    "account-pending-approval": {"http_status": 403, "category": "business", "title": "Cuenta en revisión", "message": "Tu cuenta está pendiente de aprobación por un administrador.", "icon": "clock", "tone": "warn"},
    "password-expired": {"http_status": 403, "category": "business", "title": "Contraseña expirada", "message": "Tu contraseña expiró. Debes establecer una nueva para continuar.", "icon": "key", "tone": "exp"},
    "session-expired": {"http_status": 401, "category": "business", "title": "Sesión expirada", "message": "Tu sesión expiró por inactividad. Inicia sesión de nuevo.", "icon": "clock", "tone": "exp", "cta": {"label": "Iniciar sesión", "href": "/accounts/login/"}},
    "mfa-required": {"http_status": 403, "category": "business", "title": "Verificación en dos pasos", "message": "Completa la verificación en dos pasos para continuar.", "icon": "shield-check", "tone": "warn"},
    "subscription-expired": {"http_status": 402, "category": "business", "title": "Suscripción vencida", "message": "Tu suscripción venció. Renueva para seguir usando CertManager.", "icon": "calendar", "tone": "crit"},
    "subscription-canceled": {"http_status": 402, "category": "business", "title": "Suscripción cancelada", "message": "Tu suscripción fue cancelada. Reactívala para recuperar el acceso.", "icon": "circle-x", "tone": "crit"},
    "payment-required": {"http_status": 402, "category": "business", "title": "Pago requerido", "message": "Hay un pago pendiente. Actualiza tu método de pago para continuar.", "icon": "file-text", "tone": "crit"},
    "payment-failed": {"http_status": 402, "category": "business", "title": "Pago rechazado", "message": "No pudimos procesar tu último pago. Revisa tu método de pago.", "icon": "triangle-alert", "tone": "crit"},
    "trial-expired": {"http_status": 402, "category": "business", "title": "Prueba finalizada", "message": "Tu periodo de prueba terminó. Elige un plan para continuar.", "icon": "clock", "tone": "crit"},
    "billing-issue": {"http_status": 402, "category": "business", "title": "Problema de facturación", "message": "Hay un problema con tu facturación. Contacta a soporte o revisa tu cuenta.", "icon": "file-text", "tone": "crit"},
    "plan-limit-reached": {"http_status": 403, "category": "business", "title": "Límite del plan alcanzado", "message": "Alcanzaste el límite de tu plan actual. Mejóralo para continuar.", "icon": "trending-up", "tone": "crit"},
    "seat-limit-reached": {"http_status": 403, "category": "business", "title": "Sin asientos disponibles", "message": "Tu plan no tiene asientos de usuario disponibles. Agrega más para invitar.", "icon": "users", "tone": "crit"},
    "quota-exceeded": {"http_status": 429, "category": "business", "title": "Cuota excedida", "message": "Superaste la cuota de uso de tu plan. Espera al próximo ciclo o mejóralo.", "icon": "trending-up", "tone": "crit"},
    "storage-limit-reached": {"http_status": 403, "category": "business", "title": "Almacenamiento lleno", "message": "Alcanzaste el límite de almacenamiento. Libera espacio o amplía tu plan.", "icon": "server", "tone": "crit"},
    "api-rate-limit": {"http_status": 429, "category": "business", "title": "Límite de API alcanzado", "message": "Superaste el límite de llamadas a la API. Reintenta en unos minutos.", "icon": "clock", "tone": "crit", "retry": True},
    "license-expired": {"http_status": 403, "category": "business", "title": "Licencia expirada", "message": "La licencia de tu organización expiró. Renuévala para seguir operando.", "icon": "shield-alert", "tone": "exp"},
    "license-invalid": {"http_status": 403, "category": "business", "title": "Licencia inválida", "message": "La licencia no es válida o no pudo verificarse. Contacta a soporte.", "icon": "shield-alert", "tone": "exp"},
    # ---------------- OPERACIONALES ----------------
    "maintenance": {"http_status": 503, "category": "operational", "title": "En mantenimiento", "message": "Estamos haciendo mejoras. Volvemos en breve, gracias por tu paciencia.", "icon": "settings", "tone": "crit", "retry": True},
    "degraded": {"http_status": 503, "category": "operational", "title": "Servicio degradado", "message": "Algunas funciones pueden estar lentas o no disponibles temporalmente.", "icon": "triangle-alert", "tone": "warn", "retry": True},
    "read-only": {"http_status": 503, "category": "operational", "title": "Modo solo lectura", "message": "El sistema está en modo solo lectura. Puedes consultar pero no modificar por ahora.", "icon": "eye", "tone": "warn"},
    "offline": {"http_status": 503, "category": "operational", "title": "Sin conexión", "message": "No pudimos conectar con el servidor. Revisa tu conexión e intenta de nuevo.", "icon": "globe", "tone": "crit", "retry": True},
    "database-down": {"http_status": 503, "category": "operational", "title": "Base de datos no disponible", "message": "No pudimos conectar con la base de datos. Reintenta en unos minutos.", "icon": "server", "tone": "err", "retry": True},
    "cache-down": {"http_status": 503, "category": "operational", "title": "Caché no disponible", "message": "El servicio de caché no responde. El sistema puede ir más lento.", "icon": "server", "tone": "warn", "retry": True},
    "email-provider-down": {"http_status": 503, "category": "operational", "title": "Correo no disponible", "message": "No pudimos enviar el correo. El proveedor de correo no responde.", "icon": "mail", "tone": "crit", "retry": True},
    "payment-provider-down": {"http_status": 503, "category": "operational", "title": "Pagos no disponibles", "message": "El proveedor de pagos no responde. Inténtalo de nuevo en unos minutos.", "icon": "file-text", "tone": "crit", "retry": True},
    "sms-provider-down": {"http_status": 503, "category": "operational", "title": "SMS no disponible", "message": "No pudimos enviar el SMS. El proveedor no responde por ahora.", "icon": "bell", "tone": "crit", "retry": True},
    "integration-error": {"http_status": 502, "category": "operational", "title": "Error de integración", "message": "Una integración externa falló. Revisa la configuración o reintenta.", "icon": "layers", "tone": "err", "retry": True},
    "oauth-error": {"http_status": 502, "category": "operational", "title": "Error de autenticación externa", "message": "No pudimos completar el inicio de sesión con el proveedor externo.", "icon": "key", "tone": "err", "retry": True},
    "webhook-error": {"http_status": 502, "category": "operational", "title": "Error de webhook", "message": "No pudimos entregar el webhook. Reintentaremos automáticamente.", "icon": "webhook", "tone": "err", "retry": True},
    "sync-error": {"http_status": 502, "category": "operational", "title": "Error de sincronización", "message": "La sincronización falló. Reintenta o revisa el origen de datos.", "icon": "refresh-cw", "tone": "err", "retry": True},
    # ---------------- MULTI-TENANT ----------------
    "tenant-not-found": {"http_status": 404, "category": "tenant", "title": "Organización no encontrada", "message": "La organización solicitada no existe.", "icon": "search", "tone": "warn"},
    "tenant-disabled": {"http_status": 403, "category": "tenant", "title": "Organización deshabilitada", "message": "Esta organización está deshabilitada. Contacta a soporte.", "icon": "shield-alert", "tone": "exp"},
    "tenant-suspended": {"http_status": 403, "category": "tenant", "title": "Organización suspendida", "message": "Esta organización está suspendida temporalmente.", "icon": "shield-alert", "tone": "exp"},
    "tenant-archived": {"http_status": 410, "category": "tenant", "title": "Organización archivada", "message": "Esta organización fue archivada y es de solo lectura.", "icon": "layers", "tone": "none"},
    "org-not-found": {"http_status": 404, "category": "tenant", "title": "Equipo no encontrado", "message": "El equipo u organización solicitada no existe.", "icon": "search", "tone": "warn"},
    "org-disabled": {"http_status": 403, "category": "tenant", "title": "Equipo deshabilitado", "message": "Este equipo está deshabilitado.", "icon": "users", "tone": "exp"},
    "branch-not-found": {"http_status": 404, "category": "tenant", "title": "Sucursal no encontrada", "message": "La sucursal solicitada no existe.", "icon": "search", "tone": "warn"},
    "branch-disabled": {"http_status": 403, "category": "tenant", "title": "Sucursal deshabilitada", "message": "Esta sucursal está deshabilitada.", "icon": "shield-alert", "tone": "exp"},
    "branch-suspended": {"http_status": 403, "category": "tenant", "title": "Sucursal suspendida", "message": "Esta sucursal está suspendida temporalmente.", "icon": "shield-alert", "tone": "exp"},
    "branch-archived": {"http_status": 410, "category": "tenant", "title": "Sucursal archivada", "message": "Esta sucursal fue archivada y es de solo lectura.", "icon": "layers", "tone": "none"},
    "insufficient-role": {"http_status": 403, "category": "tenant", "title": "Rol insuficiente", "message": "Tu rol no tiene los permisos necesarios para esta acción.", "icon": "shield-alert", "tone": "exp"},
    "permission-denied": {"http_status": 403, "category": "tenant", "title": "Permiso denegado", "message": "No tienes permiso para realizar esta acción.", "icon": "lock", "tone": "exp"},
    "feature-not-enabled": {"http_status": 403, "category": "tenant", "title": "Función no habilitada", "message": "Esta función no está habilitada en tu plan u organización.", "icon": "sliders-horizontal", "tone": "warn"},
    # ---------------- UX (estados no-error) ----------------
    "empty-state": {"http_status": 200, "category": "ux", "title": "Aún no hay nada aquí", "message": "Cuando agregues datos aparecerán en esta sección.", "icon": "layers", "tone": "none"},
    "no-results": {"http_status": 200, "category": "ux", "title": "Sin resultados", "message": "No encontramos coincidencias. Prueba con otros filtros o términos.", "icon": "search", "tone": "none"},
    "first-time-setup": {"http_status": 200, "category": "ux", "title": "Configura tu espacio", "message": "Completa la configuración inicial para empezar a monitorear certificados.", "icon": "settings", "tone": "none"},
    "onboarding": {"http_status": 200, "category": "ux", "title": "Te damos la bienvenida", "message": "Sigue estos pasos para sacar el máximo provecho de CertManager.", "icon": "shield-check", "tone": "none", "cta": {"label": "Empezar", "href": "/"}},
    "waiting": {"http_status": 200, "category": "ux", "title": "En espera", "message": "Estamos esperando que finalice una operación previa.", "icon": "clock", "tone": "none", "retry": True},
    "loading": {"http_status": 200, "category": "ux", "title": "Cargando", "message": "Estamos preparando tus datos, esto tomará solo un momento.", "icon": "refresh-cw", "tone": "none"},
    "syncing": {"http_status": 200, "category": "ux", "title": "Sincronizando", "message": "Estamos sincronizando la información más reciente.", "icon": "refresh-cw", "tone": "none"},
}

VALID_TONES = {"ok", "warn", "crit", "exp", "err", "none"}
DEFAULT = {
    "http_status": 500, "category": "http", "title": "Algo salió mal",
    "message": "Ocurrió un error inesperado. Inténtalo de nuevo en unos minutos.",
    "icon": "triangle-alert", "tone": "err", "retry": True, "cta": None,
}


@dataclass(frozen=True)
class StatusMeta:
    key: str
    http_status: int
    category: str
    title: str
    message: str
    icon: str
    tone: str
    retry: bool = False
    cta: dict | None = None


def get_meta(key: str, http_status: int | None = None) -> StatusMeta:
    raw = {**DEFAULT, **ERROR_CATALOG.get(key, {})}
    if http_status is not None:
        raw["http_status"] = http_status
    if raw["tone"] not in VALID_TONES:
        raw["tone"] = "err"
    return StatusMeta(
        key=key, http_status=raw["http_status"], category=raw["category"],
        title=raw["title"], message=raw["message"], icon=raw["icon"],
        tone=raw["tone"], retry=raw.get("retry", False), cta=raw.get("cta"),
    )


def _obsforge_correlation_id() -> str | None:
    """correlation_id del request actual si obsforge está activo. Lectura PURA
    (no muta el contextvar). Fail-safe total si obsforge no está instalado."""
    try:
        from obsforge.propagation.correlation import CorrelationManager
    except ImportError:
        return None
    try:
        ctx = CorrelationManager().get_correlation()
    except Exception:  # noqa: BLE001 - la telemetría nunca rompe el render
        return None
    return getattr(ctx, "correlation_id", None) if ctx is not None else None


def current_reference_id(request) -> str:
    """Reference id para el card de soporte. Garantiza str, nunca lanza.

    Prioridad: request.reference_id (fijado por RequestIDMiddleware) → obsforge →
    header entrante X-Correlation-ID/X-Request-ID → uuid corto.
    """
    rid = getattr(request, "reference_id", None)
    if rid:
        return str(rid)
    rid = _obsforge_correlation_id()
    if rid:
        return str(rid)
    headers = getattr(request, "headers", {}) or {}
    rid = headers.get("X-Correlation-ID") or headers.get("X-Request-ID")
    if rid:
        return str(rid)
    return uuid.uuid4().hex[:16]


def build_reference(request, meta: StatusMeta) -> dict:
    return {
        "reference_id": current_reference_id(request),
        "path": getattr(request, "path", "") or "",
        "method": getattr(request, "method", "") or "",
        "status": meta.http_status,
        "key": meta.key,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def render_status(request, key: str, http_status: int | None = None, extra: dict | None = None) -> HttpResponse:
    """Renderiza la página de estado/error. Nunca propaga: si el template falla,
    cae a una respuesta de texto plano para no romper la cadena de errores."""
    meta = get_meta(key, http_status)
    reference = build_reference(request, meta)
    ctx = {"meta": meta, "reference": reference, **(extra or {})}
    is_htmx = bool(getattr(request, "headers", None) and request.headers.get("HX-Request"))
    tpl = "system/_status_inline.html" if is_htmx else "system/status.html"
    try:
        # Sin `request=` a propósito: las plantillas no necesitan context
        # processors (forge_globals toca la BD), así el render no falla en un 500
        # por DB caída ni depende de la sesión.
        html = render_to_string(tpl, ctx)
    except Exception:  # noqa: BLE001 - último recurso, jamás dejar a Django sin respuesta
        html = (
            f"<h1>Error {meta.http_status}</h1><p>{meta.title}</p>"
            f"<pre>ref: {reference['reference_id']}</pre>"
        )
    return HttpResponse(html, status=meta.http_status)


# --- Handlers de error de Django (registrados en config/urls.py) ---
def bad_request(request, exception=None):
    return render_status(request, "http-400", 400)


def permission_denied(request, exception=None):
    return render_status(request, "http-403", 403)


def page_not_found(request, exception=None):
    return render_status(request, "http-404", 404)


def server_error(request):
    return render_status(request, "http-500", 500)
