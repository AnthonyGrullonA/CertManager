"""Configuración (PASO 11) — paneles HTMX sobre OrganizationSettings.

SOLO Owner: cualquier usuario sin ``is_owner`` recibe **403** (no 302), tanto en
la página como en los parciales y los endpoints de prueba.

Paneles (sección → form): Monitoreo, Correo (SMTP), Integraciones y Seguridad.
La identidad/organización no se expone porque CertManager se usa solo para
monitoreo de certificados.

Secretos write-only: el GET de SMTP/Integraciones nunca incluye
``smtp_password`` ni la URL del webhook (ver ``apps/core/forms.py``).
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView

from apps.core.forms import SETTINGS_PANELS, LdapConfigForm, SmsGatewayForm
from apps.core.models import (
    LdapConfiguration,
    OrganizationSettings,
    SmsGatewayConfig,
)

# Definición de las secciones (orden + etiqueta + icono Lucide) para la nav.
SECTIONS = [
    {"key": "monitoreo", "label": "Monitoreo", "icon": "refresh-cw"},
    {"key": "smtp", "label": "Correo (SMTP)", "icon": "mail"},
    {"key": "integraciones", "label": "Integraciones", "icon": "webhook"},
    {"key": "seguridad", "label": "Seguridad", "icon": "lock"},
]
_SECTION_KEYS = {s["key"] for s in SECTIONS}


class _OwnerOnlyMixin(LoginRequiredMixin):
    """Exige autenticación + ``is_owner``; si no, 403 (no redirección)."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not getattr(user, "is_owner", False):
            raise PermissionDenied(_("Solo el Owner puede acceder a Configuración."))
        return super().dispatch(request, *args, **kwargs)


def _build_form(section, settings_obj, data=None, files=None):
    form_cls = SETTINGS_PANELS[section]
    kwargs = {"data": data, "files": files}
    # Los forms de modelo reciben instance; el de integraciones no.
    if section == "integraciones":
        return form_cls(**kwargs)
    return form_cls(instance=settings_obj, **kwargs)


def _render_panel(request, section, form, *, saved=False, ldap_form=None, sms_form=None):
    template = f"config/panels/_{section}.html"
    ctx = {
        "section": section,
        "form": form,
        "saved": saved,
        "sections": SECTIONS,
    }
    # El panel de Seguridad incluye el sub-panel LDAP (su propio form/instancia).
    if section == "seguridad":
        if ldap_form is None:
            ldap_form = LdapConfigForm(instance=LdapConfiguration.load())
        ctx["ldap_form"] = ldap_form
    # El panel de Integraciones incluye el sub-panel del gateway SMS.
    if section == "integraciones":
        if sms_form is None:
            sms_form = SmsGatewayForm(instance=SmsGatewayConfig.load())
        ctx["sms_form"] = sms_form
    return render(request, template, ctx)


class SettingsView(_OwnerOnlyMixin, TemplateView):
    """Página principal: nav de secciones + el panel inicial (monitoreo)."""

    template_name = "config/settings.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        section = self.request.GET.get("section", "monitoreo")
        if section not in _SECTION_KEYS:
            section = "monitoreo"
        settings_obj = OrganizationSettings.load()
        ctx["sections"] = SECTIONS
        ctx["active_section"] = section
        ctx["form"] = _build_form(section, settings_obj)
        # Sub-paneles con su propio form/instancia (también en carga directa por
        # URL, no solo vía HTMX): LDAP en Seguridad, gateway SMS en Integraciones.
        if section == "seguridad":
            ctx["ldap_form"] = LdapConfigForm(instance=LdapConfiguration.load())
        elif section == "integraciones":
            ctx["sms_form"] = SmsGatewayForm(instance=SmsGatewayConfig.load())
        return ctx


class SettingsPanelView(_OwnerOnlyMixin, View):
    """GET (carga) y POST (guarda) de un panel concreto vía HTMX."""

    def get(self, request, section):
        if section not in _SECTION_KEYS:
            raise Http404("Sección desconocida.")
        settings_obj = OrganizationSettings.load()
        form = _build_form(section, settings_obj)
        return _render_panel(request, section, form)

    def post(self, request, section):
        if section not in _SECTION_KEYS:
            raise Http404("Sección desconocida.")

        # Sub-panel LDAP dentro de Seguridad: su propio form/instancia.
        if section == "seguridad" and request.POST.get("panel") == "ldap":
            ldap_form = LdapConfigForm(
                instance=LdapConfiguration.load(), data=request.POST
            )
            if ldap_form.is_valid():
                ldap_form.save()
                fresh_ldap = LdapConfigForm(instance=LdapConfiguration.load())
                seg = _build_form("seguridad", OrganizationSettings.load())
                return _render_panel(
                    request, "seguridad", seg, saved=True, ldap_form=fresh_ldap
                )
            seg = _build_form("seguridad", OrganizationSettings.load())
            return _render_panel(request, "seguridad", seg, ldap_form=ldap_form)

        # Sub-panel SMS dentro de Integraciones: su propio form/instancia.
        if section == "integraciones" and request.POST.get("panel") == "sms":
            sms_form = SmsGatewayForm(instance=SmsGatewayConfig.load(), data=request.POST)
            integ = _build_form("integraciones", OrganizationSettings.load())
            if sms_form.is_valid():
                sms_form.save()
                fresh_sms = SmsGatewayForm(instance=SmsGatewayConfig.load())
                return _render_panel(
                    request, "integraciones", integ, saved=True, sms_form=fresh_sms
                )
            return _render_panel(request, "integraciones", integ, sms_form=sms_form)

        settings_obj = OrganizationSettings.load()
        form = _build_form(
            section, settings_obj, data=request.POST, files=request.FILES or None
        )
        if form.is_valid():
            form.save()
            # Releer para reflejar lo guardado y volver a enmascarar secretos.
            settings_obj = OrganizationSettings.load()
            fresh = _build_form(section, settings_obj)
            return _render_panel(request, section, fresh, saved=True)
        return _render_panel(request, section, form)


