"""Pantalla CertDetalle (Forge UI · PASO 8).

Espejo de ``ui_kits/certforge/CertDetalle.jsx`` PERO con **datos reales**: el kit
inventa SHA-1 / versión / cadena / SAN / historial; aquí se usa **solo** el último
``CertificateCheck`` (``cert.last_check``) y el historial real de ``checks``. Si no
hay ``last_check`` cada pestaña muestra su propio estado vacío es-DO.

Vistas:
- ``CertDetailView`` (name ``cert-detail``): página completa con hero (badge grande,
  días, validity_bar) + tabs HTMX con deep-link (``?tab=…``).
- ``CertDetailTabView`` (name ``cert-detail-tab``): devuelve SOLO el panel de una
  pestaña (Resumen / Cadena+SAN / Técnico / Historial / Alertas). El deep-link
  funciona porque ``CertDetailView`` también respeta ``?tab=`` al render inicial.
- ``CertNotifyView`` (name ``cert-notify``): notificación **manual** a los
  responsables del certificado (POST). RBAC: un Miembro puede sobre certs de su
  grupo (recortado por ``Certificate.objects.for_user``). Throttle por usuario.
- ``CertEditView`` (name ``cert-edit``): modal de edición (reutiliza
  ``CertificateForm`` del PASO 7).

"Probar ahora" reutiliza ``cert-test`` (drawer) del PASO 7 — esta pantalla solo lo
enlaza; el endpoint y el drawer ya existen.

Propiedad de archivos (PASO 8): este módulo NO toca ``views.py`` ni las urls
compartidas; el cableado real es el PASO 14.
"""
from __future__ import annotations

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View

from apps.accounts.models import default_avatar_choice
from apps.alerts.models import Alert, AlertUserState
from apps.certificates.forms import CertificateForm
from apps.certificates.models import Certificate
from apps.core.enums import (
    AlertStatus,
    DeliveryStatus,
    MembershipRole,
    NotificationChannel,
)

# Pestañas válidas del detalle (deep-link ?tab=…). 'resumen' es la inicial.
VALID_TABS = ("resumen", "cadena", "tecnico", "historial", "alertas")
DEFAULT_TAB = "resumen"

# Cuántos chequeos del historial se listan / cuántos puntos para la mini-tendencia.
HISTORY_LIMIT = 50
TREND_POINTS = 12

# Throttle de "Notificar" manual: N envíos por usuario en una ventana (scope
# cert_notify). Síncrono en MVP; cache local protege de abuso/DoS.
NOTIFY_THROTTLE_MAX = 5
NOTIFY_THROTTLE_WINDOW_SECONDS = 60

_CHANNEL_ICON = {
    "EMAIL": "mail",
    "WEBHOOK": "webhook",
    "PLATFORM": "bell",
}


def _has_cert_sms() -> bool:
    """¿Gateway SMS habilitado y configurado? (misma regla que webhook)."""
    from apps.core.models import SmsGatewayConfig

    cfg = SmsGatewayConfig.load()
    return bool(cfg.enabled and cfg.ftp_host)


def _html(html, status=200):
    return HttpResponse(html, status=status, content_type="text/html; charset=utf-8")


def _get_cert(request, pk):
    """Certificado del ámbito del usuario (RBAC) o 404."""
    return get_object_or_404(
        Certificate.objects.for_user(request.user)
        .select_related("team")
        .prefetch_related("recipients__user", "team__memberships__user"),
        pk=pk,
    )


# ---------------------------------------------------------------------------
# Responsables: destinatarios explícitos del certificado; si no hay, Admins del
# grupo como fallback.
# ---------------------------------------------------------------------------
def _avatar_for(user, email):
    """Avatar de la persona pintada: el elegido si es usuario; si es un correo
    externo (o un legado sin elección), el derivado determinista por email."""
    if user is not None:
        prefs = getattr(user, "preferences", None)
        choice = getattr(prefs, "avatar_choice", 0)
        if choice:
            return choice
    return default_avatar_choice(email)


def _responsables(cert):
    people: list[dict] = []
    seen: set = set()

    for r in cert.recipients.select_related("user__preferences"):
        key = r.email.lower()
        if key not in seen:
            seen.add(key)
            name = r.user.get_full_name() if r.user_id else ""
            people.append({
                "name": name or r.email,
                "email": r.email,
                "source": "recipient",
                "threshold": r.alert_threshold_days,
                "avatar_choice": _avatar_for(r.user if r.user_id else None, r.email),
            })

    if not people:
        for m in cert.team.memberships.select_related("user__preferences"):
            key = m.user.email.lower()
            if m.role == MembershipRole.ADMIN and key not in seen:
                seen.add(key)
                people.append(
                    {
                        "name": m.user.get_full_name() or m.user.email,
                        "email": m.user.email,
                        "source": "admin",
                        "avatar_choice": _avatar_for(m.user, m.user.email),
                    }
                )
    return people


