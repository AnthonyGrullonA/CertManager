"""Formularios de la pantalla Reportes (constructor + reportes programados).

- ``ReportBuilderForm`` valida los filtros del constructor para la preview/export
  en vivo. No persiste nada; solo normaliza la entrada del usuario.
- ``ScheduledReportForm`` es el ModelForm del CRUD de reportes programados
  (``ScheduledReport``): plantilla, frecuencia, hora de envío, lista de formatos
  (multi-formato) y destinatarios. El scoping de ``team`` se restringe a los
  grupos visibles del usuario que edita.
"""
from __future__ import annotations

from django import forms

from apps.core.enums import (
    CertificateStatus,
    ReportFormat,
    ReportFrequency,
    ReportTemplate,
)
from apps.teams.models import Team

from .models import ScheduledReport
from .services import DATE_RANGES


class ReportBuilderForm(forms.Form):
    """Filtros del constructor de reportes (no persiste)."""

    template = forms.ChoiceField(
        label="Plantilla",
        choices=ReportTemplate.choices,
        required=False,
        initial=ReportTemplate.INVENTORY,
    )
    date_range = forms.ChoiceField(
        label="Rango de fechas",
        choices=[(k, k) for k in DATE_RANGES],
        required=False,
        initial="30",
    )
    date_from = forms.DateField(label="Desde", required=False)
    date_to = forms.DateField(label="Hasta", required=False)
    teams = forms.MultipleChoiceField(label="Grupos", required=False)
    statuses = forms.MultipleChoiceField(
        label="Estado",
        choices=CertificateStatus.choices,
        required=False,
    )
    expiry_window = forms.ChoiceField(
        label="Ventana de vencimiento",
        choices=[("", "Cualquiera"), ("7", "≤ 7 días"), ("15", "≤ 15 días"), ("30", "≤ 30 días"), ("90", "≤ 90 días")],
        required=False,
    )
    issuer = forms.CharField(label="Emisor", required=False, max_length=255)
    recipient = forms.CharField(label="Responsable", required=False, max_length=255)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        teams = Team.objects.for_user(user) if user is not None else Team.objects.none()
        self.fields["teams"].choices = [(str(t.id), t.name) for t in teams]
        # Estilo Forge UI: clase .input en los widgets de texto/selección.
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxSelectMultiple,)):
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = (css + " input").strip()
            if isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault("size", "4")


class ScheduledReportForm(forms.ModelForm):
    """CRUD de reportes programados (modal). Multi-formato + hora de envío."""

    formats = forms.MultipleChoiceField(
        label="Formato(s) adjunto(s)",
        choices=ReportFormat.choices,
        required=True,
        widget=forms.CheckboxSelectMultiple,
        help_text="Multi-formato simultáneo permitido (PDF + Excel + CSV).",
    )
    recipients_text = forms.CharField(
        label="Destinatarios",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "usuarios, correos o grupo (uno por línea o separados por comas)"}),
        help_text="Ej. Admins de cada grupo. Separa con coma o salto de línea.",
    )

    class Meta:
        model = ScheduledReport
        fields = [
            "name", "template", "frequency", "start_date", "interval_days",
            "send_time", "team", "email_template", "is_active",
        ]
        labels = {
            "name": "Nombre",
            "template": "Plantilla",
            "email_template": "Plantilla de correo",
            "frequency": "Frecuencia",
            "start_date": "Fecha de inicio",
            "interval_days": "Intervalo (días)",
            "send_time": "Hora de envío",
            "team": "Grupo",
            "is_active": "Activo",
        }
        widgets = {
            "send_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "interval_days": forms.NumberInput(attrs={"min": 1, "placeholder": "p.ej. 15 o 30"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        # Restringe los grupos seleccionables a los visibles del usuario.
        if user is not None:
            self.fields["team"].queryset = Team.objects.for_user(user)
        self.fields["team"].required = False
        self.fields["team"].empty_label = "Todos los grupos"

        # Plantilla de correo (kind=REPORT). Opcional: vacío => texto plano.
        from apps.mailtemplates.models import EmailTemplate

        self.fields["email_template"].queryset = EmailTemplate.objects.usable(kind="REPORT")
        self.fields["email_template"].required = False
        self.fields["email_template"].empty_label = "Texto plano (predeterminado)"

        # Estilo Forge UI en los widgets de texto/selección del modal.
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxSelectMultiple, forms.CheckboxInput)):
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = (css + " input w-full").strip()

        # Hidrata campos derivados al editar.
        if self.instance and self.instance.pk:
            self.fields["formats"].initial = self.instance.formats or [self.instance.output_format]
            self.fields["recipients_text"].initial = "\n".join(self.instance.recipients or [])

    def clean(self):
        cleaned = super().clean()
        from apps.core.enums import ReportFrequency

        freq = cleaned.get("frequency")
        if freq == ReportFrequency.EVERY_N_DAYS:
            if not cleaned.get("interval_days"):
                self.add_error("interval_days", "Indica cada cuántos días (p.ej. 15 o 30).")
            if not cleaned.get("start_date"):
                self.add_error("start_date", "Elige la fecha desde la que empieza a contar.")
        return cleaned

    def clean_recipients_text(self):
        raw = self.cleaned_data.get("recipients_text", "") or ""
        parts = []
        for chunk in raw.replace(",", "\n").splitlines():
            value = chunk.strip()
            if value and value not in parts:
                parts.append(value)
        return parts

    def save(self, commit=True):
        obj = super().save(commit=False)
        formats = self.cleaned_data.get("formats") or []
        obj.formats = list(formats)
        # Mantén output_format (compatibilidad) sincronizado con el primer formato.
        if formats:
            obj.output_format = formats[0]
        obj.recipients = self.cleaned_data.get("recipients_text") or []
        if self.user is not None and obj.created_by_id is None:
            obj.created_by = self.user
        if commit:
            obj.save()
        return obj
