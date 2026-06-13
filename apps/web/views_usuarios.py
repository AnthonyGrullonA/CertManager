"""Pantalla Usuarios (PASO 10) — solo Owner.

Lista de usuarios con avatar/nombre/correo, rol global, grupos, último acceso y
estado, con búsqueda en vivo (HTMX). Modal de alta de usuario (correo, contraseña
local opcional o acceso LDAP, grupo(s) y rol de grupo) y acciones de fila.

RBAC: SOLO el Owner global accede. No-Owner recibe 403 (UserPassesTestMixin con
``raise_exception``). El item del sidebar ya se oculta por ``forge_is_owner``.
NUNCA se permite mass-assignment de ``is_owner`` desde la invitación.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import ListView, View

from apps.accounts.forms_edit import UserEditForm
from apps.accounts.forms_invite import CreateUserForm
from apps.teams.models import Membership, Team

User = get_user_model()


class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Acceso solo-Owner.

    - Anónimo: redirige al login (comportamiento de LoginRequiredMixin).
    - Autenticado no-Owner: 403 (no se le revela la existencia del recurso vía
      redirección a login). El item del sidebar ya está oculto por is_owner.
    """

    def test_func(self):
        return bool(getattr(self.request.user, "is_owner", False))

    def handle_no_permission(self):
        # Anónimo -> login; autenticado sin permiso -> 403.
        if not self.request.user.is_authenticated:
            return super(UserPassesTestMixin, self).handle_no_permission()
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied


class UserListView(OwnerRequiredMixin, ListView):
    """DataTable de usuarios con búsqueda por nombre/correo.

    Respuestas HTMX devuelven solo las filas (``_rows.html``) para el filtrado en
    vivo; las normales devuelven la página completa.
    """

    template_name = "usuarios/list.html"
    context_object_name = "users"

    def get_queryset(self):
        qs = User.objects.all().select_related("preferences").prefetch_related(
            Prefetch(
                "memberships",
                queryset=Membership.objects.select_related("team"),
            )
        ).order_by("email")
        search = (self.request.GET.get("q") or "").strip()
        if search:
            qs = qs.filter(email__icontains=search) | qs.filter(
                first_name__icontains=search
            ) | qs.filter(last_name__icontains=search)
            qs = qs.distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search"] = (self.request.GET.get("q") or "").strip()
        ctx["invite_form"] = CreateUserForm(
            groups_queryset=Team.objects.all().order_by("name")
        )
        return ctx

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["usuarios/_rows.html"]
        return [self.template_name]


class UserInviteView(OwnerRequiredMixin, View):
    """Modal de alta: GET devuelve el modal; POST crea el usuario.

    El POST válido devuelve la tabla recargada (OOB-friendly) con un toast de
    éxito vía ``window.cfToast`` disparado por el parcial.
    """

    def get(self, request, *args, **kwargs):
        form = CreateUserForm(groups_queryset=Team.objects.all().order_by("name"))
        return render(request, "usuarios/_invite_modal.html", {"form": form})

    def post(self, request, *args, **kwargs):
        form = CreateUserForm(
            request.POST, groups_queryset=Team.objects.all().order_by("name")
        )
        if form.is_valid():
            user = form.save()
            users = (
                User.objects.all()
                .select_related("preferences")
                .prefetch_related(
                    Prefetch(
                        "memberships",
                        queryset=Membership.objects.select_related("team"),
                    )
                )
                .order_by("email")
            )
            resp = render(
                request,
                "usuarios/_invite_success.html",
                {"users": users, "invited": user},
            )
            # Cierra el modal (el parcial vacía #modal-root vía OOB) y refresca.
            return resp
        return render(request, "usuarios/_invite_modal.html", {"form": form})


class UserToggleActiveView(OwnerRequiredMixin, View):
    """Activa/desactiva un usuario (acción de fila). Devuelve la fila refrescada.

    No permite que el Owner se desactive a sí mismo (evita lock-out).
    """

    def post(self, request, pk, *args, **kwargs):
        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk:
            return HttpResponse(
                _("No puedes desactivar tu propia cuenta."), status=400
            )
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        target = _user_with_memberships(target.pk)
        return render(request, "usuarios/_row.html", {"u": target})


def _user_with_memberships(pk):
    """Recarga un usuario con sus membresías (y grupos) prefetcheadas."""
    return (
        User.objects.filter(pk=pk)
        .select_related("preferences")
        .prefetch_related(
            Prefetch(
                "memberships",
                queryset=Membership.objects.select_related("team"),
            )
        )
        .first()
    )


