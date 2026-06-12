"""Vistas del módulo de plantillas de correo.

- Lista y creación: cualquier usuario autenticado (uso global).
- Editar / borrar / predeterminar: Owner, Admin de grupo o el creador.
"""
from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import ListView

from apps.core.enums import TemplateKind

from .forms import EmailTemplateForm
from .models import EmailTemplate
from .permissions import can_create_template, can_edit_template
from .render import render_email
from .variables import mandatory_fields, variables_for

# Contexto de ejemplo para la vista previa.
SAMPLE = {
    "CERT": {
        "dominio": "api.ejemplo.com", "puerto": "443", "estado": "Por vencer",
        "dias_restantes": "12", "vence_el": "2026-07-01", "emisor": "Let's Encrypt",
        "grupo": "Infraestructura", "severidad": "Crítico",
        "frase_estado": "vence en 12 días", "ultimo_chequeo": "2026-06-08 09:00",
    },
    "REPORT": {
        "nombre_reporte": "Inventario mensual", "total": "128",
        "resumen_kpis": "vigente: 110 · por_vencer: 12 · vencido: 6",
        "alcance": "Todos los grupos", "generado_el": "08/06/2026 09:00",
        "rango_fechas": "Últimos 30 días", "plantilla_label": "Inventario",
    },
}


def _html(s, status=200):
    return HttpResponse(s, status=status, content_type="text/html; charset=utf-8")


def _builder_context(request, form, kind):
    return {
        "form": form,
        "kind": kind,
        "kinds": TemplateKind.choices,
        "variables": variables_for(kind),
        "mandatory": sorted(mandatory_fields(kind)),
        "all_variables": {k: variables_for(k) for k in TemplateKind.values},
        "mandatory_by_kind": {k: sorted(mandatory_fields(k)) for k in TemplateKind.values},
    }


class MailTemplateListView(LoginRequiredMixin, ListView):
    template_name = "plantillas/list.html"
    context_object_name = "templates"

    def get_queryset(self):
        qs = EmailTemplate.objects.all().select_related("team", "created_by").order_by("kind", "name")
        kind = self.request.GET.get("kind")
        if kind in TemplateKind.values:
            qs = qs.filter(kind=kind)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tpls = list(ctx["templates"])
        for t in tpls:
            t.user_can_edit = can_edit_template(self.request.user, t)
        ctx["templates"] = tpls
        ctx["kinds"] = TemplateKind.choices
        ctx["active_kind"] = self.request.GET.get("kind", "")
        ctx["can_create"] = can_create_template(self.request.user)
        return ctx


class MailTemplateCreateView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if not can_create_template(request.user):
            raise PermissionDenied
        kind = request.GET.get("kind") if request.GET.get("kind") in TemplateKind.values else "CERT"
        form = EmailTemplateForm(user=request.user, initial={"kind": kind})
        return _html(render_to_string("plantillas/builder.html",
                                      _builder_context(request, form, kind), request=request))

    def post(self, request, *args, **kwargs):
        if not can_create_template(request.user):
            raise PermissionDenied
        form = EmailTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            return redirect("mailtemplate-list")
        kind = request.POST.get("kind") if request.POST.get("kind") in TemplateKind.values else "CERT"
        return _html(render_to_string("plantillas/builder.html",
                                      _builder_context(request, form, kind), request=request), status=422)


class MailTemplateEditView(LoginRequiredMixin, View):
    def _get(self, request, pk):
        tpl = get_object_or_404(EmailTemplate, pk=pk)
        if not can_edit_template(request.user, tpl):
            raise PermissionDenied
        return tpl

    def get(self, request, pk, *args, **kwargs):
        tpl = self._get(request, pk)
        form = EmailTemplateForm(instance=tpl, user=request.user)
        return _html(render_to_string("plantillas/builder.html",
                                      _builder_context(request, form, tpl.kind), request=request))

    def post(self, request, pk, *args, **kwargs):
        tpl = self._get(request, pk)
        form = EmailTemplateForm(request.POST, instance=tpl, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("mailtemplate-list")
        return _html(render_to_string("plantillas/builder.html",
                                      _builder_context(request, form, tpl.kind), request=request), status=422)


class MailTemplateDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        tpl = get_object_or_404(EmailTemplate, pk=pk)
        if not can_edit_template(request.user, tpl):
            raise PermissionDenied
        tpl.delete()
        return redirect("mailtemplate-list")


class MailTemplateDetailPreviewView(LoginRequiredMixin, View):
    """Overview de una plantilla GUARDADA (clic en la fila) con datos de ejemplo."""

    def get(self, request, pk, *args, **kwargs):
        tpl = get_object_or_404(EmailTemplate, pk=pk)
        rendered = render_email(tpl, SAMPLE.get(tpl.kind, {}))
        return _html(render_to_string(
            "plantillas/_preview_modal.html",
            {"rendered": rendered, "tpl": tpl, "can_edit": can_edit_template(request.user, tpl)},
            request=request,
        ))


class MailTemplatePreviewView(LoginRequiredMixin, View):
    """Renderiza la plantilla en curso con datos de ejemplo (modal)."""

    def post(self, request, *args, **kwargs):
        kind = request.POST.get("kind") if request.POST.get("kind") in TemplateKind.values else "CERT"
        try:
            blocks = json.loads(request.POST.get("blocks_json") or "[]")
            if not isinstance(blocks, list):
                blocks = []
        except (ValueError, TypeError):
            blocks = []
        transient = EmailTemplate(kind=kind, subject=request.POST.get("subject", ""), blocks=blocks)
        rendered = render_email(transient, SAMPLE.get(kind, {}))
        return _html(render_to_string("plantillas/_preview_modal.html",
                                      {"rendered": rendered}, request=request))