def _channels(cert):
    """Lista de canales efectivos activos (para los tags de notificación)."""
    eff = cert.effective_channels
    return [
        {"key": "platform", "label": _("Plataforma"), "icon": "bell", "tone": "brand", "on": eff["platform"]},
        {"key": "email", "label": _("Correo"), "icon": "mail", "tone": "ok", "on": eff["email"]},
        {"key": "webhook", "label": _("Webhook"), "icon": "webhook", "tone": "neutral", "on": eff["webhook"]},
    ]


# ---------------------------------------------------------------------------
# Construcción del contexto por pestaña (SOLO datos reales)
# ---------------------------------------------------------------------------
def _tab_context(request, cert, tab):
    """Contexto del panel de la pestaña pedida. Cada panel maneja su vacío."""
    ctx = {"cert": cert, "tab": tab, "last_check": cert.last_check}

    if tab == "resumen":
        ctx["responsables"] = _responsables(cert)
        ctx["channels"] = _channels(cert)
    elif tab == "tecnico":
        ctx["rows"] = _tecnico_rows(cert.last_check)
    elif tab == "cadena":
        lc = cert.last_check
        ctx["chain"] = list(lc.chain or []) if lc else []
        ctx["san"] = list(lc.san or []) if lc else []
    elif tab == "historial":
        checks = list(
            cert.checks.order_by("-checked_at")[:HISTORY_LIMIT]
        )
        ctx["checks"] = checks
        ctx["trend"] = _trend(checks)
    elif tab == "alertas":
        ctx["alerts"] = _alert_history(request.user, cert)

    return ctx


def _tecnico_rows(last_check):
    """Filas técnicas (mono) SOLO con datos reales del último chequeo.

    NUNCA inventa SHA-1 / versión (el kit los falsea): solo emite las filas para
    las que hay valor real. Devuelve [] si no hay last_check (estado vacío).
    """
    if last_check is None:
        return []
    rows = []
    if last_check.signature_algorithm:
        rows.append({"label": _("Algoritmo de firma"), "value": last_check.signature_algorithm})
    if last_check.key_size:
        rows.append({"label": _("Tamaño de clave"), "value": f"{last_check.key_size} bits"})
    if last_check.serial:
        rows.append({"label": _("Número de serie"), "value": last_check.serial})
    if last_check.fingerprint_sha256:
        rows.append({"label": "SHA-256", "value": last_check.fingerprint_sha256})
    return rows


def _trend(checks):
    """Serie de días restantes (orden cronológico) para la mini-tendencia.

    Devuelve dicts {x, y, days} normalizados a un viewBox 0..100 / 0..30 para
    dibujar una polilínea SVG sin librerías. Vacío si <2 puntos con días.
    """
    pts = [
        c.days_left
        for c in reversed(checks[:TREND_POINTS])
        if c.days_left is not None
    ]
    if len(pts) < 2:
        return None
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    n = len(pts)
    coords = []
    for i, d in enumerate(pts):
        x = round(i / (n - 1) * 100, 2)
        # y invertida: más días => más arriba (y menor).
        y = round(28 - (d - lo) / span * 26, 2)
        coords.append({"x": x, "y": y, "days": d})
    polyline = " ".join(f"{p['x']},{p['y']}" for p in coords)
    return {"points": coords, "polyline": polyline, "min": lo, "max": hi}


def _alert_history(user, cert):
    """Histórico COMPLETO de alertas del cert (incl. dismissed/archivadas).

    DoD: la pestaña Alertas muestra todo el histórico, incluidas las limpiadas;
    ``dismissed`` es solo presentación (tenue + tag "Archivada"), nunca un filtro.
    """
    alerts = list(
        cert.alerts.prefetch_related("deliveries").order_by("-created_at")
    )
    states = {
        s.alert_id: s
        for s in AlertUserState.objects.filter(user=user, alert__in=alerts)
    }
    for a in alerts:
        st = states.get(a.id)
        a.is_read = bool(st and st.read_at)
        dismissed = bool(st and st.dismissed_at)
        a.is_archived = dismissed or a.status != AlertStatus.OPEN
        a.family = _severity_family(a.severity)
        delivery = a.deliveries.first()
        a.channel_label = delivery.get_channel_display() if delivery else _("Plataforma")
        a.channel_icon = _CHANNEL_ICON.get(delivery.channel if delivery else "PLATFORM", "bell")
    return alerts


