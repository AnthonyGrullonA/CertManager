"""URLs de la capa web (Forge UI) — cableado definitivo (PASO 14).

Promueve los names temporales de cada pantalla a sus names canónicos y registra
TODAS las rutas para que la app quede navegable end-to-end:

- ``dashboard`` (en ``''``): ``views_dashboard.DashboardView`` (Forge). Reemplaza
  la ``DashboardView`` transicional de ``views.py`` (eliminada).
- ``certificate-list`` (en ``certificates/``): ``views_certificates``
  ``CertificateListForgeView`` (Forge). Reemplaza la ``CertificateListView``
  transicional de ``views.py`` (eliminada).

El resto de pantallas se cablea por ``include`` de sus módulos ``urls_<slug>``,
que ya exponen sus names canónicos (alert-*, team-*, user-*, settings*, profile*,
report-*, cert-detail*, etc.). Las acciones de Certificados (cert-create,
cert-bulk, cert-export, cert-test) y Dashboard (dashboard-check-all) llegan por
los ``include`` de ``urls_certificates`` y ``urls_dashboard``.
"""
from django.urls import include, path

from .views_certificates import CertificateListForgeView
from .views_dashboard import DashboardView

urlpatterns = [
    # Names canónicos en sus rutas definitivas.
    path("", DashboardView.as_view(), name="dashboard"),
    path("certificates/", CertificateListForgeView.as_view(), name="certificate-list"),
    # Pantallas (cada módulo expone sus names canónicos).
    path("", include("apps.web.urls_dashboard")),     # dashboard-check-all
    path("", include("apps.web.urls_certificates")),  # cert-create/bulk/export/test (+ certificate-list-forge)
    path("", include("apps.web.urls_detalle")),       # cert-detail/-tab/-notify/-edit
    path("", include("apps.web.urls_alerts")),        # alert-list/-read/-dismiss/-read-all/-clear-panel/-panel
    path("", include("apps.web.urls_grupos")),        # team-list/-create
    path("", include("apps.web.urls_usuarios")),      # user-list/-invite/-toggle-active
    path("", include("apps.web.urls_config")),        # settings/-panel/-test-smtp/-test-webhook
    path("", include("apps.web.urls_perfil")),        # profile/-section/password-change
    path("", include("apps.web.urls_reportes")),      # report-list/-preview/-export/-create/-edit/-delete
    path("", include("apps.web.urls_apikeys")),       # api-keys/-create/-revoke + api-docs
    path("", include("apps.mailtemplates.urls")),     # mailtemplate-list/-create/-edit/-delete/-preview
    path("", include("apps.web.urls_faq")),           # faq (ayuda)
]
