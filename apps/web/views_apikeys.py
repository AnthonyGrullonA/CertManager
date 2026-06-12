"""Aprovisionamiento de API keys (solo Owner) + página de documentación de la API.

Al crear una clave se muestra UNA sola vez el secreto completo junto con la URL
base y un ejemplo de uso (todo lo necesario para consumir la API).
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from apps.core.enums import ApiKeyScope
from apps.core.models import ApiKey, ApiKeyUsage


class _OwnerOnly(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not request.user.is_owner:
            raise PermissionDenied(_("Solo el Owner puede gestionar claves de API."))
        return super().dispatch(request, *args, **kwargs)


def _api_base(request):
    return request.build_absolute_uri("/api/").rstrip("/")


class ApiKeysView(_OwnerOnly, TemplateView):
    """Lista de claves + formulario de creación + URL base."""

    template_name = "apikeys/list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["keys"] = ApiKey.objects.filter(created_by__isnull=False).select_related("created_by")
        ctx["scopes"] = ApiKeyScope.choices
        ctx["api_base"] = _api_base(self.request)
        ctx["docs_url"] = reverse("api-docs")
        return ctx


class ApiKeyCreateView(_OwnerOnly, View):
    """Crea una clave y muestra el secreto completo UNA vez + cómo usarla."""

    def post(self, request):
        name = (request.POST.get("name") or "").strip() or "Clave sin nombre"
        scope = request.POST.get("scope")
        if scope not in ApiKeyScope.values:
            scope = ApiKeyScope.READ_ONLY

        obj, raw = ApiKey.generate(name=name, scope=scope, user=request.user)
        return render(
            request,
            "apikeys/_created.html",
            {
                "key": obj,
                "raw_key": raw,            # se muestra solo aquí, nunca más
                "api_base": _api_base(request),
                "docs_url": reverse("api-docs"),
            },
        )


class ApiKeyRevokeView(_OwnerOnly, View):
    """Revoca (desactiva) una clave sin borrar el registro."""

    def post(self, request, pk):
        key = get_object_or_404(ApiKey, pk=pk)
        key.is_active = False
        key.save(update_fields=["is_active", "updated_at"])
        return render(request, "apikeys/_row.html", {"key": key, "revoked": True})


class ApiKeyUsageView(_OwnerOnly, View):
    """Registro de uso (Owner) de UNA clave: fecha, método, ruta, IP.

    Responde con el parcial de la tabla (paginación/orden client-side vía
    ForgeDataTable). Es el target HTMX del botón «Ver uso» de cada fila.
    """

    def get(self, request, pk):
        key = get_object_or_404(ApiKey, pk=pk)
        usages = ApiKeyUsage.objects.filter(api_key=key).order_by("-at")
        return render(
            request,
            "apikeys/_usage.html",
            {"key": key, "usages": usages, "as_modal": True},
        )


class ApiDocsView(LoginRequiredMixin, TemplateView):
    """Documentación de la API (autenticación por API key, endpoints, ejemplos)."""

    template_name = "apidocs/docs.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["api_base"] = _api_base(self.request)
        ctx["can_manage_keys"] = self.request.user.is_owner
        ctx["endpoints"] = [
            {"method": "GET", "path": "/certificates/", "desc": "Lista de certificados (filtros: status, team, is_active; búsqueda; orden)."},
            {"method": "POST", "path": "/certificates/", "desc": "Crear un certificado (requiere clave de acceso total)."},
            {"method": "GET", "path": "/certificates/{id}/", "desc": "Detalle de un certificado."},
            {"method": "POST", "path": "/certificates/{id}/test/", "desc": "Probar ahora: chequeo SSL inmediato (acceso total)."},
            {"method": "GET", "path": "/certificates/{id}/checks/", "desc": "Historial de chequeos del certificado."},
            {"method": "GET", "path": "/teams/", "desc": "Grupos visibles para la clave."},
            {"method": "GET", "path": "/alerts/", "desc": "Alertas del ámbito (filtros: severity, status)."},
        ]
        return ctx
