"""Pantalla Certificados (listado Forge UI + CRUD + bulk + export + test).

Espejo de ``ui_kits/certforge/Certificados.jsx`` (+ ``CertTable.jsx``):

- ``CertificateListForgeView`` (name ``certificate-list-forge``): listado Forge con
  FilterBar (chips removibles ), CertTable (estado, dominio, grupo,
  días+validity_bar, vence, emisor, responsables, último chequeo, acciones) y
  BulkBar. Las peticiones HTMX devuelven solo el ``tbody`` (``_rows.html``).
- ``CertificateCreateView`` (``cert-create``): modal HTMX con ``CertificateForm``
  (Guardar / Guardar y probar). Valida dominio duplicado y bloquea grupo ajeno.
- ``CertificateBulkView`` (``cert-bulk``): acciones masivas (probar / asignar a
  grupo / eliminar con confirmación).
- ``CertificateExportView`` (``cert-export``): exporta el listado filtrado a CSV.
- ``CertificateTestView`` (``cert-test``): "Probar ahora" por fila → drawer con
  resultado **real** de ``run_check`` (ERROR/timeout manejados), con throttle por
  usuario (scope ``cert_test``).

RBAC: un Miembro puede probar/crear en su grupo; las acciones sobre certs/grupos
ajenos devuelven 403/404 (recortado por ``Certificate.objects.for_user`` /
``Team.objects.for_user``). Eliminar masivo requiere confirmación explícita.

Propiedad de archivos (PASO 7): este módulo NO toca ``views.py`` ni las urls
compartidas; el cableado real es el PASO 14.
"""
from __future__ import annotations

import csv
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView

from apps.certificates.forms import CertificateForm
from apps.certificates.models import Certificate
from apps.core.enums import CertificateStatus, MembershipRole
from apps.teams.models import Team
from apps.teams.permissions import EDIT_CERT_ROLES, can_edit_certificate, can_edit_certs

logger = logging.getLogger("certmanager.web")


def _can_edit_any(user) -> bool:
    """True si el usuario puede crear/editar certificados en algún grupo."""
    if getattr(user, "is_owner", False):
        return True
    return user.memberships.filter(role__in=EDIT_CERT_ROLES).exists()


def _has_webhooks() -> bool:
    """¿Hay webhooks activos configurados? Si no, se oculta el canal 'Webhook'."""
    from apps.alerts.models import WebhookIntegration

    return WebhookIntegration.objects.filter(is_active=True).exists()


def _has_sms() -> bool:
    """¿El gateway SMS está habilitado y configurado? Misma regla que webhook:
    si no, el canal 'SMS' no se ofrece en el modal del certificado."""
    from apps.core.models import SmsGatewayConfig

    cfg = SmsGatewayConfig.load()
    return bool(cfg.enabled and cfg.ftp_host)

# Estados válidos para filtrar (espejo del listado del kit).
STATUS_CHOICES = list(CertificateStatus.choices)

# Throttle de "Probar ahora": N chequeos por usuario en una ventana (scope
# cert_test). Síncrono en MVP, sin Celery; cache local protege de abuso/DoS.
TEST_THROTTLE_MAX = 10
TEST_THROTTLE_WINDOW_SECONDS = 60


def _html(html, status=200):
    return HttpResponse(html, status=status, content_type="text/html; charset=utf-8")


def _decorate_responsables(cert):
    """Calcula los responsables (avatares) del certificado.

    Primero muestra los destinatarios explícitos del certificado (aunque no sean
    usuarios del sistema). Si no hay ninguno, cae a Admins del grupo.
    """
    people: list[dict] = []
    seen: set = set()

    for r in cert.recipients.all():
        key = r.email.lower()
        if key not in seen:
            seen.add(key)
            name = r.user.get_full_name() if r.user_id else ""
            people.append({
                "name": name or r.email,
                "email": r.email,
                "threshold": r.alert_threshold_days,
            })

    if not people:
        # Fallback: Colaboradores del grupo (el rol Admin de grupo no existe).
        for m in cert.team.memberships.all():
            key = m.user.email.lower()
            if m.role == MembershipRole.CONTRIBUTOR and key not in seen:
                seen.add(key)
                people.append(
                    {
                        "name": m.user.get_full_name() or m.user.email,
                        "email": m.user.email,
                    }
                )

    cert.responsables = people
    cert.responsables_extra = max(0, len(people) - 2)
    cert.notification_emails = list(cert.recipients.values_list("email", flat=True))
    return cert


