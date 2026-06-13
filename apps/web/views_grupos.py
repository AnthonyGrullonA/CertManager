"""Vistas server-rendered de la pantalla Grupos (Forge UI).

- ``team-list``: lista de grupos con GroupHealthMini (salud apilada por estado).
- ``team-create``: modal HTMX "Nuevo grupo" (GET abre, POST crea + fila nueva).

Scope/RBAC: el Owner ve todos los grupos; un no-Owner ve solo los suyos.
Crear grupo es exclusivo del Owner (403 en caso contrario).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, View

from apps.certificates.models import Certificate
from apps.core.enums import CertificateStatus, MembershipRole
from apps.teams.forms import TeamForm
from apps.teams.models import Membership, Team
from apps.teams.permissions import can_view

User = get_user_model()

# Familias Forge en orden de la barra apilada (espejo de GroupHealthMini.jsx).
HEALTH_ORDER = ["exp", "crit", "warn", "ok", "err", "none"]

# Estado backend -> familia Forge (espejo de status_family).
STATUS_TO_FAMILY = {
    CertificateStatus.VIGENTE: "ok",
    CertificateStatus.POR_VENCER: "warn",
    CertificateStatus.CRITICO: "crit",
    CertificateStatus.VENCIDO: "exp",
    CertificateStatus.ERROR: "err",
    CertificateStatus.SIN_CHEQUEAR: "none",
}


def _health_counts(team):
    """Conteo de certificados por familia Forge para la barra de salud."""
    rows = (
        Certificate.objects.for_team(team).values_list("status").annotate(n=Count("id"))
    )
    counts = {fam: 0 for fam in HEALTH_ORDER}
    for status, n in rows:
        fam = STATUS_TO_FAMILY.get(status, "none")
        counts[fam] += n
    return counts


def _health_segments(counts):
    """Lista de segmentos no vacíos con su porcentaje, para la plantilla."""
    total = sum(counts.values()) or 1
    segments = []
    for fam in HEALTH_ORDER:
        val = counts.get(fam, 0)
        if val:
            segments.append({"family": fam, "value": val, "pct": val * 100 / total})
    return segments


def _decorate_team(team):
    """Adjunta datos derivados (salud, conteos, admins) usados por la lista."""
    counts = _health_counts(team)
    team.health_segments = _health_segments(counts)
    team.health_total = sum(counts.values())
    team.cert_count = team.health_total
    team.member_count = team.memberships.count()
    team.default_email = (team.default_recipients or [""])[0] if team.default_recipients else ""
    return team


class TeamListView(LoginRequiredMixin, ListView):
    template_name = "grupos/list.html"
    context_object_name = "teams"

    def get_queryset(self):
        return (
            Team.objects.for_user(self.request.user)
            .prefetch_related("memberships__user", "certificates")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["teams"] = [_decorate_team(t) for t in ctx["teams"]]
        ctx["can_create"] = bool(getattr(self.request.user, "is_owner", False))
        return ctx


class TeamCreateView(LoginRequiredMixin, View):
    """Modal HTMX para crear un grupo. Solo el Owner puede crear."""

    def _check_owner(self):
        if not getattr(self.request.user, "is_owner", False):
            raise PermissionDenied(_("Solo el Owner puede crear grupos."))

    def get(self, request, *args, **kwargs):
        self._check_owner()
        html = render_to_string(
            "grupos/_create_modal.html",
            {"form": TeamForm()},
            request=request,
        )
        return _html(html)

    def post(self, request, *args, **kwargs):
        self._check_owner()
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save(commit=False)
            team.created_by = request.user
            team.save()
            _decorate_team(team)
            html = render_to_string(
                "grupos/_row_created.html",
                {"team": team},
                request=request,
            )
            return _html(html)
        # Form inválido: re-renderiza el modal con errores (HTMX reemplaza root).
        html = render_to_string(
            "grupos/_create_modal.html",
            {"form": form},
            request=request,
        )
        return _html(html, status=422)


def _html(html, status=200):
    from django.http import HttpResponse

    return HttpResponse(html, status=status, content_type="text/html; charset=utf-8")


# ===========================================================================
# Detalle de grupo (overview + gestión de miembros inline).
# ===========================================================================
MEMBER_ROLE_ORDER = {
    MembershipRole.CONTRIBUTOR: 0,
    MembershipRole.VIEWER: 1,
}


def _get_team_visible(user, pk):
    """Grupo visible para el usuario (Owner o miembro); si no, 404."""
    team = get_object_or_404(Team, pk=pk)
    if not (getattr(user, "is_owner", False) or can_view(user, team)):
        raise Http404("Grupo no encontrado")
    return team


def _can_manage_team(user, team):
    """Gestiona miembros: SOLO el Owner global (el rol Admin de grupo no existe)."""
    return bool(getattr(user, "is_owner", False))


def _members_context(team, user):
    """Miembros ordenados por rol y nombre + datos para la gestión inline."""
    memberships = list(
        team.memberships.select_related("user", "user__preferences").all()
    )
    memberships.sort(
        key=lambda m: (
            MEMBER_ROLE_ORDER.get(m.role, 9),
            (m.user.get_full_name() or m.user.email).lower(),
        )
    )
    can_manage = _can_manage_team(user, team)
    available = []
    if can_manage:
        member_ids = [m.user_id for m in memberships]
        available = list(
            User.objects.filter(is_active=True)
            .exclude(id__in=member_ids)
            .order_by("first_name", "email")
        )
    return {
        "team": team,
        "memberships": memberships,
        "can_manage": can_manage,
        "available_users": available,
        "roles": MembershipRole.choices,
        "request_user_id": user.id,
    }


class TeamDetailView(LoginRequiredMixin, View):
    """Overview de un grupo: salud, miembros (con gestión), certificados y
    valores por defecto. Visible para miembros del grupo y el Owner."""

    CERT_PREVIEW = 12

    def get(self, request, pk, *args, **kwargs):
        team = _get_team_visible(request.user, pk)
        _decorate_team(team)
        certs = list(Certificate.objects.for_team(team).order_by("domain")[: self.CERT_PREVIEW])
        ctx = _members_context(team, request.user)
        ctx["certificates"] = certs
        # Overview: no listamos cientos; mostramos un preview + enlace al listado.
        ctx["cert_more"] = max(0, team.cert_count - len(certs))
        return render(request, "grupos/detail.html", ctx)


class _MemberActionView(LoginRequiredMixin, View):
    """Base de acciones de miembros: resuelve el grupo, gatea la gestión y
    devuelve la región de miembros (#group-members) refrescada."""

    def _team_managed(self, request, pk):
        team = _get_team_visible(request.user, pk)
        if not _can_manage_team(request.user, team):
            raise PermissionDenied(
                _("Solo el Owner o un Admin del grupo puede gestionar miembros.")
            )
        return team

    def _render_members(self, request, team):
        ctx = _members_context(team, request.user)
        ctx["oob"] = True  # refresca también el contador de miembros (OOB)
        html = render_to_string("grupos/_members.html", ctx, request=request)
        return _html(html)


class TeamMemberAddView(_MemberActionView):
    def post(self, request, pk, *args, **kwargs):
        team = self._team_managed(request, pk)
        try:
            target = User.objects.get(pk=request.POST.get("user"), is_active=True)
        except (User.DoesNotExist, ValueError, TypeError):
            return _html(str(_("Selecciona un usuario válido.")), status=422)
        role = request.POST.get("role")
        if role not in MembershipRole.values:
            role = MembershipRole.VIEWER
        Membership.objects.get_or_create(
            user=target, team=team, defaults={"role": role}
        )
        return self._render_members(request, team)


class TeamMemberRoleView(_MemberActionView):
    def post(self, request, pk, user_id, *args, **kwargs):
        team = self._team_managed(request, pk)
        role = request.POST.get("role")
        if role not in MembershipRole.values:
            return _html(str(_("Rol inválido.")), status=422)
        Membership.objects.filter(team=team, user_id=user_id).update(role=role)
        return self._render_members(request, team)


class TeamMemberRemoveView(_MemberActionView):
    def post(self, request, pk, user_id, *args, **kwargs):
        team = self._team_managed(request, pk)
        Membership.objects.filter(team=team, user_id=user_id).delete()
        return self._render_members(request, team)


class TeamEditView(LoginRequiredMixin, View):
    """Editar los ajustes de un grupo (Owner o Admin del grupo). Modal HTMX.
    Al guardar dispara cf:team-updated para refrescar el detalle sin recargar."""

    def _team_managed(self, request, pk):
        team = _get_team_visible(request.user, pk)
        if not _can_manage_team(request.user, team):
            raise PermissionDenied(_("Solo el Owner o un Admin del grupo puede editarlo."))
        return team

    def get(self, request, pk, *args, **kwargs):
        team = self._team_managed(request, pk)
        form = TeamForm(instance=team)
        return _html(render_to_string(
            "grupos/_edit_modal.html", {"form": form, "team": team}, request=request,
        ))

    def post(self, request, pk, *args, **kwargs):
        team = self._team_managed(request, pk)
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            html = render_to_string(
                "partials/_toast.html",
                {"tone": "ok", "title": _("Grupo actualizado"),
                 "message": _("Los cambios se guardaron correctamente.")},
                request=request,
            )
            resp = _html(html)
            resp["HX-Trigger"] = "cf:team-updated"
            return resp
        return _html(render_to_string(
            "grupos/_edit_modal.html", {"form": form, "team": team}, request=request,
        ), status=422)
