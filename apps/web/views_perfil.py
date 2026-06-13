"""Pantalla Perfil (paso 12): datos, preferencias, grupos, avatar.

Cada sección se guarda de forma parcial vía HTMX y responde con un toast
(``partials/_toast.html`` OOB). Las secciones operan sobre ``UserPreferences``
(creadas por señal al crear el usuario) y, para "Datos personales", sobre el
propio ``User``.

URLs expuestas (names): ``profile``, ``profile-section``, ``password-change``.
"""
from __future__ import annotations

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l
from django.views.generic import TemplateView

from apps.accounts.forms_profile import (
    AvatarChoiceForm,
    PersonalDataForm,
    PreferencesForm,
    ProfilePasswordChangeForm,
)
from apps.accounts.models import get_or_create_preferences, user_has_2fa


def _toast(tone, title, message):
    """Renderiza el parcial de toast OOB para empujar a #toast-host."""
    return render_to_string(
        "partials/_toast.html",
        {"tone": tone, "title": title, "message": message},
    )


def _my_groups(user):
    """Grupos del usuario con su rol por grupo (solo lectura)."""
    rows = []
    memberships = (
        user.memberships.select_related("team").order_by("team__name")
        if user.is_authenticated
        else []
    )
    for m in memberships:
        rows.append({"name": m.team.name, "role": m.get_role_display()})
    # El Owner global se rotula como "Owner" donde tenga membresía explícita;
    # si no tiene membresías, mostramos el estado vacío de la sección.
    if getattr(user, "is_owner", False):
        for row in rows:
            row["role"] = "Owner"
    return rows


@method_decorator(login_required, name="dispatch")
class ProfileView(TemplateView):
    """Página completa de Perfil con todas las secciones."""

    template_name = "perfil/profile.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        prefs = get_or_create_preferences(user)
        ctx["prefs"] = prefs
        ctx["personal_form"] = PersonalDataForm(instance=user)
        ctx["preferences_form"] = PreferencesForm(instance=prefs)
        ctx["avatar_choice_form"] = AvatarChoiceForm(instance=prefs)
        ctx["password_form"] = ProfilePasswordChangeForm(user=user)
        ctx["my_groups"] = _my_groups(user)
        ctx["display_name"] = user.get_full_name() or user.email
        ctx["display_role"] = "Owner" if user.is_owner else "Miembro"
        ctx["two_factor_enabled"] = user_has_2fa(user)
        # Banner cuando PasswordExpiryMiddleware redirige por contraseña vencida.
        ctx["password_expired"] = self.request.GET.get("password_expired") == "1"
        # Banner cuando la contraseña vigente es temporal (reset del Owner).
        ctx["password_reset"] = (
            self.request.GET.get("password_reset") == "1"
            or self.request.user.must_change_password
        )
        return ctx


# Mapa sección -> (Form, target_es_user, etiqueta toast, var_de_form, template).
# El avatar es SOLO SVG generado (avatar_choice); no se permite subir fotos.
_SECTIONS = {
    "personal": (PersonalDataForm, True, _l("Datos personales"), "personal_form", "personal"),
    "preferences": (PreferencesForm, False, _l("Preferencias"), "preferences_form", "preferences"),
    "avatar_choice": (AvatarChoiceForm, False, _l("Avatar"), "avatar_choice_form", "avatar"),
}


@login_required
def profile_section(request, section):
    """Guardado parcial HTMX de una sección. Devuelve fragmento + toast OOB."""
    if request.method != "POST" or section not in _SECTIONS:
        return HttpResponse(status=400)

    user = request.user
    prefs = get_or_create_preferences(user)
    form_cls, is_user_target, label, form_var, template = _SECTIONS[section]
    instance = user if is_user_target else prefs
    form = form_cls(request.POST, request.FILES, instance=instance)
    template_name = f"perfil/_section_{template}.html"

    if form.is_valid():
        form.save()
        # Reconstruimos un form limpio para reflejar valores guardados.
        fresh = form_cls(
            instance=user if is_user_target else get_or_create_preferences(user)
        )
        html = render_to_string(
            template_name,
            {
                form_var: fresh,
                "prefs": get_or_create_preferences(user),
                "user": user,
                "display_name": user.get_full_name() or user.email,
            },
            request=request,
        )
        html += _toast("ok", _("Cambios guardados"), _("%(label)s actualizado.") % {"label": label})
        return HttpResponse(html)

    # Errores -> re-render del fragmento con errores + toast de error.
    html = render_to_string(
        template_name,
        {
            form_var: form,
            "prefs": prefs,
            "user": user,
            "display_name": user.get_full_name() or user.email,
        },
        request=request,
    )
    html += _toast("err", _("Revisa el formulario"), _("Hay datos por corregir."))
    return HttpResponse(html, status=422)


@login_required
def password_change(request):
    """Cambio de contraseña (modal). GET abre el modal; POST procesa."""
    if request.method == "GET":
        form = ProfilePasswordChangeForm(user=request.user)
        return render(request, "perfil/_password_modal.html", {"password_form": form})

    form = ProfilePasswordChangeForm(user=request.user, data=request.POST)
    if form.is_valid():
        form.save()
        # La nueva contraseña ya es del usuario: levanta el forzado del reset.
        if form.user.must_change_password:
            form.user.must_change_password = False
            form.user.save(update_fields=["must_change_password"])
        # Mantener la sesión activa tras cambiar la contraseña.
        update_session_auth_hash(request, form.user)
        # Vaciar el modal y empujar el toast de éxito.
        html = '<div id="modal-root"></div>'
        html += _toast("ok", _("Contraseña actualizada"), _("Tu contraseña se cambió correctamente."))
        return HttpResponse(html)

    html = render_to_string(
        "perfil/_password_modal.html",
        {"password_form": form},
        request=request,
    )
    html += _toast("err", _("No se pudo cambiar"), _("Revisa los datos ingresados."))
    return HttpResponse(html, status=422)
