"""Rutas de autenticación (Forge UI).

Expone únicamente el ``login`` con ``CustomLoginView`` (recordarme +
``EmailAuthenticationForm``, que prueba ModelBackend y luego LDAP de forma
automática) y el ``logout``. No hay flujo de restablecimiento de contraseña en
esta pantalla: el usuario pidió un único botón de inicio de sesión, sin SSO
aparte ni enlace de recuperación.

Se cablea en ``config/urls.py`` ANTES de cualquier otra ruta para que ``login``
resuelva a la vista Forge.
"""
from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import path

from apps.accounts.views import CustomLoginView, ForcePasswordChangeView
from apps.web.views_2fa import two_factor_verify

urlpatterns = [
    path("accounts/login/", CustomLoginView.as_view(), name="login"),
    # Segundo paso del login (verificación TOTP) para usuarios con 2FA activo.
    path("accounts/2fa/", two_factor_verify, name="two-factor-verify"),
    # Contraseña temporal (reset del Owner): definir la propia antes de seguir.
    path(
        "accounts/cambiar-contrasena/",
        ForcePasswordChangeView.as_view(),
        name="password-force-change",
    ),
    # Tras cerrar sesión, vuelve al login con ?logout=1 para mostrar el aviso de
    # "Sesión cerrada" (la sesión se limpia en logout, por eso no se usa messages).
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="/accounts/login/?logout=1"),
        name="logout",
    ),
]
