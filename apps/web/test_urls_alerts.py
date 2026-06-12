"""ROOT_URLCONF de prueba para el Centro de Alertas (PASO 5).

Compone las urls globales (dashboard, logout, certificate-list…) con las propias
del módulo de alertas, sin tocar las urls compartidas (que se cablean en el
PASO 14). Los tests usan
``@override_settings(ROOT_URLCONF='apps.web.test_urls_alerts')`` para que el
Client resuelva ambas y los ``{% url %}`` de las plantillas rendericen.
"""
from config.urls import urlpatterns as _base

from apps.web.urls_alerts import urlpatterns as _mine

urlpatterns = _base + list(_mine)
