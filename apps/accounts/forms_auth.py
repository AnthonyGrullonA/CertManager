"""Formularios de autenticación de CertManager (Forge UI).

``EmailAuthenticationForm`` reetiqueta el campo de credencial como **"Correo"**
porque el modelo de usuario usa ``USERNAME_FIELD = "email"``. Mantiene el
``name=username`` que espera ``django.contrib.auth`` (y los backends, incluido
``LDAPBackend``), de modo que la integración no cambia: solo cambia la UI.
"""
from __future__ import annotations

from django.contrib.auth.forms import AuthenticationForm
from django.forms import EmailInput, PasswordInput, TextInput


class EmailAuthenticationForm(AuthenticationForm):
    """Login por correo. El campo sigue llamándose ``username`` en el POST.

    Se mantiene el nombre ``username`` (no se renombra a ``email``) para no
    romper ``AuthenticationForm`` ni los backends de autenticación: tanto
    ``ModelBackend`` (usuario local, ``USERNAME_FIELD = "email"``) como
    ``django_auth_ldap.backend.LDAPBackend`` (SSO corporativo) reciben el valor
    por la clave ``username``.
    """

    # Mensaje de credenciales en español (genérico, no revela si el correo
    # existe — OWASP A07). El bloqueo por fuerza bruta usa su propio mensaje.
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Credenciales inválidas. Verifica tu correo y contraseña.",
        "inactive": "Esta cuenta está desactivada.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reetiquetar a "Correo" (es-DO) sin tocar el name del campo.
        self.fields["username"].label = "Correo"
        # Widgets como <input type=email/password>; el markup Forge UI vive en la
        # plantilla, aquí solo damos los atributos imprescindibles.
        self.fields["username"].widget = EmailInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": "tu@empresa.com",
                "inputmode": "email",
            }
        )
        self.fields["password"].widget = PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "••••••••",
            }
        )
        # Defensa: si por alguna razón el username dejara de ser email, el widget
        # de texto plano sigue funcionando.
        if not isinstance(self.fields["username"].widget, (EmailInput, TextInput)):
            self.fields["username"].widget = TextInput()