class UserEditView(OwnerRequiredMixin, View):
    """Editar un usuario en un modal HTMX (solo Owner).

    GET devuelve el modal con el formulario; POST válido guarda y devuelve la
    fila actualizada (swap del propio ``<tr>``) + un toast de éxito. POST
    inválido re-renderiza el modal con errores.

    ANTI-ESCALADA: el formulario no expone ``is_owner``/``is_staff``; aunque se
    intente inyectar por el POST, se ignora (no está en ``Meta.fields``). Nadie
    puede auto-promoverse a Owner desde aquí.
    """

    def _groups_qs(self):
        return Team.objects.all().order_by("name")

    def get(self, request, pk, *args, **kwargs):
        target = get_object_or_404(User, pk=pk)
        form = UserEditForm(instance=target, groups_queryset=self._groups_qs())
        return render(
            request,
            "usuarios/_edit_modal.html",
            {"form": form, "target": target},
        )

    def post(self, request, pk, *args, **kwargs):
        target = get_object_or_404(User, pk=pk)
        # No permitir que el Owner se auto-desactive (evita lock-out), igual que
        # en la acción de fila.
        form = UserEditForm(
            request.POST, instance=target, groups_queryset=self._groups_qs()
        )
        if form.is_valid():
            if (
                target.pk == request.user.pk
                and not form.cleaned_data.get("is_active", True)
            ):
                form.add_error(
                    "is_active", _("No puedes desactivar tu propia cuenta.")
                )
            else:
                form.save()
                updated = _user_with_memberships(target.pk)
                resp = render(
                    request, "usuarios/_edit_success.html", {"u": updated}
                )
                # Refresca el detalle del usuario si está abierto (sin recargar).
                resp["HX-Trigger"] = "cf:user-updated"
                return resp
        return render(
            request,
            "usuarios/_edit_modal.html",
            {"form": form, "target": target},
        )


class UserResetPasswordView(OwnerRequiredMixin, View):
    """Restablece la contraseña de un usuario con una temporal (solo Owner).

    GET devuelve el modal de confirmación (checkbox opcional "enviar por
    correo"). POST genera la temporal, la fija con ``must_change_password`` (el
    middleware fuerza el cambio en el siguiente login) y devuelve el partial de
    éxito que la muestra UNA vez; nunca se persiste en claro. Si se pidió el
    correo, se envía en esta misma petición SIN la copia BCC de auditoría
    (filtraría la contraseña).

    Guardas: a uno mismo no (para eso está Perfil) y a usuarios LDAP tampoco
    (su credencial vive en el directorio, no aquí).
    """

    def get(self, request, pk, *args, **kwargs):
        target = get_object_or_404(User, pk=pk)
        return render(request, "usuarios/_reset_modal.html", {"target": target})

    def post(self, request, pk, *args, **kwargs):
        from apps.accounts.passwords import generate_temp_password

        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk:
            return HttpResponse(
                _("No puedes restablecer tu propia contraseña aquí; usa tu Perfil."),
                status=400,
            )
        if not target.has_usable_password():
            return HttpResponse(
                _("Este usuario inicia sesión por LDAP: su credencial se gestiona en el directorio."),
                status=400,
            )

        temp = generate_temp_password()
        target.set_password(temp)
        target.must_change_password = True
        target.save()

        mail_sent = mail_error = False
        if request.POST.get("send_email"):
            mail_sent = self._send_temp_password(target, temp)
            mail_error = not mail_sent

        return render(
            request,
            "usuarios/_reset_success.html",
            {
                "target": target,
                "temp_password": temp,
                "mail_sent": mail_sent,
                "mail_error": mail_error,
            },
        )

    @staticmethod
    def _send_temp_password(target, temp) -> bool:
        """Correo con la temporal. SIN BCC de auditoría (no filtrar la clave)."""
        from django.core.mail import EmailMessage

        from apps.core.mail import default_from_email, smtp_connection

        body = _(
            "Hola,\n\n"
            "Un administrador restableció tu contraseña de CertManager.\n\n"
            "Contraseña temporal: %(temp)s\n\n"
            "Al iniciar sesión se te pedirá definir una contraseña propia.\n"
        ) % {"temp": temp}
        try:
            EmailMessage(
                subject=_("CertManager — contraseña temporal"),
                body=body,
                from_email=default_from_email(),
                to=[target.email],
                connection=smtp_connection(),
            ).send()
            return True
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "No se pudo enviar la contraseña temporal a %s", target.email
            )
            return False


class UserDetailView(OwnerRequiredMixin, View):
    """Overview de lectura de un usuario (solo Owner): cuenta, rol global,
    grupos/roles, último acceso y estado de 2FA. Para cambios, reusa el modal de
    editar (botón "Editar" -> UserEditView)."""

    def get(self, request, pk, *args, **kwargs):
        from apps.accounts.models import TwoFactorDevice

        target = get_object_or_404(
            User.objects.select_related("preferences").prefetch_related(
                Prefetch(
                    "memberships",
                    queryset=Membership.objects.select_related("team"),
                )
            ),
            pk=pk,
        )
        memberships = sorted(
            target.memberships.all(),
            key=lambda m: (m.team.name or "").lower(),
        )
        two_factor_on = TwoFactorDevice.objects.filter(
            user=target, confirmed_at__isnull=False
        ).exists()
        return render(
            request,
            "usuarios/detail.html",
            {
                "target": target,
                "memberships": memberships,
                "two_factor_on": two_factor_on,
            },
        )
