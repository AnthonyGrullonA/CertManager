"""Formularios de la pantalla Perfil (paso 12).

Cada sección guarda de forma parcial sobre ``UserPreferences`` (y, en el caso de
"Datos personales", sobre el propio ``User``). Los formularios son pequeños y
disjuntos para que un guardado parcial no toque campos de otras secciones.
"""
from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm

from .models import UserPreferences

User = get_user_model()


# Idiomas y zonas horarias que ofrecemos en la UI (es-DO primero).
LANGUAGE_CHOICES = [
    ("es-do", "Español"),
    ("en", "English"),
]

TIMEZONE_CHOICES = [
    ("America/Santo_Domingo", "Santo Domingo (UTC-4)"),
    ("UTC", "UTC"),
]


class PersonalDataForm(forms.ModelForm):
    """Datos personales editables: nombre y correo del usuario."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo",
        }

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email


class PreferencesForm(forms.ModelForm):
    """Idioma y zona horaria."""

    language = forms.ChoiceField(choices=LANGUAGE_CHOICES, label="Idioma")
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES, label="Zona horaria")

    class Meta:
        model = UserPreferences
        fields = ["language", "timezone"]


class AvatarChoiceForm(forms.ModelForm):
    """Selección de un avatar SVG generado (índice 1..AVATAR_COUNT).

    No existe el estado "sin avatar": todo usuario tiene uno asignado, así que
    0 se rechaza. No hay subida de fotos. El índice se valida contra el
    catálogo de avatares para no persistir basura.
    """

    class Meta:
        model = UserPreferences
        fields = ["avatar_choice"]

    def clean_avatar_choice(self):
        # Import perezoso: el catálogo vive en la capa web (templatetag).
        from apps.web.templatetags.forge_avatars import AVATAR_COUNT

        value = self.cleaned_data.get("avatar_choice") or 0
        if value < 1 or value > AVATAR_COUNT:
            raise forms.ValidationError("Avatar no válido.")
        return value


class ProfilePasswordChangeForm(PasswordChangeForm):
    """Cambio de contraseña; reusa la validación de Django."""
