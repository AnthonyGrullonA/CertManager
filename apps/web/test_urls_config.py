"""ROOT_URLCONF de pruebas para Configuración (PASO 11).

Combina las urls globales (dashboard, certificate-list, logout…) con las de este
paso, para que el Client resuelva todo y los ``{% url %}`` rendericen. Se activa
en los tests con ``@override_settings(ROOT_URLCONF='apps.web.test_urls_config')``.
"""
from config.urls import urlpatterns as _base
from apps.web.urls_config import urlpatterns as _mine

urlpatterns = _base + list(_mine)
