"""URLConf de prueba para la pantalla Perfil.

Combina las urls globales (dashboard, logout, certificate-list…) con las propias
de Perfil para que el Client resuelva ambos sets y los {% url %} rendericen.
Úsalo con @override_settings(ROOT_URLCONF='apps.web.test_urls_perfil').
"""
from config.urls import urlpatterns as _base

from apps.web.urls_perfil import urlpatterns as _mine

urlpatterns = _base + list(_mine)
