"""Dashboard Forge UI (PASO 6).

Reescribe el dashboard con la estética Forge UI (KpiCards con franja de estado,
ChartCards donut/barras/tendencia, CertTable compacta "Requieren atención" y
ActivityFeed de alertas recientes) y, sobre todo, un **drill-down unificado**:
cada KPI, segmento del donut y barra enlaza al listado filtrado con una
semántica que COINCIDE exactamente con el bucket mostrado.

Decisiones congeladas que aquí se materializan (migration-plan.md §7):

- La primera ventana ``≤7d`` **incluye los vencidos** (``days_left < 7``, también
  negativos). Las ventanas son rangos por cota superior, sin solape:
  ``(-inf,7) [7,15) [15,30) [30,60) [60,90)``. Cada barra expone ``days_lt`` y,
  cuando aplica, ``days_gte`` para que el conteo de la barra == filas del drill.
- KPI "Crítico / Vencido" abre ``status__in=CRITICO,VENCIDO``; "Error / sin
  chequear" abre ``status__in=ERROR,SIN_CHEQUEAR``. El donut respeta los mismos
  mapeos por segmento.
- "Chequear todo" está atado al **scope activo** del ámbito (síncrono en MVP):
  responde con un toast OOB de conteo real y un ``HX-Trigger`` que refresca KPIs.

Propiedad de archivos: este módulo NO toca ``apps/web/views.py`` ni las urls
compartidas. Se cablea de forma definitiva en el PASO 14.
"""
from __future__ import annotations

import logging
import threading
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from apps.alerts.models import Alert
from apps.certificates.models import Certificate, CertificateCheck
from apps.core.enums import AlertStatus, CertificateStatus

logger = logging.getLogger("certmanager.dashboard")

# Nº de semanas que abarca la gráfica de tendencia del dashboard.
TREND_WEEKS = 8

# Ventanas de vencimiento (cotas superiores, en días). El primer bucket incluye
# los vencidos (días < 0); ver migration-plan.md §7.
EXPIRY_WINDOWS = [7, 15, 30, 60, 90]

# Estados que "requieren atención", en orden de urgencia.
ATTENTION_STATUSES = [
    CertificateStatus.VENCIDO,
    CertificateStatus.CRITICO,
    CertificateStatus.ERROR,
    CertificateStatus.POR_VENCER,
]

# Familia Forge por estado (para color de franja KPI / segmento donut).
# Color por estado en el dashboard (donut). Esquema: rojo = PELIGRO real
# (crítico/vencido), naranja = ATENCIÓN (error), gris = pendiente (sin chequear).
# Es un mapa LOCAL del dashboard: no afecta badges de otras pantallas.
STATUS_FAMILY = {
    CertificateStatus.VIGENTE: "ok",        # verde
    CertificateStatus.POR_VENCER: "warn",   # ámbar
    CertificateStatus.CRITICO: "exp",       # rojo (peligro)
    CertificateStatus.VENCIDO: "exp",       # rojo (peligro)
    CertificateStatus.ERROR: "crit",        # naranja (atención, no peligro)
    CertificateStatus.SIN_CHEQUEAR: "none", # gris (pendiente de chequeo)
}

# Familia de la barra según su ventana (urgencia visual).
WINDOW_FAMILY = {7: "crit", 15: "warn", 30: "warn", 60: "ok", 90: "ok"}

# Color CSS (token) por estado para el donut y su leyenda. Arco y punto comparten
# esta MISMA fuente para que coincidan exacto (y sigan el tema claro/oscuro). Por
# defecto es ``--status-<familia>-solid``; VENCIDO se overridea a un rojo más
# oscuro (``--status-exp-fg``) para distinguirse de CRITICO en el donut: ambos son
# rojo (= peligro), pero el vencido, más severo, se ve más oscuro.
STATUS_COLOR_VAR = {
    CertificateStatus.VENCIDO: "var(--status-exp-fg)",
}


def _status_color(status) -> str:
    return STATUS_COLOR_VAR.get(status, f"var(--status-{STATUS_FAMILY[status]}-solid)")


def _scoped_certificates(request):
    """Certificados visibles para el usuario, recortados al **scope activo**.

    El scope efectivo lo resuelve el context processor (querystring › cookie ›
    default). Aquí lo re-derivamos de forma equivalente y barata para no acoplar
    la vista al render: ``team`` en querystring, si no la cookie ``cf_scope``.
    """
    certs = Certificate.objects.for_user(request.user)
    raw = (
        request.GET.get("team")
        or request.POST.get("team")
        or request.COOKIES.get("cf_scope")
        or ""
    ).strip()
    if raw and raw not in ("", "all"):
        # Dueño (FK) o compartido al grupo (M2M groups); espejo de for_team().
        certs = certs.filter(Q(team_id=raw) | Q(groups=raw)).distinct()
    return certs