class TestSmtpView(_OwnerOnlyMixin, View):
    """'Probar envío' de SMTP: envía un correo de prueba real con la config actual."""

    def post(self, request):
        from django.core.mail import EmailMessage

        from apps.core.mail import default_from_email, global_bcc, smtp_connection

        settings_obj = OrganizationSettings.load()
        if not settings_obj.smtp_host:
            return render(
                request,
                "config/_test_result.html",
                {
                    "tone": "warn",
                    "title": _("Configura el host SMTP"),
                    "msg": _("Falta el servidor de correo para enviar la prueba."),
                },
            )

        destino = settings_obj.smtp_from or settings_obj.smtp_user
        try:
            EmailMessage(
                subject="CertManager — correo de prueba",
                body=(
                    "Este es un correo de prueba enviado desde la configuración de "
                    "CertManager. Si lo recibes, el SMTP está operativo."
                ),
                from_email=default_from_email(settings_obj),
                to=[destino],
                bcc=global_bcc(settings_obj, exclude=[destino]),
                connection=smtp_connection(settings_obj),
            ).send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            return render(
                request,
                "config/_test_result.html",
                {
                    "tone": "exp",
                    "title": _("No se pudo enviar el correo"),
                    "msg": _("Revisa la configuración SMTP: %(exc)s") % {"exc": exc},
                },
            )
        return render(
            request,
            "config/_test_result.html",
            {
                "tone": "ok",
                "title": _("Correo de prueba enviado"),
                "msg": _("Se envió a %(destino)s.") % {"destino": destino},
            },
        )


class TestWebhookView(_OwnerOnlyMixin, View):
    """'Probar webhook': hace un POST real al webhook activo, con guarda anti-SSRF."""

    def post(self, request):
        from urllib.parse import urlparse

        import requests

        from apps.alerts.models import WebhookIntegration
        from apps.monitoring.services import SSRFValidationError, validate_public_host

        hook = WebhookIntegration.objects.filter(team__isnull=True, is_active=True).first()
        if hook is None:
            return render(
                request,
                "config/_test_result.html",
                {
                    "tone": "warn",
                    "title": _("Sin webhook configurado"),
                    "msg": _("Agrega una URL de Slack o Teams antes de probar."),
                },
            )

        try:
            host = urlparse(hook.url).hostname
            if not host:
                raise SSRFValidationError("URL de webhook sin host válido.")
            validate_public_host(host)  # bloquea rangos internos/metadata
            resp = requests.post(
                hook.url,
                json={"text": "CertManager — mensaje de prueba del webhook."},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return render(
                request,
                "config/_test_result.html",
                {
                    "tone": "exp",
                    "title": _("No se pudo contactar el webhook"),
                    "msg": str(exc),
                },
            )
        return render(
            request,
            "config/_test_result.html",
            {
                "tone": "ok",
                "title": _("Webhook contactado"),
                "msg": _("Se envió un mensaje de prueba a %(name)s.") % {"name": hook.name},
            },
        )


class TestLdapView(_OwnerOnlyMixin, View):
    """'Probar conexión' LDAP: hace el bind de servicio y persiste el resultado."""

    def post(self, request):
        from django.utils import timezone

        from apps.accounts.ldap_backend import test_connection

        config = LdapConfiguration.load()
        ok, message = test_connection(config)

        config.last_test_at = timezone.now()
        config.last_test_ok = ok
        config.last_test_message = message[:300]
        config.save()

        if ok:
            return render(
                request,
                "config/_test_result.html",
                {"tone": "ok", "title": _("Conexión LDAP correcta"), "msg": message},
            )
        return render(
            request,
            "config/_test_result.html",
            {"tone": "err", "title": _("No se pudo conectar a LDAP"), "msg": message},
        )


class TestSmsView(_OwnerOnlyMixin, View):
    """'Probar SMS': deposita un SMS de prueba en el gateway FTP configurado."""

    def post(self, request):
        from apps.alerts.sms import send_sms

        config = SmsGatewayConfig.load()
        if not config.ftp_host:
            return render(
                request,
                "config/_test_result.html",
                {
                    "tone": "warn",
                    "title": _("Sin gateway SMS configurado"),
                    "msg": _("Configura el host FTP y el número por defecto antes de probar."),
                },
            )
        # Para la prueba se fuerza el envío aunque 'enabled' esté apagado todavía.
        cfg = config
        if not cfg.enabled:
            cfg.enabled = True
        ok, detail = send_sms(cfg, "CertManager — mensaje de prueba del gateway SMS.")
        if ok:
            return render(
                request,
                "config/_test_result.html",
                {"tone": "ok", "title": _("SMS de prueba enviado"), "msg": detail},
            )
        return render(
            request,
            "config/_test_result.html",
            {"tone": "exp", "title": _("No se pudo enviar el SMS"), "msg": detail},
        )
