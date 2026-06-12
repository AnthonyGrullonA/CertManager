"""Formularios de la app Certificados (capa web Forge UI, PASO 7).

`CertificateForm` cubre el alta/edición de un certificado desde el modal Forge
(espejo de ``CertForm`` en ``ui_kits/certforge/Certificados.jsx``):

- Campos: dominio, puerto, grupo, umbral de alerta, destinatarios y canales.
- RBAC: el queryset de ``team`` se recorta a los grupos visibles del usuario
  (Owner: todos; resto: sus grupos) de modo que **no se puede crear en un grupo
  ajeno** ni siquiera manipulando el POST (``team`` ajeno => inválido).
- Valida **dominio duplicado** dentro del mismo grupo (espejo del
  ``UniqueConstraint(team, domain, port)`` del modelo, pero con un mensaje es-DO).
"""
from __future__ import annotations

from django import forms

from apps.core.enums import CertificateStatus  # noqa: F401  (referencia semántica)
from apps.teams.models import Team

from .models import Certificate

# Umbrales de alerta ofrecidos en el modal (espejo del Select del kit).
ALERT_THRESHOLD_CHOICES = [
    (15, "15 días"),
    (30, "30 días"),
    (45, "45 días"),
    (60, "60 días"),
]


class CertificateForm(forms.ModelForm):
    """Alta/edición de un certificado con RBAC por grupo y validación de dominio.

    Se construye con ``user`` para recortar el queryset de ``team`` a su ámbito.
    """

    alert_threshold_days = forms.TypedChoiceField(
        label="Umbral de alerta",
        choices=ALERT_THRESHOLD_CHOICES,
        coerce=int,
        initial=30,
        required=False,
    )
    recipients = forms.CharField(
        label="Destinatarios de notificación",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "correo@equipo.com, …"}
        ),
        help_text="Heredan del grupo si se deja vacío",
    )
    validate_on_save = forms.BooleanField(
        label="Validar conexión al guardar",
        required=False,
        initial=True,
    )
    # Grupos adicionales como checkboxes (patrón Forge para multi-selección, igual
    # que "Formato(s)" en reportes) — más limpio que un <select multiple> crudo.
    groups = forms.ModelMultipleChoiceField(
        label="Grupos adicionales",
        queryset=Team.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Otros grupos que también gestionan/ven este certificado.",
    )

    class Meta:
        model = Certificate
        fields = [
            "domain",
            "port",
            "team",
            "alert_threshold_days",
            "notify_platform",
            "notify_email",
            "notify_webhook",
            "notify_sms",
            "email_template",
            "groups",
        ]
        widgets = {
            "domain": forms.TextInput(attrs={"placeholder": "api.ejemplo.com"}),
            "port": forms.NumberInput(attrs={"min": 1, "max": 65535}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.duplicate_info = []  # certs existentes con el mismo dominio:puerto (otros grupos)
        # RBAC: solo grupos donde el usuario puede EDITAR certificados
        # (Owner: todos; resto: grupos donde es Colaborador o Admin). Un Viewer no
        # tiene ninguno => no puede crear. Un team ajeno no aparece => inválido.
        from apps.teams.permissions import EDIT_CERT_ROLES

        if user is None or getattr(user, "is_owner", False):
            team_qs = Team.objects.all()
        else:
            editable_ids = user.memberships.filter(
                role__in=EDIT_CERT_ROLES
            ).values_list("team_id", flat=True)
            team_qs = Team.objects.filter(id__in=editable_ids)
        self.fields["team"].queryset = team_qs.order_by("name")
        self.fields["team"].label = "Grupo"
        self.fields["team"].empty_label = "Selecciona grupo"

        # Plantilla de correo (kind=CERT). Opcional: vacío => texto plano.
        from apps.mailtemplates.models import EmailTemplate

        self.fields["email_template"].queryset = EmailTemplate.objects.usable(kind="CERT")
        self.fields["email_template"].required = False
        self.fields["email_template"].label = "Plantilla de correo"
        self.fields["email_template"].empty_label = "Texto plano (predeterminado)"

        # Grupos ADICIONALES de gestión/visualización (además del dueño). Solo se
        # ofrecen grupos donde el usuario puede editar (Contributor+).
        self.fields["groups"].queryset = team_qs.order_by("name")

        self.fields["port"].initial = 443
        # Canales por defecto: plataforma siempre, correo sí, webhook no.
        self.fields["notify_platform"].initial = True
        self.fields["notify_email"].initial = True
        self.fields["notify_webhook"].initial = False
        self.fields["notify_sms"].initial = False

        # Clase Forge para todos los controles de texto/numero/select.
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " input").strip()

    # --- Validaciones -----------------------------------------------------
    def clean_domain(self):
        domain = (self.cleaned_data.get("domain") or "").strip().lower()
        if not domain:
            raise forms.ValidationError("El dominio es obligatorio.")
        # Limpieza básica: sin esquema ni path (solo el host).
        for prefix in ("https://", "http://"):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.split("/")[0].strip()
        return domain

    def clean_port(self):
        port = self.cleaned_data.get("port") or 443
        if port < 1 or port > 65535:
            raise forms.ValidationError("El puerto debe estar entre 1 y 65535.")
        return port

    def clean(self):
        cleaned = super().clean()
        team = cleaned.get("team")
        domain = cleaned.get("domain")
        port = cleaned.get("port") or 443

        # Defensa en profundidad: aunque el queryset ya recorta, verificamos que
        # el usuario pueda EDITAR certificados en el grupo elegido (Contributor+).
        if team is not None and self.user is not None:
            from apps.teams.permissions import can_edit_certs

            if not can_edit_certs(self.user, team):
                self.add_error(
                    "team",
                    "No tienes permiso para crear certificados en este grupo.",
                )

        # Dominio duplicado dentro del mismo grupo (espejo del UniqueConstraint).
        if team is not None and domain:
            qs = Certificate.objects.filter(team=team, domain=domain, port=port)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "domain",
                    "Ya existe un certificado con este dominio y puerto en el grupo.",
                )

        # Duplicidad ENTRE grupos: el mismo dominio:puerto ya existe en OTRO grupo.
        # Para evitar duplicar el monitoreo, se bloquea e indica dónde está; si el
        # existente está pausado, la UI ofrece reactivarlo (ver duplicate_info).
        if domain:
            from apps.teams.permissions import can_edit_certificate

            others = Certificate.objects.filter(domain=domain, port=port)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if team is not None:
                others = others.exclude(team=team)  # el mismo grupo ya se reportó arriba
            others = list(others.select_related("team").prefetch_related("groups"))
            if others:
                names = []
                for c in others:
                    gs = [c.team.name] + [g.name for g in c.groups.all()]
                    names.extend(gs)
                    self.duplicate_info.append({
                        "id": c.pk,
                        "groups": gs,
                        "is_active": c.is_active,
                        "editable": self.user is not None and can_edit_certificate(self.user, c),
                    })
                uniq = ", ".join(dict.fromkeys(names))  # dedup preservando orden
                self.add_error(
                    "domain",
                    f"El dominio {domain}:{port} ya está agregado en: {uniq}. "
                    "Para evitar duplicidad, agregá tu grupo al certificado existente "
                    "en vez de crear uno nuevo.",
                )
        return cleaned

    def save(self, commit=True):
        cert = super().save(commit=False)
        if commit:
            cert.save()
            self.save_m2m()  # persiste `groups` (grupos adicionales)
            self._save_recipients(cert)
        return cert

    def _save_recipients(self, cert):
        """Reemplaza los destinatarios del certificado con los del campo de texto."""
        raw = (self.cleaned_data.get("recipients") or "").strip()
        if not raw:
            return
        from .models import CertificateRecipient

        emails = [e.strip() for e in raw.replace(";", ",").split(",") if e.strip()]
        for email in emails:
            CertificateRecipient.objects.get_or_create(certificate=cert, email=email)