def _severity_family(severity):
    return {
        "POR_VENCER": "warn",
        "CRITICO": "crit",
        "VENCIDO": "exp",
        "ERROR": "err",
    }.get(str(severity).upper(), "none")


# ---------------------------------------------------------------------------
# Página completa
# ---------------------------------------------------------------------------
class CertDetailView(LoginRequiredMixin, View):
    """`/certificates/<pk>/` — detalle con hero + tabs (deep-link ``?tab=``)."""

    def get(self, request, pk, *args, **kwargs):
        cert = _get_cert(request, pk)
        tab = request.GET.get("tab", DEFAULT_TAB)
        if tab not in VALID_TABS:
            tab = DEFAULT_TAB
        ctx = _tab_context(request, cert, tab)
        ctx["active_tab"] = tab
        ctx["tabs"] = _tabs_meta(cert)
        html = render_to_string("detalle/detail.html", ctx, request=request)
        return _html(html)


class CertDetailTabView(LoginRequiredMixin, View):
    """`/certificates/<pk>/tab/<tab>/` — SOLO el panel de la pestaña (HTMX)."""

    def get(self, request, pk, tab, *args, **kwargs):
        cert = _get_cert(request, pk)
        if tab not in VALID_TABS:
            tab = DEFAULT_TAB
        ctx = _tab_context(request, cert, tab)
        ctx["active_tab"] = tab
        html = render_to_string("detalle/_tab_panel.html", ctx, request=request)
        return _html(html)


def _tabs_meta(cert):
    """Metadatos de las pestañas (con conteos reales de historial/alertas)."""
    return [
        {"value": "resumen", "label": _("Resumen")},
        {"value": "cadena", "label": _("Cadena y SAN")},
        {"value": "tecnico", "label": _("Detalles técnicos")},
        {"value": "historial", "label": _("Historial"), "count": cert.checks.count()},
        {"value": "alertas", "label": _("Alertas"), "count": cert.alerts.count()},
    ]


# ---------------------------------------------------------------------------
# Notificar (manual) — envía a los responsables
# ---------------------------------------------------------------------------
def _notify_throttle_ok(user) -> bool:
    key = f"cert_notify:{user.pk}"
    count = cache.get(key, 0)
    if count >= NOTIFY_THROTTLE_MAX:
        return False
    cache.add(key, 0, NOTIFY_THROTTLE_WINDOW_SECONDS)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, NOTIFY_THROTTLE_WINDOW_SECONDS)
    return True


