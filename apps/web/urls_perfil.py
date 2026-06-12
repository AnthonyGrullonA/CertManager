"""URLs de la pantalla Perfil (paso 12).

Names expuestos: ``profile``, ``profile-section``, ``password-change``.
El cableado real en ``apps/web/urls.py`` se integra en el paso 14.
"""
from django.urls import path

from .views_2fa import two_factor_confirm, two_factor_disable, two_factor_setup
from .views_perfil import ProfileView, password_change, profile_section

urlpatterns = [
    path("perfil/", ProfileView.as_view(), name="profile"),
    path("perfil/seccion/<str:section>/", profile_section, name="profile-section"),
    path("perfil/contrasena/", password_change, name="password-change"),
    path("perfil/2fa/activar/", two_factor_setup, name="two-factor-setup"),
    path("perfil/2fa/confirmar/", two_factor_confirm, name="two-factor-confirm"),
    path("perfil/2fa/desactivar/", two_factor_disable, name="two-factor-disable"),
]
