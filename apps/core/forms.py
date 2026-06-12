"""Formularios de Configuración (PASO 11).

Cinco formularios sobre el singleton ``OrganizationSettings`` (uno por panel
HTMX) + un formulario auxiliar de integraciones que mapea sobre el primer
``WebhookIntegration`` global (Slack/Teams).

Regla de **secretos write-only** (decisión 14 del plan): ni ``smtp_password`` ni
la URL del webhook se exponen nunca en claro en la UI. En el formulario:

- el campo del secreto es ``required=False`` y se renderiza con placeholder
  enmascarado (la plantilla muestra "●●● configurado" si ya hay valor);
- al guardar, **un valor vacío conserva el secreto previo** (no lo borra).

Las clases CSS aplicadas son las ya compiladas en ``forge.css`` (``input``), de
modo que este paso no toca el bundle de estilos.
"""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _l

from apps.alerts.models import WebhookIntegration
from apps.core.enums import WebhookType
from apps.core.models import LdapConfiguration, OrganizationSettings, SmsGatewayConfig

# Marcador que la plantilla usa para indicar "hay un secreto guardado" sin
# revelarlo. El POST que reenvía este valor textual se trata como "sin cambios".
SECRET_PLACEHOLDER = "●●● configurado"

_INPUT = "input w-full"
_INPUT_SM = "input"
_INPUT_NUMERIC = "input settings-number-input"
_INPUT_SELECT_COMPACT = "input settings-select-compact"


class _SettingsModelForm(forms.ModelForm):
    """Base: ``ModelForm`` sobre el singleton, con clases Forge UI por defecto."""

    class Meta:
        model = OrganizationSettings
        fields: list[str] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = (css + " " + _INPUT).strip()


# ---------------------------------------------------------------------------
# Panel: Monitoreo
# ---------------------------------------------------------------------------
class MonitoreoSettingsForm(_SettingsModelForm):
    class Meta(_SettingsModelForm.Meta):
        fields = [
            "check_interval_hours",
            "connect_timeout",
            "retries",
            "preferred_check_window_start",
            "preferred_check_window_end",
        ]
        widgets = {
            "preferred_check_window_start": forms.TimeInput(
                attrs={"type": "time"}, format="%H:%M"
            ),
            "preferred_check_window_end": forms.TimeInput(
                attrs={"type": "time"}, format="%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preferred_check_window_start"].input_formats = ["%H:%M"]
        self.fields["preferred_check_window_end"].input_formats = ["%H:%M"]
        for name in ("check_interval_hours", "connect_timeout", "retries"):
            self.fields[name].widget.attrs["class"] = _INPUT_NUMERIC
            self.fields[name].widget.attrs["inputmode"] = "numeric"


# ---------------------------------------------------------------------------
# Panel: SMTP (secreto write-only)
# ---------------------------------------------------------------------------
class SmtpSettingsForm(_SettingsModelForm):
    # El secreto NO se vincula al modelo (excluido de Meta.fields): se gestiona a
    # mano para garantizar el comportamiento write-only.
    smtp_password = forms.CharField(
        label="Contraseña",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": SECRET_PLACEHOLDER},
        ),
    )

    class Meta(_SettingsModelForm.Meta):
        fields = [
            "smtp_host",
            "smtp_port",
            "smtp_user",
            "smtp_from",
            "smtp_use_tls",
            "email_copy_enabled",
            "email_copy_address",
        ]

    @property
    def has_password(self) -> bool:
        """¿Existe un secreto guardado? (para mostrar '●●● configurado')."""
        return bool(self.instance and self.instance.smtp_password)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Write-only: solo sobreescribir si el usuario tecleó algo nuevo.
        new_secret = self.cleaned_data.get("smtp_password", "")
        if new_secret:
            instance.smtp_password = new_secret
        # Si viene vacío -> se conserva el valor previo (no se toca).
        if commit:
            instance.save()
        return instance


