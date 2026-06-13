"""Permisos DRF que aplican el modelo de roles de CertForge.

- Owner global: acceso total.
- Admin/Miembro: acotados a sus grupos (la escritura, solo Admin).

Las vistas usan `scope_queryset` para filtrar por pertenencia.
"""
from rest_framework import permissions

from apps.core.enums import MembershipRole

# La escritura de certificados la pueden hacer los Colaboradores (no Viewers).
# La gestión del grupo (alertas compartidas, miembros) es exclusiva del Owner:
# el rol Admin de grupo se eliminó por decisión del Owner.
WRITE_CERT_ROLES = [MembershipRole.CONTRIBUTOR]


class ApiKeyScopePermission(permissions.BasePermission):
    """Aplica el ámbito de la API key: las claves 'solo lectura' solo permiten
    métodos seguros (GET/HEAD/OPTIONS). El acceso por sesión no se ve afectado.
    """

    message = "Esta API key es de solo lectura; no permite operaciones de escritura."

    def has_permission(self, request, view):
        from apps.core.models import ApiKey

        api_key = getattr(request, "auth", None)
        if isinstance(api_key, ApiKey) and api_key.is_read_only:
            return request.method in permissions.SAFE_METHODS
        return True


def user_team_ids(user, roles=None):
    """IDs de grupos a los que pertenece el usuario, opcionalmente filtrando por rol."""
    qs = user.memberships.all()
    if roles:
        qs = qs.filter(role__in=roles)
    return list(qs.values_list("team_id", flat=True))


def scope_certificates(queryset, user):
    """Filtra un queryset de certificados según el usuario."""
    if user.is_owner:
        return queryset
    return queryset.filter(team_id__in=user_team_ids(user))


def user_is_team_admin(user, team_id):
    """Gestión del grupo: SOLO el Owner global (el rol Admin de grupo no existe)."""
    return bool(getattr(user, "is_owner", False))


class IsOwnerOrTeamMember(permissions.BasePermission):
    """Lectura: Owner o miembro del grupo. Escritura: Owner o Admin del grupo."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_owner:
            return True
        team_id = getattr(obj, "team_id", None) or getattr(getattr(obj, "certificate", None), "team_id", None)
        if team_id is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return team_id in user_team_ids(user)
        return team_id in user_team_ids(user, roles=WRITE_CERT_ROLES)


# Acciones sobre alertas que SON estado personal del usuario (cualquier usuario
# con visibilidad del ámbito puede ejecutarlas). El resto (resolve/snooze) son
# del recurso compartido y exigen Admin/Owner.
PERSONAL_ALERT_ACTIONS = frozenset({"read", "dismiss", "read_all", "clear_panel"})
SHARED_ALERT_ACTIONS = frozenset({"resolve", "snooze"})


class IsScopedAlertViewer(permissions.BasePermission):
    """Permiso de alertas según el diseño de notificaciones (plan, paso 2).

    - Lectura y estado personal (read/dismiss/read-all/clear-panel): cualquier
      usuario autenticado con visibilidad del ámbito de la alerta.
    - Acciones sobre el recurso compartido (resolve/snooze): solo Admin del grupo
      u Owner global.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        team_id = getattr(getattr(obj, "certificate", None), "team_id", None)
        if team_id is None:
            return False

        in_scope = user.is_owner or team_id in user_team_ids(user)
        if not in_scope:
            return False

        action = getattr(view, "action", None)
        if request.method in permissions.SAFE_METHODS or action in PERSONAL_ALERT_ACTIONS:
            return True
        if action in SHARED_ALERT_ACTIONS:
            return user_is_team_admin(user, team_id)
        # Por defecto (cualquier otra escritura sobre la alerta): Admin/Owner.
        return user_is_team_admin(user, team_id)
