"""Centro de Alertas + panel de la campana.

Modelo de estados (work-stream B):
- **Estado compartido** de la alerta: ``OPEN`` → ``RESOLVED`` (``resolved_at``).
  "Resolver" es la acción que reemplaza al antiguo "Limpiar" no-destructivo: saca
  la alerta de "abiertas" y de la campana, pero la conserva en el Centro (histórico)
  con tag "Resuelta". RBAC: solo **Owner global** o **Admin del grupo** del
  certificado pueden resolver.
- **Estado personal** (``AlertUserState.read_at``): "leída" para el resaltado y el
  badge. Cualquier usuario con visibilidad del ámbito puede marcar leída.

Visibilidad:
- **Campana / panel:** alertas del ámbito con ``status=OPEN`` (ya NO se aplica el
  sello ``panel_cleared_at``: limpiar = resolver). El badge cuenta las no leídas.
- **Centro (`/alerts/`):** SIEMPRE todo el histórico del ámbito; las resueltas
  salen tenues + tag "Resuelta".

Cada mutación responde con ``_toast.html`` (OOB) + badge OOB y dispara
``cf:alerts-changed`` para que el chrome se mantenga coherente sin recargar.
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView

from apps.alerts.models import Alert, AlertUserState
from apps.certificates.models import Certificate
from apps.core.enums import AlertStatus, MembershipRole
from apps.teams.models import Membership

# La campana muestra solo las primeras N del panel (resto en el centro).
PANEL_LIMIT = 8

_CHANNEL_ICON = {
    "EMAIL": "mail",
    "WEBHOOK": "webhook",
    "PLATFORM": "bell",
}


# ---------------------------------------------------------------------------
# Ámbito, RBAC y estado personal
# ---------------------------------------------------------------------------
def _scoped_alerts(user):
    """Alertas cuyo certificado es visible para el usuario (todo el histórico)."""
    certs = Certificate.objects.for_user(user)
    return Alert.objects.filter(certificate__in=certs)


def _get_scoped_alert(user, pk):
    return get_object_or_404(
        _scoped_alerts(user).select_related("certificate__team"), pk=pk
    )


def _can_manage_alert(user, alert) -> bool:
    """¿Puede el usuario RESOLVER esta alerta compartida? SOLO el Owner global
    (el rol Admin de grupo se eliminó por decisión del Owner)."""
    return bool(getattr(user, "is_owner", False))


def _manageable_open_alerts(user):
    """Alertas OPEN del ámbito que el usuario puede resolver (solo Owner)."""
    qs = _scoped_alerts(user).filter(status=AlertStatus.OPEN)
    if getattr(user, "is_owner", False):
        return qs
    return qs.none()


def _states_by_alert(user, alerts):
    ids = [a.id for a in alerts]
    return {
        s.alert_id: s
        for s in AlertUserState.objects.filter(user=user, alert_id__in=ids)
    }


def _panel_queryset(user):
    """Alertas que muestra la campana: simplemente las OPEN del ámbito.

    Ya NO se filtra por ``panel_cleared_at`` (limpiar = resolver). El badge es el
    subconjunto no leído de este queryset.
    """
    return _scoped_alerts(user).filter(status=AlertStatus.OPEN).distinct()


def _panel_count(user) -> int:
    alerts = list(_panel_queryset(user))
    states = _states_by_alert(user, alerts)
    return sum(
        1 for a in alerts if not (states.get(a.id) and states[a.id].read_at)
    )


def _severity_family(severity):
    return {
        "POR_VENCER": "warn",
        "CRITICO": "crit",
        "VENCIDO": "exp",
        "ERROR": "err",
    }.get(str(severity).upper(), "none")


def _decorate(alert, state, user):
    """Anota una alerta con su estado de presentación para las plantillas."""
    alert.is_read = bool(state and state.read_at)
    # "Resuelta": cualquier estado distinto de OPEN (resuelta/pospuesta).
    alert.is_resolved = alert.status != AlertStatus.OPEN
    alert.is_archived = alert.is_resolved  # compat con plantillas/estilos previos
    alert.family = _severity_family(alert.severity)
    alert.can_manage = _can_manage_alert(user, alert)
    delivery = alert.deliveries.first()
    alert.channel_label = delivery.get_channel_display() if delivery else "Plataforma"
    alert.channel_icon = _CHANNEL_ICON.get(
        delivery.channel if delivery else "PLATFORM", "bell"
    )
    return alert


# ---------------------------------------------------------------------------
# Respuesta de mutación: toast OOB + badge OOB
# ---------------------------------------------------------------------------
def _chrome_response(request, *, tone, title, message, status=200):
    html = render_to_string(
        "partials/_toast.html",
        {"tone": tone, "title": title, "message": message},
        request=request,
    )
    html += render_to_string(
        "alerts/_badge_oob.html",
        {"forge_panel_count": _panel_count(request.user)},
        request=request,
    )
    response = HttpResponse(html, status=status)
    response["HX-Trigger"] = "cf:alerts-changed"
    return response


# ---------------------------------------------------------------------------
# Centro de Alertas
# ---------------------------------------------------------------------------
TAB_TODAS = "todas"
TAB_NOLEIDAS = "noleidas"
TAB_CRITICAS = "criticas"
TAB_ERROR = "error"
VALID_TABS = {TAB_TODAS, TAB_NOLEIDAS, TAB_CRITICAS, TAB_ERROR}


class AlertCenterView(LoginRequiredMixin, TemplateView):
    """`/alerts/` — Centro con tabs por severidad/estado. Lista todo el histórico."""

    template_name = "alerts/center.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        tab = self.request.GET.get("tab", TAB_TODAS)
        if tab not in VALID_TABS:
            tab = TAB_TODAS

        base = (
            _scoped_alerts(user)
            .select_related("certificate", "certificate__team")
            .prefetch_related("deliveries")
            .order_by("-created_at")
        )
        all_list = list(base)
        states = _states_by_alert(user, all_list)
        for a in all_list:
            _decorate(a, states.get(a.id), user)

        unread_count = sum(1 for a in all_list if not a.is_read)

        if tab == TAB_NOLEIDAS:
            rows = [a for a in all_list if not a.is_read]
        elif tab == TAB_CRITICAS:
            rows = [a for a in all_list if a.severity in ("CRITICO", "VENCIDO")]
        elif tab == TAB_ERROR:
            rows = [a for a in all_list if a.severity == "ERROR"]
        else:
            rows = all_list

        ctx.update(
            {
                "rows": rows,
                "active_tab": tab,
                "total_count": len(all_list),
                "unread_count": unread_count,
                "can_resolve_any": _manageable_open_alerts(user).exists(),
            }
        )
        return ctx

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            # Respuesta HX = la región completa (tabs + tabla) que reemplaza
            # #alert-region por innerHTML. Evita el swap OOB dentro del <tbody>.
            return ["alerts/_region.html"]
        return [self.template_name]


# ---------------------------------------------------------------------------
# Panel de la campana + detalle
# ---------------------------------------------------------------------------
class AlertPanelView(LoginRequiredMixin, TemplateView):
    """`GET /alerts/panel/` — lista del panel de la campana (parcial)."""

    template_name = "alerts/_panel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        alerts = list(
            _panel_queryset(user)
            .select_related("certificate", "certificate__team")
            .prefetch_related("deliveries")
            .order_by("-created_at")[:PANEL_LIMIT]
        )
        states = _states_by_alert(user, alerts)
        for a in alerts:
            _decorate(a, states.get(a.id), user)
        ctx["panel_alerts"] = alerts
        ctx["forge_panel_count"] = _panel_count(user)
        return ctx


class AlertDetailView(LoginRequiredMixin, TemplateView):
    """`GET /alerts/<pk>/detail/` — detalle de una alerta (drawer HTMX)."""

    template_name = "alerts/_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        alert = _get_scoped_alert(user, kwargs["pk"])
        state = AlertUserState.objects.filter(user=user, alert=alert).first()
        _decorate(alert, state, user)
        # Marcar como leída al abrir el detalle (estado personal).
        if state is None or state.read_at is None:
            st, _created = AlertUserState.objects.get_or_create(alert=alert, user=user)
            if st.read_at is None:
                st.read_at = timezone.now()
                st.save(update_fields=["read_at", "updated_at"])
        deliveries = list(alert.deliveries.all())
        for d in deliveries:
            d.icon = _CHANNEL_ICON.get(d.channel, "bell")
        alert.deliveries_list = deliveries
        ctx["alert"] = alert
        return ctx


# ---------------------------------------------------------------------------
# Mutaciones de estado personal (leída)
# ---------------------------------------------------------------------------
class AlertReadView(LoginRequiredMixin, View):
    """`POST /alerts/<pk>/read/` — marca leída (estado personal)."""

    def post(self, request, pk):
        alert = _get_scoped_alert(request.user, pk)
        state, _created = AlertUserState.objects.get_or_create(alert=alert, user=request.user)
        if state.read_at is None:
            state.read_at = timezone.now()
            state.save(update_fields=["read_at", "updated_at"])
        return _chrome_response(
            request, tone="ok",
            title=_("Alerta marcada como leída"),
            message=alert.certificate.domain,
        )


class AlertReadAllView(LoginRequiredMixin, View):
    """`POST /alerts/read-all/` — marca leídas todas las del panel."""

    def post(self, request):
        user = request.user
        now = timezone.now()
        for alert in _panel_queryset(user):
            state, _created = AlertUserState.objects.get_or_create(alert=alert, user=user)
            if state.read_at is None:
                state.read_at = now
                state.save(update_fields=["read_at", "updated_at"])
        return _chrome_response(
            request, tone="ok",
            title=_("Todas marcadas como leídas"),
            message=_("El panel sigue mostrando tus alertas abiertas."),
        )


# ---------------------------------------------------------------------------
# Mutaciones de estado compartido (resolver) — RBAC Admin/Owner
# ---------------------------------------------------------------------------
class AlertResolveView(LoginRequiredMixin, View):
    """`POST /alerts/<pk>/resolve/` — resuelve/cierra una alerta (Admin/Owner)."""

    def post(self, request, pk):
        alert = _get_scoped_alert(request.user, pk)
        if not _can_manage_alert(request.user, alert):
            raise PermissionDenied(_("Solo Admin del grupo u Owner pueden resolver alertas."))
        if alert.status == AlertStatus.OPEN:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = timezone.now()
            alert.save(update_fields=["status", "resolved_at", "updated_at"])
        return _chrome_response(
            request, tone="ok",
            title=_("Alerta resuelta"),
            message=_("%(domain)s · queda en el histórico.") % {"domain": alert.certificate.domain},
        )


class AlertResolveAllView(LoginRequiredMixin, View):
    """`POST /alerts/resolve-all/` — resuelve todas las OPEN gestionables (Admin/Owner)."""

    def post(self, request):
        user = request.user
        now = timezone.now()
        count = _manageable_open_alerts(user).update(status=AlertStatus.RESOLVED, resolved_at=now)
        # Panel vacío al instante + toast/badge OOB.
        html = render_to_string("alerts/_panel.html", {"panel_alerts": []}, request=request)
        html += render_to_string(
            "partials/_toast.html",
            {
                "tone": "ok",
                "title": _("Alertas resueltas"),
                "message": _("%(count)s alerta(s) cerradas. Siguen en el centro como resueltas.") % {"count": count},
            },
            request=request,
        )
        html += render_to_string(
            "alerts/_badge_oob.html", {"forge_panel_count": _panel_count(user)}, request=request
        )
        response = HttpResponse(html)
        response["HX-Trigger"] = "cf:alerts-changed"
        return response