# ---------------------------------------------------------------------------
# Panel: Integraciones (webhooks Teams/Slack; URL write-only)
# ---------------------------------------------------------------------------
class IntegracionesSettingsForm(forms.Form):
    """Webhooks globales Slack/Teams sobre ``WebhookIntegration``.

    La URL es un secreto: el GET nunca la devuelve; un POST con la URL vacía
    conserva la previa.
    """

    slack_url = forms.URLField(
        label="URL del webhook (Slack)",
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(
            attrs={"class": _INPUT, "placeholder": SECRET_PLACEHOLDER}
        ),
    )
    teams_url = forms.URLField(
        label="URL del webhook (Teams)",
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(
            attrs={"class": _INPUT, "placeholder": SECRET_PLACEHOLDER}
        ),
    )
    rich_format = forms.BooleanField(label="Formato enriquecido", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slack = self._get_or_none(WebhookType.SLACK)
        self.teams = self._get_or_none(WebhookType.TEAMS)
        if not self.is_bound:
            # Nunca prellenar las URLs (write-only). Solo el toggle.
            initial_rich = bool(
                (self.slack and self.slack.rich_format)
                or (self.teams and self.teams.rich_format)
            )
            self.fields["rich_format"].initial = initial_rich

    @staticmethod
    def _get_or_none(webhook_type):
        return (
            WebhookIntegration.objects.filter(team__isnull=True, webhook_type=webhook_type)
            .order_by("id")
            .first()
        )

    @property
    def has_slack(self) -> bool:
        return bool(self.slack and self.slack.url)

    @property
    def has_teams(self) -> bool:
        return bool(self.teams and self.teams.url)

    def _upsert(self, existing, webhook_type, url, rich):
        """Crea/actualiza la integración respetando el secreto write-only."""
        if existing is None:
            if not url:
                return  # nada que crear sin URL
            WebhookIntegration.objects.create(
                team=None,
                webhook_type=webhook_type,
                name=webhook_type.label if hasattr(webhook_type, "label") else str(webhook_type),
                url=url,
                rich_format=rich,
            )
            return
        if url:
            existing.url = url
        existing.rich_format = rich
        existing.save()

    def save(self):
        rich = self.cleaned_data.get("rich_format", False)
        self._upsert(
            self.slack, WebhookType.SLACK, self.cleaned_data.get("slack_url", ""), rich
        )
        self._upsert(
            self.teams, WebhookType.TEAMS, self.cleaned_data.get("teams_url", ""), rich
        )


# ---------------------------------------------------------------------------
# Panel: Seguridad (2FA/SSO = 'Próximamente'; solo el toggle LDAP es real)
# ---------------------------------------------------------------------------
# Períodos de expiración de contraseña ofrecidos en el panel de Seguridad.
PASSWORD_EXPIRY_CHOICES = [
    (30, _l("Cada mes")),
    (90, _l("Cada 3 meses")),
    (180, _l("Cada 6 meses")),
    (365, _l("Cada año")),
]


class SeguridadSettingsForm(_SettingsModelForm):
    class Meta(_SettingsModelForm.Meta):
        fields = [
            "password_min_length",
            "session_timeout",
            "password_expiry_enabled",
            "password_expiry_days",
            "ldap_enabled",
        ]
        widgets = {
            "password_min_length": forms.Select(
                choices=[(8, "8 caracteres"), (12, "12 caracteres"), (16, "16 caracteres")]
            ),
            "password_expiry_days": forms.Select(choices=PASSWORD_EXPIRY_CHOICES),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password_min_length"].widget.attrs["class"] = _INPUT_SELECT_COMPACT
        self.fields["session_timeout"].widget.attrs["class"] = _INPUT_NUMERIC
        self.fields["session_timeout"].widget.attrs["inputmode"] = "numeric"
        self.fields["password_expiry_days"].widget.attrs["class"] = _INPUT_SELECT_COMPACT


# ---------------------------------------------------------------------------
# Panel: LDAP corporativo (sobre core.LdapConfiguration; bind_password write-only)
# ---------------------------------------------------------------------------
class LdapConfigForm(forms.ModelForm):
    """Edita el singleton ``LdapConfiguration``.

    El ``bind_password`` es un secreto write-only: el GET nunca lo expone (campo
    manual, no vinculado a ``Meta.fields``) y un POST con el campo vacío conserva
    el valor previo (igual que SMTP/Integraciones).
    """

    # Secreto fuera de Meta.fields: gestionado a mano (write-only).
    bind_password = forms.CharField(
        label="Contraseña de bind",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": SECRET_PLACEHOLDER},
        ),
    )

    class Meta:
        model = LdapConfiguration
        fields = [
            "enabled",
            "server_uri",
            "use_ssl",
            "start_tls",
            "bind_dn",
            "user_search_base",
            "user_filter",
            "email_attribute",
            "connect_timeout",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = (css + " " + _INPUT).strip()

    @property
    def has_password(self) -> bool:
        """¿Existe un secreto de bind guardado? (para mostrar '●●● configurado')."""
        return bool(self.instance and self.instance.bind_password)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Write-only: solo sobreescribir si el usuario tecleó algo nuevo.
        new_secret = self.cleaned_data.get("bind_password", "")
        if new_secret:
            instance.bind_password = new_secret
        # Vacío -> se conserva el valor previo (no se toca).
        if commit:
            instance.save()
        return instance


# ---------------------------------------------------------------------------
# Sub-panel: Gateway SMS (FTP). Espejo del de webhooks/LDAP: password write-only.
# ---------------------------------------------------------------------------
class SmsGatewayForm(forms.ModelForm):
    """Edita el singleton ``SmsGatewayConfig``. ``ftp_password`` es write-only
    (el GET no lo expone; un POST vacío conserva el valor previo)."""

    ftp_password = forms.CharField(
        label="Contraseña FTP",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": SECRET_PLACEHOLDER},
        ),
    )

    class Meta:
        model = SmsGatewayConfig
        fields = ["enabled", "ftp_host", "ftp_user", "default_number", "remote_filename"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = (css + " " + _INPUT).strip()

    @property
    def has_password(self) -> bool:
        return bool(self.instance and self.instance.ftp_password)

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_secret = self.cleaned_data.get("ftp_password", "")
        if new_secret:
            instance.ftp_password = new_secret
        if commit:
            instance.save()
        return instance


# Mapa sección -> form usado por la vista/plantilla. El panel de organizacion no
# se expone en la UI: CertManager queda enfocado en monitoreo de certificados.
SETTINGS_PANELS = {
    "monitoreo": MonitoreoSettingsForm,
    "smtp": SmtpSettingsForm,
    "integraciones": IntegracionesSettingsForm,
    "seguridad": SeguridadSettingsForm,
}
