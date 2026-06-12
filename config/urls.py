"""URLs raíz de CertForge: admin, API y web."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import health

# Defensa en profundidad: el admin de Django solo lo ve el superusuario real.
# (El AdminAccessMiddleware ya redirige a no-superusers; esto bloquea además a
# nivel del propio AdminSite, patrón recomendado.)
admin.site.has_permission = lambda request: bool(
    request.user.is_active and request.user.is_superuser
)

# Branding del admin acorde a la marca (oculta el wordmark del framework).
admin.site.site_header = "CertManager · Administración"
admin.site.site_title = "CertManager"
admin.site.index_title = "Panel de administración"

# Handlers de error centralizados (apps.core.errors → templates/system/*).
# No afecta a /api/ (DRF mantiene sus errores JSON). Solo actúan con DEBUG=False.
handler400 = "apps.core.errors.bad_request"
handler403 = "apps.core.errors.permission_denied"
handler404 = "apps.core.errors.page_not_found"
handler500 = "apps.core.errors.server_error"

urlpatterns = [
    # Healthcheck sin auth (Docker HEALTHCHECK / orquestadores).
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    # Documentación OpenAPI/Swagger (navegable, gateada por login de sesión).
    path(
        "api/schema/",
        login_required(SpectacularAPIView.as_view(authentication_classes=[], permission_classes=[])),
        name="api-schema",
    ),
    path(
        "api/docs/",
        login_required(SpectacularSwaggerView.as_view(url_name="api-schema")),
        name="api-docs",
    ),
    # Autenticación con templates Forge UI: CustomLoginView (login) y logout.
    path("", include("apps.web.urls_login")),
    # Web (templates Forge UI): dashboard, certificados, alertas, grupos,
    # usuarios, configuración, perfil, reportes y detalle.
    path("", include("apps.web.urls")),
]

# Servir archivos subidos (avatares, logo) en desarrollo. En producción los
# sirve el servidor de estáticos/almacenamiento.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
