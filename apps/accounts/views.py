"""Vistas de autenticación de CertManager (Forge UI).

``CustomLoginView`` extiende ``django.contrib.auth.views.LoginView`` para usar
``EmailAuthenticationForm`` (etiqueta "Correo").

Hay un **único botón** de inicio de sesión: el mismo formulario
(``username``/``password``) se valida contra los backends de
``AUTHENTICATION_BACKENDS`` en orden (``ModelBackend`` y luego
``DatabaseLDAPBackend``), así que no hace falta un botón "SSO corporativo"
aparte. La sesión usa la duración por defecto del proyecto.
"""
from __future__ import annotations

import time

from django.conf import settings
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.shortcuts import redirect

from apps.accounts.models import user_has_2fa
from apps.core import audit

from .forms_auth import EmailAuthenticationForm

LOCK_MSG = (
    "Demasiados intentos fallidos. Por seguridad, el acceso quedó bloqueado "
    "temporalmente. Espera unos minutos e intenta de nuevo."
)


def _lock_key(ip, username):
    return f"loginlock:{ip}:{(username or '').strip().lower()}"


class CustomLoginView(LoginView):
    """Login Forge UI con bloqueo por fuerza bruta (OWASP A07).

    - Cuenta intentos fallidos por (IP, correo) en caché; tras N fallos bloquea
      durante un periodo configurable (LOGIN_LOCKOUT_*).
    - Si el usuario tiene 2FA activo, NO crea la sesión aún: guarda el usuario
      pre-autenticado y redirige al segundo paso (verificación TOTP).
    - Audita login correcto / fallido / bloqueado (OWASP A09).
    """

    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    @property
    def _max(self):
        return getattr(settings, "LOGIN_LOCKOUT_MAX", 5)

    @property
    def _window(self):
        return getattr(settings, "LOGIN_LOCKOUT_WINDOW", 300)

    @property
    def _duration(self):
        return getattr(settings, "LOGIN_LOCKOUT_DURATION", 900)

    def post(self, request, *args, **kwargs):
        self._ip = audit.client_ip(request)
        self._username = (request.POST.get("username") or "").strip()
        state = cache.get(_lock_key(self._ip, self._username))
        if state and state.get("locked_until", 0) > time.time():
            audit.log_event(
                "login_locked", object_repr=self._username,
                request=request, actor_email=self._username,
            )
            from django.forms.utils import ErrorDict

            form = self.get_form()
            form.cleaned_data = {}
            form._errors = ErrorDict()
            form.add_error(None, LOCK_MSG)
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = _lock_key(getattr(self, "_ip", ""), getattr(self, "_username", ""))
        state = cache.get(key) or {"fails": 0}
        state["fails"] = state.get("fails", 0) + 1
        if state["fails"] >= self._max:
            state["locked_until"] = time.time() + self._duration
            audit.log_event(
                "login_locked", object_repr=getattr(self, "_username", ""),
                request=self.request, actor_email=getattr(self, "_username", ""),
            )
            form.add_error(None, LOCK_MSG)
        else:
            audit.log_event(
                "login_failed", object_repr=getattr(self, "_username", ""),
                request=self.request, actor_email=getattr(self, "_username", ""),
                changes={"fails": state["fails"]},
            )
        cache.set(key, state, timeout=max(self._window, self._duration))
        return super().form_invalid(form)

    def form_valid(self, form):
        user = form.get_user()
        cache.delete(_lock_key(getattr(self, "_ip", ""), getattr(self, "_username", "")))
        # request.user aún es anónimo aquí (login() corre en super); pasamos actor.
        audit.log_event("login", object_repr=user.email, request=self.request,
                        actor=user, actor_email=user.email)
        if user_has_2fa(user):
            # Import local para evitar acoplar el módulo de auth con la capa web.
            from apps.web.views_2fa import SESSION_BACKEND, SESSION_NEXT, SESSION_USER

            self.request.session[SESSION_USER] = user.pk
            self.request.session[SESSION_BACKEND] = getattr(user, "backend", None)
            self.request.session[SESSION_NEXT] = self.get_success_url()
            return redirect("two-factor-verify")
        return super().form_valid(form)
