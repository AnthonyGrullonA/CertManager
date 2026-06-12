"""ROOT_URLCONF de prueba: urls globales + Certificados (PASO 7) + Detalle (PASO 8).

Se incluyen también las del PASO 7 porque el detalle enlaza ``cert-test`` (drawer
"Probar ahora") y ``cert-create``; así los ``{% url %}`` resuelven en los tests.
"""
from config.urls import urlpatterns as _base
from apps.web.urls_certificates import urlpatterns as _certs
from apps.web.urls_detalle import urlpatterns as _mine

urlpatterns = _base + list(_certs) + list(_mine)
