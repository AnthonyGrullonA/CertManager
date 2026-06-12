"""2FA (TOTP) opcional por usuario — enrolamiento en Perfil + verificación en login.

- Perfil → Seguridad: activar (QR), confirmar el primer código, desactivar.
- Login: si el usuario tiene 2FA activo, tras validar la contraseña se pide el
  código TOTP en una vista intermedia antes de crear la sesión.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.models import TwoFactorDevice, user_has_2fa
from apps.accounts import totp

User = get_user_model()

# Claves de sesión del login en dos pasos.
SESSION_USER = "pending_2fa_user"
SESSION_BACKEND = "pending_2fa_backend"
SESSION_NEXT = "pending_2fa_next"
SESSION_ATTEMPTS = "pending_2fa_attempts"
MAX_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Enrolamiento (Perfil → Seguridad)
# ---------------------------------------------------------------------------
def _toast(tone, title, message):
    return render_to_string(
        "partials/_toast.html", {"tone": tone, "title": title, "message": message}
    )


def _render_security(request, *, setup=False, device=None, error=None):
    """Renderiza la sección de Seguridad del Perfil según el estado del 2FA."""
    user = request.user
    device = device if device is not None else getattr(user, "totp_device", None)
    ctx = {"two_factor_enabled": bool(device and device.enabled)}
    if setup and device is not None:
        uri = totp.provisioning_uri(device.secret, user.email)
        ctx["setup"] = True
        # Si qrcode no estuviera disponible, degradamos a "clave manual": el
        # template siempre muestra el secreto en texto para tipearlo en la app.
        try:
            ctx["qr_data_uri"] = totp.qr_data_uri(uri)
        except Exception:  # noqa: BLE001
            ctx["qr_data_uri"] = ""
        ctx["totp_secret"] = device.secret
        ctx["totp_uri"] = uri
    if error:
        ctx["totp_error"] = error
    return render_to_string("perfil/_section_security.html", ctx, request=request)


@login_required
@require_http_methods(["GET"])
def two_factor_setup(request):
    """Inicia el enrolamiento: genera secreto (sin confirmar) y muestra el QR."""
    if user_has_2fa(request.user):
        return HttpResponse(_render_security(request))
    device, _created = TwoFactorDevice.objects.get_or_create(
        user=request.user, defaults={"secret": totp.new_secret()}
    )
    # Reinicia el secreto si aún no estaba confirmado (re-enrolamiento limpio).
    if device.confirmed_at is None:
        device.secret = totp.new_secret()
        device.save(update_fields=["secret", "updated_at"])
    return HttpResponse(_render_security(request, setup=True, device=device))


@login_required
@require_http_methods(["POST"])
def two_factor_confirm(request):
    """Confirma el enrolamiento validando el primer código del autenticador."""
    device = getattr(request.user, "totp_device", None)
    code = request.POST.get("code", "")
    if device is None or device.enabled:
        return HttpResponse(_render_security(request))
    if not totp.verify(device.secret, code):
        html = _render_security(request, setup=True, device=device,
                                error=_("Código incorrecto. Revisa tu app y vuelve a intentar."))
        html += _toast("err", _("Código incorrecto"), _("No pudimos activar el 2FA."))
        return HttpResponse(html, status=422)
    device.confirmed_at = timezone.now()
    device.save(update_fields=["confirmed_at", "updated_at"])
    html = _render_security(request)
    html += _toast("ok", _("2FA activado"), _("Te pediremos un código al iniciar sesión."))
    return HttpResponse(html)


@login_required
@require_http_methods(["POST"])
def two_factor_disable(request):
    """Desactiva el 2FA validando un código vigente (borra el dispositivo)."""
    device = getattr(request.user, "totp_device", None)
    code = request.POST.get("code", "")
    if device is None or not device.enabled:
        return HttpResponse(_render_security(request))
    if not totp.verify(device.secret, code):
        html = _render_security(request, error=_("Código incorrecto."))
        html += _toast("err", _("Código incorrecto"), _("El 2FA sigue activo."))
        return HttpResponse(html, status=422)
    device.delete()
    html = _render_security(request)
    html += _toast("ok", _("2FA desactivado"), _("Ya no se pedirá código al iniciar sesión."))
    return HttpResponse(html)


# ---------------------------------------------------------------------------
# Verificación en el login (segundo paso)
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def two_factor_verify(request):
    """Segundo paso del login: pide el código TOTP del usuario pre-autenticado."""
    user_id = request.session.get(SESSION_USER)
    if not user_id:
        return redirect("login")
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        request.session.pop(SESSION_USER, None)
        return redirect("login")
    device = getattr(user, "totp_device", None)
    if device is None or not device.enabled:
        # No debería pasar; degradar a login normal.
        _clear_pending(request)
        return redirect("login")

    error = None
    if request.method == "POST":
        attempts = request.session.get(SESSION_ATTEMPTS, 0) + 1
        request.session[SESSION_ATTEMPTS] = attempts
        if attempts > MAX_ATTEMPTS:
            _clear_pending(request)
            return redirect("login")
        if totp.verify(device.secret, request.POST.get("code", "")):
            backend = request.session.get(SESSION_BACKEND) or settings.AUTHENTICATION_BACKENDS[0]
            next_url = request.session.get(SESSION_NEXT) or settings.LOGIN_REDIRECT_URL
            _clear_pending(request)
            auth_login(request, user, backend=backend)
            return redirect(next_url)
        error = _("Código incorrecto. Intenta de nuevo.")

    return render(request, "registration/two_factor_verify.html", {"error": error})


def _clear_pending(request):
    for key in (SESSION_USER, SESSION_BACKEND, SESSION_NEXT, SESSION_ATTEMPTS):
        request.session.pop(key, None)