# ---------------------------------------------------------------------------
# Filtros / chips
# ---------------------------------------------------------------------------
def _chip_remove_qs(request, *keys):
    """Querystring sin los parámetros de ``keys`` (para el chip removible).

    Devuelve algo como ``?q=foo`` o ``""`` (cadena vacía) si no quedan filtros.
    """
    params = request.GET.copy()
    for k in keys:
        params.pop(k, None)
    # 'days' agrupa days_lt/days_gte.
    if "days" in keys:
        params.pop("days_lt", None)
        params.pop("days_gte", None)
    qs = params.urlencode()
    return f"?{qs}" if qs else ""


def _apply_filters(request, certs):
    """Aplica los filtros del querystring y devuelve (queryset, chips activos)."""
    chips: list[dict] = []

    q = (request.GET.get("q") or "").strip()
    if q:
        certs = certs.filter(domain__icontains=q)
        chips.append({
            "key": "q", "label": "Búsqueda", "value": q,
            "remove_qs": _chip_remove_qs(request, "q"),
        })

    # status puede repetirse (?status=A&status=B) -> status__in.
    statuses = [s for s in request.GET.getlist("status") if s in dict(CertificateStatus.choices)]
    if statuses:
        certs = certs.filter(status__in=statuses)
        labels = [str(dict(CertificateStatus.choices)[s]) for s in statuses]
        chips.append({
            "key": "status", "label": "Estado", "value": " · ".join(labels),
            "remove_qs": _chip_remove_qs(request, "status"),
        })

    team = (request.GET.get("team") or "").strip()
    if team and team not in ("", "all"):
        # Dueño (FK) o compartido al grupo (M2M groups); espejo de for_team().
        certs = certs.filter(Q(team_id=team) | Q(groups=team)).distinct()

    # Ventana de días (drill desde el dashboard): days_gte / days_lt, numéricos e
    # independientes. La primera barra ``≤7d`` manda solo ``days_lt=7`` ->
    # ``days_left < 7`` INCLUYE los vencidos (días negativos). Las barras
    # siguientes añaden cota inferior ``days_gte``. El conteo de la barra/KPI ==
    # filas del listado (mismos filtros).
    def _as_int(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    days_lt = _as_int(request.GET.get("days_lt"))
    days_gte = _as_int(request.GET.get("days_gte"))
    if days_lt is not None:
        certs = certs.filter(days_left__lt=days_lt)
    if days_gte is not None:
        certs = certs.filter(days_left__gte=days_gte)
    if days_lt is not None or days_gte is not None:
        if days_lt is not None and days_gte is not None:
            label = f"{days_gte}–{days_lt}d"
        elif days_lt is not None:
            label = f"≤{days_lt}d"
        else:
            label = f"≥{days_gte}d"
        chips.append({
            "key": "days", "label": "Ventana", "value": label,
            "remove_qs": _chip_remove_qs(request, "days"),
        })

    return certs, chips


class CertificateListForgeView(LoginRequiredMixin, ListView):
    """Listado Forge de certificados con FilterBar, acciones masivas y DataTable."""

    template_name = "certificados/list.html"
    context_object_name = "certificates"
    # Sin paginación server-side: ForgeDataTable controla búsqueda, orden y páginas
    # sobre el set completo filtrado por permisos/servidor.

    def get_queryset(self):
        certs = (
            Certificate.objects.for_user(self.request.user)
            .select_related("team")
            .prefetch_related("recipients__user", "team__memberships__user", "groups")
            .order_by("domain")
        )
        certs, self._chips = _apply_filters(self.request, certs)
        # Cota de render server-side: evita pintar miles de filas de una vez. El
        # filtrado real (q/estado/grupo/días) ocurre en el servidor; si tras
        # filtrar siguen quedando más que el cap, se muestra un aviso para
        # refinar. La paginación fina (cliente) opera sobre el set ya renderizado.
        from django.conf import settings as _s

        self._filtered_total = certs.count()
        cap = getattr(_s, "CERT_LIST_RENDER_CAP", 1000)
        return certs[:cap]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        is_owner = bool(getattr(user, "is_owner", False))
        # Grupos donde el usuario puede EDITAR (Contributor+). Owner: todos.
        editable_set = None if is_owner else set(
            user.memberships.filter(role__in=EDIT_CERT_ROLES).values_list("team_id", flat=True)
        )

        def _can_edit(cert):
            if is_owner:
                return True
            if cert.team_id in editable_set:
                return True
            # `groups` viene prefetcheado -> sin consultas extra (sin N+1).
            return any(g.id in editable_set for g in cert.groups.all())

        cert_list = list(ctx["certificates"])
        for c in cert_list:
            _decorate_responsables(c)
            c.user_can_edit = _can_edit(c)
        ctx["certificates"] = cert_list

        ctx["chips"] = getattr(self, "_chips", [])
        ctx["total_count"] = Certificate.objects.for_user(user).count()
        filtered_total = getattr(self, "_filtered_total", len(cert_list))
        ctx["filtered_count"] = filtered_total
        ctx["rendered_count"] = len(cert_list)
        ctx["truncated"] = filtered_total > len(cert_list)
        ctx["statuses"] = STATUS_CHOICES
        ctx["can_create"] = _can_edit_any(user)
        # Grupos del ámbito para "Asignar/Agregar a grupo" (bulk): solo editables.
        if is_owner:
            ctx["groups"] = list(Team.objects.all().order_by("name"))
        else:
            ctx["groups"] = list(Team.objects.filter(id__in=editable_set).order_by("name"))
        return ctx

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["certificados/_rows.html"]
        return [self.template_name]


# ---------------------------------------------------------------------------
# Crear (modal)
# ---------------------------------------------------------------------------
class CertificateCreateView(LoginRequiredMixin, View):
    """Modal HTMX "Nuevo certificado" (Guardar / Guardar y probar)."""

    def get(self, request, *args, **kwargs):
        if not _can_edit_any(request.user):
            raise PermissionDenied(_("No tienes permiso para crear certificados."))
        form = CertificateForm(user=request.user)
        return _html(
            render_to_string(
                "certificados/_create_modal.html",
                {"form": form, "has_webhooks": _has_webhooks(), "has_sms": _has_sms()},
                request=request,
            )
        )

    def post(self, request, *args, **kwargs):
        if not _can_edit_any(request.user):
            raise PermissionDenied(_("No tienes permiso para crear certificados."))
        form = CertificateForm(request.POST, user=request.user)
        if not form.is_valid():
            return _html(
                render_to_string(
                    "certificados/_create_modal.html",
                    {"form": form, "has_webhooks": _has_webhooks(), "has_sms": _has_sms()},
                    request=request,
                ),
                status=422,
            )
        cert = form.save(commit=False)
        cert.created_by = request.user
        cert.save()
        form.save_m2m()  # persiste `groups` (grupos adicionales)
        form._save_recipients(cert)

        _decorate_responsables(cert)
        cert._is_new = True

        # ¿"Guardar y probar"? -> ejecuta el chequeo real ahora.
        also_test = "save_and_test" in request.POST
        toast_title = _("Certificado guardado")
        toast_msg = _("Se agregó al grupo correctamente.")
        if also_test:
            try:
                from apps.monitoring.runner import run_check

                run_check(cert, notify=False)
                cert.refresh_from_db()
                _decorate_responsables(cert)
                cert._is_new = True
                toast_msg = _("Chequeo realizado.")
            except Exception:  # noqa: BLE001 — el guardado ya ocurrió; no romper.
                toast_msg = _("Guardado, pero el chequeo no pudo completarse.")

        html = render_to_string(
            "certificados/_row_created.html",
            {
                "cert": cert,
                "toast_title": toast_title,
                "toast_message": toast_msg,
            },
            request=request,
        )
        return _html(html)


# ---------------------------------------------------------------------------
# Acciones masivas (BulkBar)
# ---------------------------------------------------------------------------
class CertificateBulkView(LoginRequiredMixin, View):
    """Acciones masivas: probar (N) / asignar a grupo / eliminar (con confirmación).

    Selección y RBAC: solo opera sobre certificados del ámbito del usuario
    (``Certificate.objects.for_user``). Un id ajeno simplemente se ignora.
    """

    def _selected(self, request):
        ids = request.POST.getlist("ids")
        return (
            Certificate.objects.for_user(request.user)
            .filter(id__in=ids)
            .select_related("team")
        )

    def _toast(self, request, *, tone, title, message, trigger=True):
        html = render_to_string(
            "partials/_toast.html",
            {"tone": tone, "title": title, "message": message},
            request=request,
        )
        resp = _html(html)
        if trigger:
            # El listado se recarga tras una acción que cambia datos.
            resp["HX-Trigger"] = "cf:certs-changed"
        return resp

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        certs = self._selected(request)
        count = certs.count()

        if count == 0:
            return self._toast(
                request,
                tone="warn",
                title=_("Sin selección"),
                message=_("No hay certificados seleccionados."),
                trigger=False,
            )

        if action == "test":
            # Probar N (síncrono en MVP). Se ejecuta el chequeo real de cada uno.
            from apps.monitoring.runner import run_check

            ok = 0
            for cert in certs:
                try:
                    run_check(cert, notify=False)
                    ok += 1
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Probar ahora: run_check reventó para %s (cert_id=%s)",
                        cert.domain, cert.pk,
                    )
                    continue
            return self._toast(
                request,
                tone="ok",
                title=_("Chequeo en curso"),
                message=_("Se probaron %(ok)s de %(count)s certificados.") % {"ok": ok, "count": count},
            )

        if action == "assign":
            team_id = (request.POST.get("team") or "").strip()
            team = Team.objects.for_user(request.user).filter(id=team_id).first()
            if team is None or not can_edit_certs(request.user, team):
                # Grupo ajeno, inexistente o sin permiso de edición: bloquear.
                raise PermissionDenied(_("No tienes permiso para asignar a ese grupo."))
            moved = 0
            for cert in certs:
                # Solo certs que el usuario puede editar (Contributor+).
                if not can_edit_certs(request.user, cert.team):
                    continue
                # Evita colisión con el UniqueConstraint(team, domain, port).
                clash = Certificate.objects.filter(
                    team=team, domain=cert.domain, port=cert.port
                ).exclude(pk=cert.pk).exists()
                if clash:
                    continue
                cert.team = team
                cert.save(update_fields=["team", "updated_at"])
                moved += 1
            return self._toast(
                request,
                tone="ok",
                title=_("Grupo asignado"),
                message=_("Se movieron %(moved)s de %(count)s certificados a %(name)s.") % {"moved": moved, "count": count, "name": team.name},
            )

        if action in ("add_group", "remove_group"):
            team_id = (request.POST.get("team") or "").strip()
            team = Team.objects.for_user(request.user).filter(id=team_id).first()
            if team is None or not can_edit_certs(request.user, team):
                raise PermissionDenied(_("No tienes permiso sobre ese grupo."))
            changed = 0
            for cert in certs:
                # Sólo certs que el usuario puede gestionar (en cualquiera de sus grupos).
                if not can_edit_certificate(request.user, cert):
                    continue
                if action == "add_group":
                    if cert.team_id == team.id:  # el dueño no es "adicional"
                        continue
                    cert.groups.add(team)
                else:
                    cert.groups.remove(team)
                changed += 1
            if action == "add_group":
                msg = _("Se agregaron a %(changed)s de %(count)s certificados en %(name)s.") % {"changed": changed, "count": count, "name": team.name}
            else:
                msg = _("Se quitaron de %(changed)s de %(count)s certificados en %(name)s.") % {"changed": changed, "count": count, "name": team.name}
            return self._toast(
                request,
                tone="ok",
                title=_("Grupos actualizados"),
                message=msg,
            )

        if action == "delete":
            # Solo se eliminan certs que el usuario puede editar (Contributor+).
            editable = [c for c in certs if can_edit_certs(request.user, c.team)]
            if not editable:
                raise PermissionDenied(
                    _("No tienes permiso para eliminar los certificados seleccionados.")
                )
            # Eliminar masivo CON confirmación: el POST debe traer confirm=1.
            if request.POST.get("confirm") != "1":
                html = render_to_string(
                    "certificados/_bulk_delete_confirm.html",
                    {"certs": editable, "count": len(editable)},
                    request=request,
                )
                return _html(html)
            ids = [c.pk for c in editable]
            domains = [c.domain for c in editable]
            Certificate.objects.filter(pk__in=ids).delete()
            return self._toast(
                request,
                tone="ok",
                title=_("Certificados eliminados"),
                message=_("Se eliminaron %(n)s certificados.") % {"n": len(domains)},
            )

        return self._toast(
            request,
            tone="err",
            title=_("Acción no reconocida"),
            message=_("La acción solicitada no es válida."),
            trigger=False,
        )


