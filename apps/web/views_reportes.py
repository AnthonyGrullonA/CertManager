"""Pantalla Reportes (Forge UI): constructor + preview en vivo + export + CRUD.

Vistas server-rendered (HTMX) de la pantalla de Reportes. NO toca las urls
compartidas: se cablea en el PASO 14. Toda consulta respeta el scoping del
usuario (``Certificate.objects.for_user`` / ``Team.objects.for_user``).

- ``report_list``: página completa (constructor + preview inicial + lista de
  programados). Con cabecera ``HX-Request`` devuelve solo el parcial de preview
  (filtrado en vivo).
- ``report_preview``: parcial de preview (donut + barras + tabla + EmptyState).
- ``report_export``: descarga síncrona respetando los filtros; multi-formato
  simultáneo (PDF + Excel + CSV) empaquetado en ZIP.
- ``report_create`` / ``report_edit`` / ``report_delete``: CRUD de
  ``ScheduledReport`` vía modal HTMX. El envío real se difiere a un
  management-command (Celery DIFERIDO).
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.reports.forms import ReportBuilderForm, ScheduledReportForm
from apps.core.mail import smtp_connection
from apps.reports.management.commands.send_scheduled_reports import (
    _filters_for,
    generate_and_send,
)
from apps.reports.models import ScheduledReport
from apps.reports.services import ReportFilters, build_export, build_report
from apps.teams.models import Team


def _scope_label(request):
    """Etiqueta del ámbito activo, reusando el context processor del chrome."""
    from apps.web.context_processors import forge_globals

    return forge_globals(request).get("forge_scope_label", "Todos los grupos")


def _scheduled_for_user(user):
    """Reportes programados visibles para el usuario (scoping por grupo)."""
    qs = ScheduledReport.objects.select_related("team").order_by("name")
    if getattr(user, "is_owner", False):
        return qs
    team_ids = list(user.memberships.values_list("team_id", flat=True))
    # Visibles: los de sus grupos o los globales (team vacío) creados por ellos.
    from django.db.models import Q

    return qs.filter(Q(team_id__in=team_ids) | Q(created_by=user))


def _build_result(request):
    filters = ReportFilters.from_request(request.GET, multi=True)
    return filters, build_report(
        request.user,
        filters,
        scope_label=_scope_label(request),
    )


@login_required
def report_list(request):
    """Página de Reportes. HTMX -> solo el parcial de preview (filtrado en vivo)."""
    form = ReportBuilderForm(request.GET or None, user=request.user)
    _filters, result = _build_result(request)

    if request.headers.get("HX-Request"):
        return render(request, "reportes/_preview.html", {"result": result})

    ctx = {
        "form": form,
        "result": result,
        "scheduled": _scheduled_for_user(request.user),
        "scope_label": _scope_label(request),
    }
    return render(request, "reportes/list.html", ctx)


@login_required
def report_preview(request):
    """Parcial de preview en vivo (donut + barras + tabla + EmptyState)."""
    _filters, result = _build_result(request)
    return render(request, "reportes/_preview.html", {"result": result})


@login_required
def report_export(request):
    """Descarga síncrona respetando los filtros. Multi-formato -> ZIP."""
    _filters, result = _build_result(request)
    formats = request.GET.getlist("formats") or [request.GET.get("format", "CSV")]
    content, content_type, filename = build_export(result, formats)
    resp = HttpResponse(content, content_type=content_type)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _render_modal(request, form, *, action_url, title, submit_label, error=False):
    html = render_to_string(
        "reportes/_schedule_modal.html",
        {"form": form, "action_url": action_url, "title": title, "submit_label": submit_label},
        request=request,
    )
    resp = HttpResponse(html)
    if error:
        # En error de validación, re-pinta el modal en #modal-root (el form apunta
        # a #scheduled-list para el éxito). El JS del modal usa HX-Reswap como
        # señal de "no cerrar".
        resp["HX-Retarget"] = "#modal-root"
        resp["HX-Reswap"] = "innerHTML"
    return resp


def _render_list(request, *, status=200):
    """Devuelve el parcial OOB de la lista de programados (refresco tras CRUD)."""
    html = render_to_string(
        "reportes/_scheduled_list.html",
        {"scheduled": _scheduled_for_user(request.user), "oob": True},
        request=request,
    )
    return HttpResponse(html, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def report_create(request):
    """Crea un reporte programado vía modal HTMX."""
    if request.method == "POST":
        form = ScheduledReportForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return _render_list(request)
        return _render_modal(
            request, form,
            action_url=reverse("report-create"),
            title="Programar reporte",
            submit_label="Programar envío",
            error=True,
        )
    form = ScheduledReportForm(
        user=request.user,
        initial={"formats": ["PDF"], "frequency": "WEEKLY", "send_time": "08:00"},
    )
    return _render_modal(
        request, form,
        action_url=reverse("report-create"),
        title="Programar reporte",
        submit_label="Programar envío",
    )


@login_required
@require_http_methods(["GET", "POST"])
def report_edit(request, pk):
    """Edita un reporte programado vía modal HTMX (con scoping)."""
    report = get_object_or_404(_scheduled_for_user(request.user), pk=pk)
    if request.method == "POST":
        form = ScheduledReportForm(request.POST, instance=report, user=request.user)
        if form.is_valid():
            form.save()
            return _render_list(request)
        return _render_modal(
            request, form,
            action_url=reverse("report-edit", args=[report.pk]),
            title="Editar reporte programado",
            submit_label="Guardar cambios",
            error=True,
        )
    form = ScheduledReportForm(instance=report, user=request.user)
    return _render_modal(
        request, form,
        action_url=reverse("report-edit", args=[report.pk]),
        title="Editar reporte programado",
        submit_label="Guardar cambios",
    )


@login_required
@require_http_methods(["POST", "DELETE"])
def report_delete(request, pk):
    """Elimina un reporte programado (con scoping) y refresca la lista."""
    report = get_object_or_404(_scheduled_for_user(request.user), pk=pk)
    report.delete()
    return _render_list(request)


@login_required
def report_preview_scheduled(request, pk):
    """Preview de un reporte PROGRAMADO: arma sus filtros guardados y los muestra.

    Se abre en un drawer (clic en una fila de la lista de programados): permite
    ver "qué saca" ese reporte sin tener que reconstruir los filtros a mano.
    """
    report = get_object_or_404(_scheduled_for_user(request.user), pk=pk)
    filters = _filters_for(report)
    result = build_report(report.created_by or request.user, filters)
    return render(
        request,
        "reportes/_scheduled_preview.html",
        {"report": report, "result": result},
    )


@login_required
@require_http_methods(["POST"])
def report_test_send(request, pk):
    """Envía YA el reporte programado a un correo de prueba (toast con resultado)."""
    report = get_object_or_404(_scheduled_for_user(request.user), pk=pk)
    email = (request.POST.get("email") or "").strip()
    try:
        validate_email(email)
    except ValidationError:
        return _toast(request, tone="err", title=_("Correo inválido"),
                      message=_("Escribe una dirección de correo válida."), status=200)
    try:
        # Usa el SMTP configurado en OrganizationSettings (igual que el cron),
        # NO el backend por defecto (que en local es 'console' y no entrega nada).
        result = generate_and_send(report, [email], connection=smtp_connection())
    except Exception as exc:  # noqa: BLE001
        return _toast(request, tone="err", title=_("No se pudo enviar"),
                      message=str(exc), status=200)
    return _toast(
        request, tone="ok", title=_("Prueba enviada"),
        message=_("«%(name)s» (%(total)s certs) enviado a %(email)s.") % {"name": report.name, "total": result.total, "email": email},
    )


def _toast(request, *, tone, title, message, status=200):
    html = render_to_string(
        "partials/_toast.html",
        {"tone": tone, "title": title, "message": message},
        request=request,
    )
    return HttpResponse(html, status=status)