class CertNotifyView(LoginRequiredMixin, View):
    """`POST /certificates/<pk>/notify/` — notifica manualmente a los responsables.

    RBAC: un Miembro PUEDE sobre certs de su grupo (recortado por
    ``Certificate.objects.for_user``: un cert ajeno => 404). Throttle por usuario.

    Crea/asegura una ``Alert`` informativa y dispara los envíos por los canales
    efectivos del certificado (reutiliza el notificador del paso de alertas),
    registrando ``AlertDelivery`` por destino. Responde con toast (OOB).
    """

    def post(self, request, pk, *args, **kwargs):
        cert = _get_cert(request, pk)

        if not _notify_throttle_ok(request.user):
            return self._toast(
                request,
                tone="warn",
                title=_("Demasiadas notificaciones"),
                message=_("Espera un momento antes de volver a notificar."),
                status=429,
            )

        recipients = cert.all_recipients
        if not recipients and not _responsables(cert):
            return self._toast(
                request,
                tone="warn",
                title=_("Sin responsables"),
                message=_("Este certificado no tiene destinatarios ni admins de grupo."),
            )

        sent, failed = self._dispatch_manual(request, cert)

        if sent == 0 and failed > 0:
            return self._toast(
                request,
                tone="err",
                title=_("No se pudo notificar"),
                message=_("Ningún canal aceptó el envío. Revisa la configuración SMTP/webhook."),
            )

        return self._toast(
            request,
            tone="ok",
            title=_("Notificación enviada"),
            message=_("Se notificó a los responsables de %(domain)s.") % {"domain": cert.domain},
        )

    def _dispatch_manual(self, request, cert):
        """Envía una notificación manual por los canales efectivos del cert.

        Registra una ``Alert`` (status OPEN) si no hay una abierta, para que el
        envío quede asociado a un evento auditable, y un ``AlertDelivery`` por
        destino. Tolerante a fallos (SMTP/webhook caídos no rompen la vista).
        """
        from apps.alerts.models import Alert, AlertDelivery

        message = (
            f"Notificación manual: el certificado de {cert.domain} "
            f"{self._status_phrase(cert)} (enviada por {request.user.get_full_name() or request.user.email})."
        )

        from apps.core.enums import AlertSeverity

        # Severidad REAL según el estado actual del cert. Si el cert está sano
        # (vigente / sin chequear), la notificación manual NO debe crear una
        # alerta de riesgo ABIERTA (sería falsa en el panel/campana): se registra
        # como RESUELTA (auditable, con sus envíos) pero no aparece como activa.
        risk_severity = {
            "POR_VENCER": AlertSeverity.POR_VENCER,
            "CRITICO": AlertSeverity.CRITICO,
            "VENCIDO": AlertSeverity.VENCIDO,
            "ERROR": AlertSeverity.ERROR,
        }.get(cert.status)

        alert = cert.alerts.filter(status=AlertStatus.OPEN).first()
        if alert is None:
            is_risk = risk_severity is not None
            alert = Alert.objects.create(
                certificate=cert,
                severity=risk_severity or AlertSeverity.POR_VENCER,
                status=AlertStatus.OPEN if is_risk else AlertStatus.RESOLVED,
                resolved_at=None if is_risk else timezone.now(),
                message=message,
            )

        channels = cert.effective_channels
        sent = 0
        failed = 0

        if channels["platform"]:
            AlertDelivery.objects.create(
                alert=alert,
                channel=NotificationChannel.PLATFORM,
                target="in-app",
                status=DeliveryStatus.SENT,
                sent_at=timezone.now(),
            )
            sent += 1

        if channels["email"]:
            from django.core.mail import EmailMessage

            from apps.core.mail import default_from_email, global_bcc, smtp_connection
            from apps.core.models import OrganizationSettings

            org = OrganizationSettings.load()
            subject = f"[CertManager] {cert.domain} — Notificación"
            for email in cert.all_recipients:
                try:
                    EmailMessage(
                        subject=subject,
                        body=message,
                        from_email=default_from_email(org),
                        to=[email],
                        bcc=global_bcc(org, exclude=[email]),
                        connection=smtp_connection(org),
                    ).send(fail_silently=False)
                    AlertDelivery.objects.create(
                        alert=alert,
                        channel=NotificationChannel.EMAIL,
                        target=email[:500],
                        status=DeliveryStatus.SENT,
                        sent_at=timezone.now(),
                    )
                    sent += 1
                except Exception as exc:  # noqa: BLE001 — tolerante a fallos
                    AlertDelivery.objects.create(
                        alert=alert,
                        channel=NotificationChannel.EMAIL,
                        target=email[:500],
                        status=DeliveryStatus.FAILED,
                        error=str(exc),
                    )
                    failed += 1

        if channels["webhook"]:
            from apps.alerts.services import _webhooks_for, _send_webhook

            for hook in _webhooks_for(cert):
                before = AlertDelivery.objects.filter(
                    alert=alert, status=DeliveryStatus.SENT
                ).count()
                _send_webhook(alert, hook, message)
                after = AlertDelivery.objects.filter(
                    alert=alert, status=DeliveryStatus.SENT
                ).count()
                if after > before:
                    sent += 1
                else:
                    failed += 1

        return sent, failed

    def _status_phrase(self, cert):
        if cert.days_left is None:
            return "está pendiente de chequeo"
        if cert.days_left < 0:
            return f"venció hace {abs(cert.days_left)} días"
        return f"vence en {cert.days_left} días"

    def _toast(self, request, *, tone, title, message, status=200):
        html = render_to_string(
            "partials/_toast.html",
            {"tone": tone, "title": title, "message": message},
            request=request,
        )
        resp = _html(html, status=status)
        resp["HX-Trigger"] = "cf:alerts-changed"
        return resp


class CertificateEmailTestForm(forms.Form):
    email = forms.EmailField(
        label="Correo de prueba",
        widget=forms.EmailInput(
            attrs={
                "class": "input w-full",
                "placeholder": "persona@empresa.com",
                "autocomplete": "off",
            }
        ),
    )