# ---------------------------------------------------------------------------
# Activar / pausar monitoreo (toggle is_active)
# ---------------------------------------------------------------------------
class CertToggleActiveView(LoginRequiredMixin, View):
    """Activa o pausa el monitoreo de un certificado (toggle ``is_active``).

    Un certificado pausado NO se chequea (``check_certificates`` filtra
    ``is_active=True``). Requiere poder gestionar el cert (Contributor+ en alguno
    de sus grupos).
    """

    def post(self, request, pk, *args, **kwargs):
        cert = get_object_or_404(Certificate.objects.for_user(request.user), pk=pk)
        if not can_edit_certificate(request.user, cert):
            raise PermissionDenied(_("No tienes permiso para gestionar este certificado."))
        cert.is_active = not cert.is_active
        cert.save(update_fields=["is_active", "updated_at"])
        if cert.is_active:
            _toggle_title = _("Monitoreo activado")
            _toggle_msg = _("%(domain)s: el monitoreo quedó activo.") % {"domain": cert.domain}
        else:
            _toggle_title = _("Monitoreo pausado")
            _toggle_msg = _("%(domain)s: el monitoreo quedó en pausa (no se chequeará).") % {"domain": cert.domain}
        html = render_to_string(
            "partials/_toast.html",
            {
                "tone": "ok",
                "title": _toggle_title,
                "message": _toggle_msg,
            },
            request=request,
        )
        resp = _html(html)
        resp["HX-Trigger"] = "cf:certs-changed, cf:cert-updated"
        return resp


