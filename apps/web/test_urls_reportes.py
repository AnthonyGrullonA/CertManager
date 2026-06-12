"""ROOT_URLCONF de pruebas para la pantalla Reportes (PASO 13).

Suma las rutas de Reportes a las urls globales para que el Client resuelva tanto
las urls compartidas (dashboard, certificate-list…) como las nuevas, sin tocar
``config/urls.py`` (que se cablea en el PASO 14).
"""
from config.urls import urlpatterns as _base

from apps.web.urls_reportes import urlpatterns as _mine

urlpatterns = _base + list(_mine)