def _list_url(**params) -> str:
    """URL del listado de certificados con los parámetros de drill dados.

    Acepta listas en ``status`` para emitir ``?status=A&status=B`` (status__in).
    Mantiene el ``team`` del scope activo para que el listado herede el ámbito.
    """
    base = reverse("certificate-list")
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple)):
            for v in value:
                pairs.append((key, str(v)))
        else:
            pairs.append((key, str(value)))
    return f"{base}?{urlencode(pairs)}" if pairs else base


def _weekly_trend(certs, now, weeks: int = TREND_WEEKS) -> dict:
    """Tendencia **real** de las últimas ``weeks`` semanas desde el historial.

    Para cada ventana semanal cuenta los certificados DISTINTOS del ámbito cuyo
    chequeo registrado (``CertificateCheck``) en esa semana resultó en estado
    "Por vencer" o "Vencido". La fuente es el historial real, no datos fijos: si
    aún no hay chequeos, las series quedan en cero (``has_data=False``) y la
    plantilla muestra un estado vacío honesto en vez de una curva inventada.
    """
    labels: list[str] = []
    por_vencer: list[int] = []
    vencidos: list[int] = []
    history = CertificateCheck.objects.filter(certificate__in=certs)
    for i in range(weeks - 1, -1, -1):
        w_start = now - timedelta(weeks=i + 1)
        w_end = now - timedelta(weeks=i)
        window = history.filter(checked_at__gte=w_start, checked_at__lt=w_end)
        pv = (
            window.filter(status=CertificateStatus.POR_VENCER)
            .values("certificate").distinct().count()
        )
        vc = (
            window.filter(status=CertificateStatus.VENCIDO)
            .values("certificate").distinct().count()
        )
        labels.append(w_end.strftime("%d %b"))
        por_vencer.append(pv)
        vencidos.append(vc)
    return {
        "labels": labels,
        "por_vencer": por_vencer,
        "vencidos": vencidos,
        "has_data": any(por_vencer) or any(vencidos),
    }


class DashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard Forge UI con drill-down unificado y "Chequear todo"."""

    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request
        certs = _scoped_certificates(request)

        scope_team = (request.GET.get("team") or request.COOKIES.get("cf_scope") or "").strip()
        if scope_team in ("", "all"):
            scope_team = ""

        # --- KPIs: conteo por estado -------------------------------------
        counts = dict(
            certs.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )

        def c(*statuses):
            return sum(counts.get(s, 0) for s in statuses)

        total = certs.count()
        n_vigente = c(CertificateStatus.VIGENTE)
        n_por_vencer = c(CertificateStatus.POR_VENCER)
        n_critico = c(CertificateStatus.CRITICO)
        n_vencido = c(CertificateStatus.VENCIDO)
        n_error = c(CertificateStatus.ERROR)
        n_sin = c(CertificateStatus.SIN_CHEQUEAR)

        ctx["kpis"] = {
            "total": total,
            "vigente": n_vigente,
            "por_vencer": n_por_vencer,
            "critico": n_critico,
            "vencido": n_vencido,
            "error": n_error,
            "sin_chequear": n_sin,
            # Agregados de las tarjetas combinadas.
            "critico_vencido": n_critico + n_vencido,
            "error_sin_chequear": n_error + n_sin,
        }

        # Tarjetas KPI con franja de estado + drill (label/valor/familia/href).
        ctx["kpi_cards"] = [
            {
                # Agregado, no es un estado → azul (info), NO el rojo de marca.
                "label": "Total monitoreados", "value": total, "family": "info",
                "icon": "shield-check", "href": _list_url(team=scope_team),
            },
            {
                "label": "Vigentes", "value": n_vigente, "family": "ok",
                "icon": "circle-check",
                "href": _list_url(status=CertificateStatus.VIGENTE, team=scope_team),
            },
            {
                "label": "Por vencer", "value": n_por_vencer, "family": "warn",
                "icon": "clock",
                "href": _list_url(status=CertificateStatus.POR_VENCER, team=scope_team),
            },
            {
                "label": "Crítico / Vencido", "value": n_critico + n_vencido, "family": "exp",
                "icon": "triangle-alert",
                "href": _list_url(
                    status=[CertificateStatus.CRITICO, CertificateStatus.VENCIDO],
                    team=scope_team,
                ),
            },
            {
                # Agrupa ERROR + SIN_CHEQUEAR: la etiqueta lo nombra explícitamente
                # para que el valor coincida con lo mostrado (no oculta los ERROR).
                # Atención, no peligro → naranja (familia crit), NO rojo (el rojo
                # queda para Crítico/Vencido).
                "label": "Error / sin chequear", "value": n_error + n_sin, "family": "crit",
                "icon": "circle-alert",
                "href": _list_url(
                    status=[CertificateStatus.ERROR, CertificateStatus.SIN_CHEQUEAR],
                    team=scope_team,
                ),
            },
        ]

        # --- Donut: distribución por estado ------------------------------
        ctx["status_distribution"] = [
            {
                "key": s.value,
                "label": s.label,
                "value": counts.get(s.value, 0),
                "family": STATUS_FAMILY[s],
                "color": _status_color(s),
                "href": _list_url(status=s.value, team=scope_team),
            }
            for s in CertificateStatus
        ]

        # --- Barras: ventanas de vencimiento -----------------------------
        # Buckets por cota superior, sin solape. El primero incluye vencidos
        # (días < 7, también negativos): ``days_left < 7``. El resto añade cota
        # inferior ``days_left >= prev``. El conteo de cada barra == filas del
        # drill (mismos filtros days_gte/days_lt).
        windows = []
        prev = None
        for w in EXPIRY_WINDOWS:
            q = Q(days_left__lt=w)
            drill = {"days_lt": w, "team": scope_team}
            if prev is not None:
                q &= Q(days_left__gte=prev)
                drill["days_gte"] = prev
            n = certs.filter(q).count()
            windows.append({
                "label": f"≤{w}d",
                "value": n,
                "family": WINDOW_FAMILY[w],
                "window_min": prev,   # None en el primero (incluye vencidos)
                "window_max": w,
                "href": _list_url(**drill),
            })
            prev = w
        ctx["expiry_windows"] = windows
        # Cota de escala para el ancho de las barras (>=1 para evitar /0).
        ctx["max_window_value"] = max([w["value"] for w in windows] + [1])

        # --- Tabla "Requieren atención" (compacta) -----------------------
        ctx["attention"] = (
            certs.filter(status__in=ATTENTION_STATUSES)
            .select_related("team")
            .order_by("days_left")[:5]
        )
        ctx["attention_href"] = _list_url(
            status=[
                CertificateStatus.VENCIDO,
                CertificateStatus.CRITICO,
                CertificateStatus.POR_VENCER,
            ],
            team=scope_team,
        )

        # --- Actividad reciente: últimas alertas abiertas del ámbito -----
        ctx["recent_alerts"] = (
            Alert.objects.filter(certificate__in=certs, status=AlertStatus.OPEN)
            .select_related("certificate")
            .order_by("-created_at")[:8]
        )

        # --- Tendencia (real, últimas 8 semanas) -------------------------
        ctx["trend"] = _weekly_trend(certs, timezone.now())

        ctx["scope_team"] = scope_team
        return ctx


def _check_all_worker(cert_ids) -> int:
    """Ejecuta el chequeo REAL de cada certificado por id y devuelve cuántos
    terminaron sin reventar.

    Función pura de orquestación (sin hilos ni conexiones): corre ``run_check``
    (mismo runner que "Probar ahora" y el command ``check_certificates``;
    ``notify=False`` porque es un re-chequeo manual y no debe disparar alertas).
    Un fallo aislado se registra y NO detiene el lote. Es directamente testeable.
    """
    from apps.monitoring.runner import run_check

    ok = 0
    certs = Certificate.objects.filter(id__in=cert_ids).select_related("team")
    for cert in certs:
        try:
            run_check(cert, notify=False)
            ok += 1
        except Exception:  # noqa: BLE001 — un fallo aislado no detiene el lote.
            logger.exception("Chequear todo: run_check falló (cert_id=%s)", cert.pk)
            continue
    return ok


def _dispatch_check_all(cert_ids) -> threading.Thread:
    """Lanza ``_check_all_worker`` en un hilo en segundo plano (no bloquea la
    petición). Cierra las conexiones de BD del hilo al terminar para no filtrar
    sockets. Devuelve el hilo (útil en pruebas)."""
    ids = list(cert_ids)

    def _run():
        try:
            _check_all_worker(ids)
        finally:
            from django.db import connections

            connections.close_all()

    thread = threading.Thread(target=_run, name="check-all", daemon=True)
    thread.start()
    return thread


class DashboardCheckAllView(LoginRequiredMixin, View):
    """"Chequear todo" atado al scope activo: dispara el chequeo REAL en segundo
    plano (no bloquea la petición, aguanta inventarios grandes).

    Cuenta los certificados del ámbito, lanza ``_dispatch_check_all`` y responde:

    - un **toast OOB** con el conteo real en curso ("Chequeo en curso para N…");
    - una cabecera ``HX-Trigger: cf:check-all-started`` para que el dashboard
      refresque sus KPIs (los estados van actualizándose conforme terminan los
      chequeos; una recarga posterior muestra el resultado final).

    Responde a ``POST`` (acción con efecto) y exige sesión.
    """

    def post(self, request, *args, **kwargs):
        certs = _scoped_certificates(request)
        cert_ids = list(certs.values_list("id", flat=True))
        total = len(cert_ids)

        if total:
            _dispatch_check_all(cert_ids)

        if total == 0:
            msg = _("No hay certificados en este ámbito para chequear.")
        elif total == 1:
            msg = _("Chequeo en curso para 1 certificado…")
        else:
            msg = _("Chequeo en curso para %(total)s certificados…") % {"total": total}

        html = render_to_string(
            "dashboard/_check_all_toast.html",
            {"count": total, "message": msg},
            request=request,
        )
        resp = HttpResponse(html)
        # Refresca los KPIs (el dashboard escucha este evento por hx-trigger).
        resp["HX-Trigger"] = "cf:check-all-started"
        return resp