class CertSnoozeView(LoginRequiredMixin, View):
    """Silencia (o reactiva) las alertas de un certificado por N días.

    POST ``days`` ∈ {1,7,30} silencia hasta ahora+N; ``days=0`` reactiva. Mientras
    está silenciado, las alertas se registran pero NO se notifican. Requiere poder
    gestionar el cert (Contributor+ en alguno de sus grupos).
    """

    ALLOWED_DAYS = {1, 7, 30}

    def post(self, request, pk, *args, **kwargs):
        cert = get_object_or_404(Certificate.objects.for_user(request.user), pk=pk)
        if not can_edit_certificate(request.user, cert):
            raise PermissionDenied(_("No tienes permiso para gestionar este certificado."))
        try:
            days = int(request.POST.get("days", 0))
        except (TypeError, ValueError):
            days = 0
        if days in self.ALLOWED_DAYS:
            cert.snoozed_until = timezone.now() + timezone.timedelta(days=days)
            title = _("Alertas silenciadas")
            message = _("%(domain)s: sin notificaciones por %(days)s día(s).") % {"domain": cert.domain, "days": days}
        else:
            cert.snoozed_until = None
            title = _("Alertas reactivadas")
            message = _("%(domain)s: notificaciones activas.") % {"domain": cert.domain}
        cert.save(update_fields=["snoozed_until", "updated_at"])
        html = render_to_string(
            "partials/_toast.html",
            {"tone": "ok", "title": title, "message": message},
            request=request,
        )
        resp = _html(html)
        resp["HX-Trigger"] = "cf:certs-changed, cf:cert-updated"
        return resp


