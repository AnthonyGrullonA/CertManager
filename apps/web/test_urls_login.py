"""URLconf de prueba para la pantalla Login (PASO 4).

Combina las rutas globales (dashboard, logout, certificate-list…) con las de
login/reset propias de este paso. ``_mine`` va **primero** para que ``login`` y
``password_reset*`` resuelvan a ``CustomLoginView`` y a las vistas con templates
Forge UI (de lo contrario ganarían las de ``django.contrib.auth.urls``, ya
incluidas en ``config.urls``).

Se usa con ``@override_settings(ROOT_URLCONF='apps.web.test_urls_login')``.
"""
from apps.web.urls_login import urlpatterns as _mine
from config.urls import urlpatterns as _base

urlpatterns = list(_mine) + list(_base)
