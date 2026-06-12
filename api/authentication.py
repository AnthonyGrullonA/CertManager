"""Autenticación de la API REST por API key.

Acepta la clave en una de dos formas:
    Authorization: Api-Key cf_live_xxx
    X-Api-Key: cf_live_xxx

Autentica como el usuario dueño de la clave; el ámbito (full / read_only) queda en
``request.auth`` (la propia ApiKey) y lo aplica ``ApiKeyScopePermission``.
"""
import logging

from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.core.models import ApiKey

logger = logging.getLogger("certmanager.api")


class ApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = b"api-key"

    def authenticate(self, request):
        raw = None
        header = authentication.get_authorization_header(request).split()
        if header and header[0].lower() == self.keyword:
            if len(header) == 1:
                raise exceptions.AuthenticationFailed("Falta la clave tras 'Api-Key'.")
            if len(header) > 2:
                raise exceptions.AuthenticationFailed("Encabezado de API key inválido.")
            raw = header[1].decode()
        else:
            raw = request.META.get("HTTP_X_API_KEY")

        if not raw:
            return None  # deja paso a otros métodos (sesión/Token) o a 401

        api_key = ApiKey.lookup(raw)
        if api_key is None:
            raise exceptions.AuthenticationFailed("API key inválida o revocada.")
        if not api_key.created_by.is_active:
            raise exceptions.AuthenticationFailed("El usuario de la clave está inactivo.")

        # Marca de último uso + registro de la petición (auditoría de uso).
        ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")) or None

        # Log estructurado de la petición a la API: va a stdout/Loki (y, si obsforge
        # está activo, se sintetiza por el bridge del root). Es el espejo en el flujo
        # de logs de lo que ApiKeyUsage guarda en la BD: queda QUIÉN (key + usuario),
        # con qué ámbito y desde dónde llamó cada endpoint.
        logger.info(
            "api:%s %s",
            request.method,
            request.path,
            extra={
                "event": "api_request",
                "method": request.method,
                "path": request.path[:255],
                "actor_email": api_key.created_by.email,
                "api_key": api_key.name,
                "scope": api_key.scope,
                "ip": ip,
            },
        )
        try:
            from apps.core.models import ApiKeyUsage

            ApiKeyUsage.objects.create(
                api_key=api_key,
                method=request.method,
                path=request.path[:255],
                ip=ip,
            )
        except Exception:  # noqa: BLE001 — el registro de uso nunca debe romper la auth
            pass
        return (api_key.created_by, api_key)

    def authenticate_header(self, request):
        return "Api-Key"


# --- Documentación: declara el esquema de seguridad por API key en OpenAPI ---
try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class ApiKeyAuthScheme(OpenApiAuthenticationExtension):
        target_class = "api.authentication.ApiKeyAuthentication"
        name = "ApiKeyAuth"

        def get_security_definition(self, auto_schema):
            return {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "Clave de API. Formato: 'Api-Key cf_live_…' (acceso total) "
                "o 'cf_ro_…' (solo lectura). También se acepta la cabecera 'X-Api-Key'.",
            }
except ImportError:  # drf-spectacular no instalado (entorno mínimo): sin docs.
    pass