# ---------------------------------------------------------------------------
# Exportar (CSV)
# ---------------------------------------------------------------------------
class CertificateExportView(LoginRequiredMixin, View):
    """Exporta el listado filtrado a CSV (síncrono, MVP)."""

    def get(self, request, *args, **kwargs):
        certs = (
            Certificate.objects.for_user(request.user)
            .select_related("team")
            .prefetch_related("groups")
            .order_by("domain")
        )
        certs, _chips = _apply_filters(request, certs)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="certificados.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["Dominio", "Puerto", "Grupo", "Estado", "Días restantes",
             "Vence el", "Emisor", "Último chequeo"]
        )
        for c in certs:
            extra = list(c.groups.values_list("name", flat=True))
            grupo = c.team.name + (" (+" + ", ".join(extra) + ")" if extra else "")
            writer.writerow([
                c.domain,
                c.port,
                grupo,
                c.get_status_display(),
                c.days_left if c.days_left is not None else "",
                c.valid_to.strftime("%Y-%m-%d") if c.valid_to else "",
                c.issuer,
                c.last_checked_at.strftime("%Y-%m-%d %H:%M") if c.last_checked_at else "",
            ])
        return response


# ---------------------------------------------------------------------------
# Probar ahora (drawer) — resultado REAL
# ---------------------------------------------------------------------------
def _throttle_ok(user) -> bool:
    """Throttle por usuario para "Probar ahora" (scope cert_test).

    Cuenta de chequeos en una ventana deslizante simple sobre cache. Devuelve
    False cuando se excede el máximo (la vista responde 429).
    """
    key = f"cert_test:{user.pk}"
    count = cache.get(key, 0)
    if count >= TEST_THROTTLE_MAX:
        return False
    # add() crea la clave con TTL solo si no existe; luego incrementamos.
    cache.add(key, 0, TEST_THROTTLE_WINDOW_SECONDS)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, TEST_THROTTLE_WINDOW_SECONDS)
    return True


