"""Formulario de alta de usuarios (PASO 10, pantalla Usuarios).

Solo el Owner accede a la pantalla de Usuarios, así que este formulario asume
contexto Owner. Aun así, NUNCA expone ``is_owner`` ni ``is_staff`` como campo:
no se permite mass-assignment del rol global desde el alta. El rol que se
pide aquí es el rol POR GRUPO (Membership: Miembro / Admin de grupo).
"""
from __future__ import annotations

from django import forms
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import User
from apps.core.enums import MembershipRole
from apps.teams.models import Team


class CreateUserForm(forms.Form):
    """Crear una persona en la organización y asignarla a grupos.

    Campos:
      - ``email``: correo de la persona (único).
      - ``password1`` / ``password2``: credencial local si no usará LDAP.
      - ``use_ldap``: crea el usuario local sin contraseña utilizable; el
        backend LDAP valida contra el directorio usando ese correo.
      - ``groups``: uno o varios grupos a los que se la agrega.
      - ``role``: rol de la persona en esos grupos (Membership). Por defecto
        Miembro. NO es el rol global (Owner); ese campo no existe a propósito.
    """

    email = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "persona@empresa.com",
                "class": "forge-input",
                "autocomplete": "off",
            }
        ),
    )
    password1 = forms.CharField(
        label="Contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Contraseña inicial",
                "class": "forge-input",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Repite la contraseña",
                "class": "forge-input",
                "autocomplete": "new-password",
            }
        ),
    )
    use_ldap = forms.BooleanField(
        label="Autenticar por LDAP",
        required=False,
        initial=False,
        help_text=(
            "Si está activo, se crea el usuario local y el login valida la "
            "contraseña contra LDAP usando este correo."
        ),
    )
    groups = forms.ModelMultipleChoiceField(
        label="Grupo",
        queryset=Team.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "forge-input"}),
    )
    role = forms.ChoiceField(
        label="Rol en el grupo",
        choices=MembershipRole.choices,
        initial=MembershipRole.VIEWER,
        widget=forms.Select(attrs={"class": "forge-input"}),
        help_text="Como Owner puedes asignar cualquier rol de grupo. "
        "El rol global Owner no se asigna desde aquí.",
    )
    def __init__(self, *args, **kwargs):
        # El queryset de grupos se inyecta desde la vista (todos para el Owner).
        groups_qs = kwargs.pop("groups_queryset", None)
        super().__init__(*args, **kwargs)
        if groups_qs is None:
            groups_qs = Team.objects.all().order_by("name")
        self.fields["groups"].queryset = groups_qs

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return email

    def clean(self):
        cleaned = super().clean()
        use_ldap = cleaned.get("use_ldap")
        password1 = cleaned.get("password1") or ""
        password2 = cleaned.get("password2") or ""

        if use_ldap:
            return cleaned

        if not password1:
            self.add_error("password1", "La contraseña es obligatoria para acceso local.")
            return cleaned
        if password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")
            return cleaned
        try:
            validate_password(password1)
        except forms.ValidationError as exc:
            self.add_error("password1", exc)
        return cleaned

    def save(self) -> User:
        """Crea el usuario y sus membresías.

        Si ``use_ldap`` está activo, el usuario queda sin contraseña local
        utilizable y el middleware/backend LDAP autentica por correo.
        ``is_owner`` queda en su valor por defecto (False).
        """
        from apps.teams.models import Membership

        email = self.cleaned_data["email"]
        if self.cleaned_data.get("use_ldap"):
            user = User.objects.create_user(email=email, password=None)
            user.set_unusable_password()
            user.save(update_fields=["password"])
        else:
            user = User.objects.create_user(email=email, password=self.cleaned_data["password1"])

        role = self.cleaned_data["role"]
        for team in self.cleaned_data["groups"]:
            Membership.objects.get_or_create(
                user=user, team=team, defaults={"role": role}
            )
        return user


# Alias temporal para no romper imports externos hasta que se renombre la URL.
InviteUserForm = CreateUserForm