class CertEmailTestView(LoginRequiredMixin, View):
    """Envía un correo de prueba de este certificado a un destinatario manual.

    No usa ``cert.all_recipients`` para no molestar a los responsables reales.
    """

    def get(self, request, pk, *args, **kwargs):
        cert = _get_cert(request, pk)
        return _html(
            render_to_string(
                "detalle/_email_test_modal.html",
                {"cert": cert, "form": CertificateEmailTestForm()},
                request=request,
            )
        )

    def post(self, request, pk, *args, **kwargs):
        cert = _get_cert(request, pk)
        form = CertificateEmailTestForm(request.POST)
        if not form.is_valid():
            return _html(
                render_to_string(
                    "detalle/_email_test_modal.html",
                    {"cert": cert, "form": form},
                    request=request,
                ),
                status=422,
            )

        from django.core.mail import EmailMessage

        from apps.core.mail import default_from_email, global_bcc, smtp_connection
        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()
        email = form.cleaned_data["email"]
        body = (
            "Correo de prueba de CertManager.\n\n"
            f"Certificado: {cert.domain}:{cert.port}\n"
            f"Estado: {cert.get_status_display()}\n"
            f"Dias restantes: {cert.days_left if cert.days_left is not None else 'sin chequear'}\n\n"
            "Este envio fue dirigido manualmente y no se envio a los responsables reales."
        )
        try:
            EmailMessage(
                subject=f"[CertManager] Prueba de certificado - {cert.domain}",
                body=body,
                from_email=default_from_email(org),
                to=[email],
                bcc=global_bcc(org, exclude=[email]),
                connection=smtp_connection(org),
            ).send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            return _html(
                render_to_string(
                    "detalle/_email_test_modal.html",
                    {"cert": cert, "form": form, "error": str(exc)},
                    request=request,
                ),
                status=502,
            )

        html = (
            '<div id="modal-root" hx-swap-oob="innerHTML"></div>'
            + render_to_string(
                "partials/_toast.html",
                {
                    "tone": "ok",
                    "title": _("Correo de prueba enviado"),
                    "message": _("Se envió solo a %(email)s.") % {"email": email},
                },
                request=request,
            )
        )
        return _html(html)


# ---------------------------------------------------------------------------
# Editar (modal) — reutiliza CertificateForm del PASO 7
# ---------------------------------------------------------------------------
class CertEditView(LoginRequiredMixin, View):
    """`/certificates/<pk>/editar/` — modal de edición (CertificateForm)."""

    def _form_initial(self, cert):
        return {
            "recipients": ", ".join(cert.recipients.values_list("email", flat=True)),
        }

    def _require_edit(self, request, cert):
        from django.core.exceptions import PermissionDenied

        from apps.teams.permissions import can_edit_certificate

        if not can_edit_certificate(request.user, cert):
            raise PermissionDenied("No tienes permiso para editar este certificado.")

    def _ctx(self, form, cert):
        from apps.alerts.models import WebhookIntegration

        return {
            "form": form,
            "cert": cert,
            "has_webhooks": WebhookIntegration.objects.filter(is_active=True).exists(),
            "has_sms": _has_cert_sms(),
        }

    def get(self, request, pk, *args, **kwargs):
        cert = _get_cert(request, pk)
        self._require_edit(request, cert)
        form = CertificateForm(
            instance=cert, user=request.user, initial=self._form_initial(cert)
        )
        return _html(
            render_to_string(
                "detalle/_edit_modal.html",
                self._ctx(form, cert),
                request=request,
            )
        )

    def post(self, request, pk, *args, **kwargs):
        cert = _get_cert(request, pk)
        self._require_edit(request, cert)
        form = CertificateForm(request.POST, instance=cert, user=request.user)
        if not form.is_valid():
            return _html(
                render_to_string(
                    "detalle/_edit_modal.html",
                    self._ctx(form, cert),
                    request=request,
                ),
                status=422,
            )
        form.save()
        # Respuesta: toast OOB + recarga del detalle vía evento HTMX.
        html = render_to_string(
            "partials/_toast.html",
            {
                "tone": "ok",
                "title": _("Certificado actualizado"),
                "message": _("Los cambios se guardaron correctamente."),
            },
            request=request,
        )
        resp = _html(html)
        # Refresca el detalle Y el listado (la edición puede cambiar dominio,
        # grupo, umbral, plantilla, etc.) — evita estado viejo hasta recargar.
        resp["HX-Trigger"] = "cf:certs-changed, cf:cert-updated"
        return resp