def _drawer_steps(result):
    """Pasos para el drawer a partir del CheckResult (real)."""
    if result.ok:
        return [
            {"label": "Resolución DNS y validación de host", "state": "ok"},
            {"label": "Conexión TLS establecida", "state": "ok"},
            {"label": "Certificado leído y validado", "state": "ok"},
        ]
    msg = result.error_message or "El chequeo falló."
    return [
        {"label": "Resolución DNS y validación de host", "state": "running"},
        {"label": msg, "state": "err"},
    ]


class CertificateTestView(LoginRequiredMixin, View):
    """"Probar ahora" por fila: drawer con resultado REAL del chequeo.

    GET abre el drawer (cáscara) con el botón para disparar el POST. POST ejecuta
    ``run_check`` (real, con anti-SSRF y manejo de ERROR/timeout en el servicio) y
    rinde el drawer con los pasos y el resultado. RBAC: solo certs del ámbito.
    """

    def _get_cert(self, request, pk):
        return get_object_or_404(
            Certificate.objects.for_user(request.user).select_related("team"),
            pk=pk,
        )

    def get(self, request, pk, *args, **kwargs):
        cert = self._get_cert(request, pk)
        html = render_to_string(
            "certificados/_drawer_test.html",
            {
                "cert": cert,
                "domain": cert.domain,
                "port": cert.port,
                "steps": None,
                "done": False,
            },
            request=request,
        )
        return _html(html)

    def post(self, request, pk, *args, **kwargs):
        cert = self._get_cert(request, pk)

        if not _throttle_ok(request.user):
            html = render_to_string(
                "certificados/_drawer_test.html",
                {
                    "cert": cert,
                    "domain": cert.domain,
                    "port": cert.port,
                    "throttled": True,
                    "done": True,
                    "steps": [
                        {"label": "Demasiadas pruebas. Espera un momento.", "state": "err"},
                    ],
                },
                request=request,
            )
            return _html(html, status=429)

        try:
            from apps.monitoring.runner import run_check

            check, result = run_check(cert, notify=False)
            cert.refresh_from_db()
        except Exception as exc:  # noqa: BLE001 — degradar a error legible.
            from apps.monitoring.services import CheckResult

            result = CheckResult(
                ok=False,
                status=CertificateStatus.ERROR,
                error_message=str(exc) or "El chequeo no pudo completarse.",
            )

        html = render_to_string(
            "certificados/_drawer_test.html",
            {
                "cert": cert,
                "domain": cert.domain,
                "port": cert.port,
                "steps": _drawer_steps(result),
                "result": result,
                "done": True,
                "checked_at": timezone.now(),
            },
            request=request,
        )
        resp = _html(html)
        # Refresca el listado Y el detalle (el chequeo cambia estado/días).
        resp["HX-Trigger"] = "cf:certs-changed, cf:cert-updated"
        return resp
