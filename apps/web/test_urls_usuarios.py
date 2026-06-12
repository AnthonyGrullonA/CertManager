"""ROOT_URLCONF de prueba para la pantalla Usuarios (sin tocar urls compartidas).

Combina las urls globales (dashboard, logout, certificate-list…) con las propias
de Usuarios para que el Client resuelva ambas y los ``{% url %}`` rendericen.
"""
from config.urls import urlpatterns as _base

from apps.web.urls_usuarios import urlpatterns as _mine

urlpatterns = _base + list(_mine)
