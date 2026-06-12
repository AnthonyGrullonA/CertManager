"""Formularios de la app Grupos (Team)."""
from django import forms

from .models import Team

# Opciones de intervalo de chequeo por defecto (horas). Espejo del kit:
# "Cada 6 h" / "Diario". Se amplía con valores intermedios usables.
CHECK_INTERVAL_CHOICES = [
    (6, "Cada 6 h"),
    (12, "Cada 12 h"),
    (24, "Diario"),
    (48, "Cada 2 días"),
]

# Umbral por defecto (días) antes de marcar "Por vencer".
THRESHOLD_CHOICES = [
    (15, "15 días"),
    (30, "30 días"),
    (45, "45 días"),
    (60, "60 días"),
]


class TeamForm(forms.ModelForm):
    """Crear/editar un Grupo desde la capa web.

    Incluye `default_check_interval` (intervalo de chequeo) como Select y un
    campo opcional para designar el Admin responsable del grupo (Membership).
    """

    default_check_interval = forms.TypedChoiceField(
        label="Frecuencia",
        choices=CHECK_INTERVAL_CHOICES,
        coerce=int,
        initial=24,
    )
    default_threshold_days = forms.TypedChoiceField(
        label="Umbral por defecto",
        choices=THRESHOLD_CHOICES,
        coerce=int,
        initial=45,
    )
    admin = forms.ModelChoiceField(
        label="Admin responsable",
        queryset=None,
        required=False,
        empty_label="Selecciona",
    )
    default_email = forms.EmailField(
        label="Correo por defecto",
        required=False,
        help_text="Se usará como destinatario si el certificado no tiene correos propios.",
        widget=forms.EmailInput(attrs={"placeholder": "equipo@empresa.com"}),
    )

    class Meta:
        model = Team
        fields = [
            "name",
            "description",
            "default_threshold_days",
            "default_check_interval",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "p. ej. Plataforma"}),
            "description": forms.TextInput(
                attrs={"placeholder": "Para qué se usa este grupo"}
            ),
        }

    def __init__(self, *args, **kwargs):
        from django.contrib.auth import get_user_model

        super().__init__(*args, **kwargs)
        # Candidatos a Admin: usuarios activos de la organización.
        self.fields["admin"].queryset = get_user_model().objects.filter(
            is_active=True
        ).order_by("first_name", "email")
        if self.instance and self.instance.pk and self.instance.default_recipients:
            self.fields["default_email"].initial = self.instance.default_recipients[0]
        # Clase Forge para todos los controles.
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " input").strip()

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("El nombre del grupo es obligatorio.")
        return name

    def save(self, commit=True):
        team = super().save(commit=False)
        email = (self.cleaned_data.get("default_email") or "").strip().lower()
        team.default_recipients = [email] if email else []
        if commit:
            team.save()
        return team
