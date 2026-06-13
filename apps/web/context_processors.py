"""Context processor global de Forge UI (PASO 3).

`forge_globals(request)` inyecta en TODAS las plantillas el chrome compartido:

- **Ámbito (scope):** grupos visibles del usuario + ámbito activo, con la
  precedencia congelada en el plan: querystring ``team`` › cookie ``cf_scope`` ›
  default (Owner → "Todos los grupos"; resto → su primer grupo).
- **Panel de notificaciones:** lista alertas ``OPEN`` del ámbito que el usuario
  NO ha limpiado: ``dismissed_at IS NULL`` (AlertUserState) y ``created_at >
  panel_cleared_at`` (UserPreferences). El badge cuenta solo las nuevas/no
  leídas dentro de ese conjunto.
- **Usuario:** nombre, iniciales y rol efectivo en el ámbito activo.
- **Monitoreo:** ``check_interval_hours`` (pie del sidebar).

Diseñado para no fallar nunca durante el render (usuario anónimo, sin
preferencias, sin grupos): cada rama degrada a valores vacíos seguros.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext as _


def asset_version(request):
    """Token de cache-busting para el CSS compilado (su mtime). Hace que tras un
    ``npm run build:css`` el navegador baje el forge.css nuevo sin hard-refresh.
    Fail-safe: si no puede leer el archivo, devuelve un valor estable."""
    try:
        path = os.path.join(settings.BASE_DIR, "static", "css", "forge.css")
        return {"forge_assets_v": str(int(os.path.getmtime(path)))}
    except Exception:  # noqa: BLE001
        return {"forge_assets_v": "1"}

from apps.core.enums import MembershipRole

# Constante de presentación: el ámbito "todos los grupos" (solo Owner).
SCOPE_ALL = "all"
SCOPE_COOKIE = "cf_scope"


def _initials(name: str, email: str) -> str:
    """Iniciales (máx. 2) a partir del nombre; cae al email si no hay nombre."""
    source = (name or "").strip()
    if source:
        parts = source.split()[:2]
        return "".join(p[0] for p in parts if p).upper() or "?"
    if email:
        return email[0].upper()
    return "?"


def forge_globals(request):
    """Globales del chrome de Forge UI para todas las plantillas."""
    user = getattr(request, "user", None)
    check_interval_hours = settings.MONITORING.get("CHECK_INTERVAL_HOURS", 24)

    # Estructura por defecto (usuario anónimo / páginas de auth).
    empty = {
        "forge_groups": [],
        "forge_scope": SCOPE_ALL,
        "forge_scope_label": _("Todos los grupos"),
        "forge_is_owner": False,
        "forge_user_name": "",
        "forge_user_initials": "?",
        "forge_user_email": "",
        "forge_user_role": "",
        "forge_user_avatar_choice": 0,
        "forge_panel_count": 0,
        "forge_check_interval_hours": check_interval_hours,
        "sidebar_collapsed": False,
    }

    sidebar_collapsed = request.COOKIES.get("cf_sidebar") == "collapsed"
    empty["sidebar_collapsed"] = sidebar_collapsed

    if user is None or not user.is_authenticated:
        return empty

    is_owner = bool(getattr(user, "is_owner", False))

    # --- Grupos visibles -------------------------------------------------
    # Import perezoso: evita ciclos de import en el arranque de Django.
    from apps.teams.models import Membership, Team

    groups_qs = Team.objects.for_user(user).order_by("name")
    groups = [{"id": t.id, "slug": t.slug, "name": t.name} for t in groups_qs]

    # Rol por grupo del usuario (para el rol efectivo en el ámbito activo).
    roles_by_team = dict(
        Membership.objects.filter(user=user).values_list("team_id", "role")
    )

    # --- Ámbito activo (precedencia: querystring › cookie › default) -----
    raw_scope = (
        request.GET.get("team")
        or request.COOKIES.get(SCOPE_COOKIE)
        or ""
    ).strip()

    valid_ids = {str(g["id"]) for g in groups}
    scope = SCOPE_ALL
    scope_team = None

    if raw_scope and raw_scope != SCOPE_ALL and raw_scope in valid_ids:
        scope = raw_scope
        scope_team = next((g for g in groups if str(g["id"]) == raw_scope), None)
    elif raw_scope == SCOPE_ALL and is_owner:
        scope = SCOPE_ALL
    else:
        # Default: Owner ve todo; no-Owner cae a su primer grupo (si tiene).
        if is_owner:
            scope = SCOPE_ALL
        elif groups:
            scope = str(groups[0]["id"])
            scope_team = groups[0]

    if scope == SCOPE_ALL:
        scope_label = _("Todos los grupos")
    else:
        scope_label = scope_team["name"] if scope_team else _("Grupo")

    # --- Rol efectivo en el ámbito --------------------------------------
    _ROLE_LABELS = {
        MembershipRole.CONTRIBUTOR: _("Colaborador"),
        MembershipRole.VIEWER: _("Visualizador"),
    }
    if is_owner:
        effective_role = _("Owner")
    elif scope_team:
        role_code = roles_by_team.get(scope_team["id"])
        effective_role = _ROLE_LABELS.get(role_code, "")
    else:
        effective_role = ""

    # --- Conteo del panel de notificaciones -----------------------------
    panel_count = _panel_count(user, is_owner, scope, scope_team, groups)

    # --- Datos de usuario -----------------------------------------------
    full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
    email = getattr(user, "email", "") or ""
    display_name = full_name or email

    # Avatar del usuario actual para el chrome (topbar/menú): avatar SVG elegido
    # (avatar_choice). No hay fotos subidas; degrada a iniciales si es 0.
    avatar_choice = 0
    user_prefs = getattr(user, "preferences", None)
    if user_prefs is not None:
        avatar_choice = getattr(user_prefs, "avatar_choice", 0) or 0

    return {
        "forge_groups": groups,
        "forge_scope": scope,
        "forge_scope_label": scope_label,
        "forge_is_owner": is_owner,
        "forge_user_name": display_name,
        "forge_user_initials": _initials(full_name, email),
        "forge_user_email": email,
        "forge_user_role": effective_role,
        "forge_user_avatar_choice": avatar_choice,
        "forge_panel_count": panel_count,
        "forge_check_interval_hours": check_interval_hours,
        "sidebar_collapsed": sidebar_collapsed,
    }


def _panel_count(user, is_owner, scope, scope_team, groups) -> int:
    """Conteo de alertas nuevas/no leídas en el panel.

    Mismo conjunto que la campana lista: ``Alert.status == OPEN`` dentro del
    ámbito activo, excluyendo las que ya tienen ``read_at`` para este usuario.
    (Ya NO se aplica el sello ``panel_cleared_at``: limpiar = resolver, work-stream B.)
    """
    from apps.alerts.models import Alert, AlertStatus, AlertUserState
    from apps.certificates.models import Certificate

    # Certificados del ámbito.
    certs = Certificate.objects.for_user(user)
    if scope != SCOPE_ALL and scope_team is not None:
        # Dueño (FK) o compartido al grupo (M2M groups); espejo de for_team().
        certs = certs.filter(Q(team_id=scope_team["id"]) | Q(groups=scope_team["id"])).distinct()
    elif not is_owner and not groups:
        return 0

    qs = Alert.objects.filter(certificate__in=certs, status=AlertStatus.OPEN).distinct()
    states = {
        s.alert_id: s
        for s in AlertUserState.objects.filter(user=user, alert__in=qs)
    }
    return sum(1 for alert in qs if not (states.get(alert.id) and states[alert.id].read_at))
