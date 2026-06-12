"""Formulario del builder de plantillas. ``blocks`` viaja como JSON en un input
oculto que serializa el builder JS; se valida estructura + campos obligatorios."""
from __future__ import annotations

import json

from django import forms

from apps.teams.models import Team

from .models import EmailTemplate
from .variables import mandatory_fields


class EmailTemplateForm(forms.ModelForm):
    blocks_json = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = EmailTemplate
        fields = ["name", "kind", "team", "subject", "is_default", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Nombre de la plantilla"}),
            "subject": forms.TextInput(attrs={"placeholder": "Asunto (admite {{variables}})"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # `team` es solo etiqueta organizativa; se ofrecen los grupos visibles.
        team_qs = Team.objects.all()
        if user is not None and not getattr(user, "is_owner", False):
            team_qs = Team.objects.for_user(user)
        self.fields["team"].queryset = team_qs.order_by("name")
        self.fields["team"].required = False
        self.fields["team"].label = "Etiqueta (grupo)"
        self.fields["team"].empty_label = "— Sin etiqueta —"
        if self.instance and self.instance.pk:
            self.fields["blocks_json"].initial = json.dumps(self.instance.blocks or [])
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
                continue
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " input").strip()

    def clean(self):
        cleaned = super().clean()
        raw = cleaned.get("blocks_json") or "[]"
        try:
            blocks = json.loads(raw)
            if not isinstance(blocks, list):
                raise ValueError
        except (ValueError, TypeError):
            self.add_error("blocks_json", "Estructura de bloques inválida.")
            blocks = []
        self._blocks = blocks
        # Fija los bloques en la instancia ANTES de que el ModelForm corra
        # ``EmailTemplate.clean`` (valida los obligatorios sobre los bloques reales).
        self.instance.blocks = blocks
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.blocks = getattr(self, "_blocks", [])
        if commit:
            obj.save()
        return obj
