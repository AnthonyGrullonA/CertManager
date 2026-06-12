"""ROOT_URLCONF de pruebas para el Dashboard Forge UI (PASO 6).

Combina las urls globales (dashboard, certificate-list, logout…) con las propias
de esta pantalla para que el ``Client`` resuelva ambos y los ``{% url %}`` de las
plantillas rendericen. Usar con::

    @override_settings(ROOT_URLCONF="apps.web.test_urls_dashboard")
"""
from config.urls import urlpatterns as _base

from apps.web.urls_dashboard import urlpatterns as _mine

urlpatterns = _base + list(_mine)
