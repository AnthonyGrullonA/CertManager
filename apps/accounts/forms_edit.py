"""Formulario de edición de usuario (pantalla Usuarios, solo Owner).

Permite editar datos básicos (nombre, apellido), el estado de la cuenta
(``is_active``) y la pertenencia a grupos con un rol común de grupo.

ANTI-ESCALADA: este formulario NUNCA expone ``is_owner`` ni ``is_staff`` como
campo. No es posible auto-promoverse a Owner desde aquí, ni promover a otra
persona, porque el rol global no se incluye en ``Meta.fields`` ni se asigna en
``save()``. El rol que se pide es el rol POR GRUPO (Membership), no el global.
"""
from __future__ import annotations

from django import forms

from apps.accounts.models import User
from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team


class UserEditForm(forms.ModelForm):
    """Editar nombre, apellido, estado y grupos/rol de grupo de un usuario.

    Campos:
      - ``first_name`` / ``last_name``: datos de la persona.
      - ``is_active``: cuenta activa o no.
      - ``groups``: grupos a los que pertenece (Membership).
      - ``role``: rol que tendrá en esos grupos (Membership). NO es el rol
        global Owner; ese campo no existe a propósito (anti-escalada).
    """

    groups = forms.ModelMultipleChoiceField(
        label="Grupos",
        queryset=Team.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    role = forms.ChoiceField(
        label="Rol en los grupos",
        choices=MembershipRole.choices,
        initial=MembershipRole.VIEWER,
        widget=forms.Select(attrs={"class": "input"}),
        help_text="El rol global Owner no se edita desde aquí.",
    )

    class Meta:
        model = User
        # is_owner / is_staff quedan FUERA a propósito: anti-escalada.
        fields = ["first_name", "last_name", "is_active"]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "is_active": "Cuenta activa",
        }
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "input", "autocomplete": "off"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "input", "autocomplete": "off"}
            ),
        }

    def __init__(self, *args, **kwargs):
        # El queryset de grupos se inyecta desde la vista (todos para el Owner).
        groups_qs = kwargs.pop("groups_queryset", None)
        super().__init__(*args, **kwargs)
        if groups_qs is None:
            groups_qs = Team.objects.all().order_by("name")
        self.fields["groups"].queryset = groups_qs

        if self.instance and self.instance.pk:
            memberships = list(
                self.instance.memberships.select_related("team").all()
            )
            self.fields["groups"].initial = [m.team_id for m in memberships]
            # Rol inicial: el más común entre sus membresías (o Miembro).
            if memberships:
                self.fields["role"].initial = memberships[0].role

    def save(self, commit: bool = True) -> User:
        """Guarda los datos básicos y reconcilia las membresías de grupo.

        ``is_owner`` no se toca jamás: no está en ``fields`` ni se asigna aquí,
        así que no hay forma de promoverse desde este formulario.
        """
        user = super().save(commit=commit)

        if commit:
            self._sync_memberships(user)
        return user

    def _sync_memberships(self, user: User) -> None:
        """Crea/actualiza/elimina membresías para coincidir con el formulario."""
        selected = list(self.cleaned_data.get("groups") or [])
        role = self.cleaned_data["role"]
        selected_ids = {t.pk for t in selected}

        existing = {m.team_id: m for m in user.memberships.all()}

        # Elimina membresías de grupos deseleccionados.
        for team_id, membership in existing.items():
            if team_id not in selected_ids:
                membership.delete()

        # Crea o actualiza las seleccionadas con el rol elegido.
        for team in selected:
            membership = existing.get(team.pk)
            if membership is None:
                Membership.objects.create(user=user, team=team, role=role)
            elif membership.role != role:
                membership.role = role
                membership.save(update_fields=["role"])
