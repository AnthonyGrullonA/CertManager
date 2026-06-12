"""Capacidades por rol de grupo — fuente única de verdad.

Roles (apps.core.enums.MembershipRole):
- VIEWER: ve certs/alertas/dashboard y genera reportes en sus grupos.
- CONTRIBUTOR: + crea/edita/borra certificados en sus grupos.
- ADMIN: + gestiona plantillas, miembros y alertas compartidas del grupo.
- Owner global (``user.is_owner``): todo, en todos los grupos.

Todos los helpers devuelven True para el Owner global y son tolerantes a
usuarios anónimos (devuelven None/False sin lanzar).
"""
from __future__ import annotations

from apps.core.enums import MembershipRole

EDIT_CERT_ROLES = (MembershipRole.CONTRIBUTOR, MembershipRole.ADMIN)


def _team_id(team):
    return getattr(team, "id", team)


def role_in(user, team):
    """Rol del usuario en el grupo, o None si no es miembro / anónimo."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    m = user.memberships.filter(team_id=_team_id(team)).first()
    return m.role if m else None


def can_view(user, team) -> bool:
    if getattr(user, "is_owner", False):
        return True
    return role_in(user, team) is not None


def can_edit_certs(user, team) -> bool:
    if getattr(user, "is_owner", False):
        return True
    return role_in(user, team) in EDIT_CERT_ROLES


def is_team_admin(user, team) -> bool:
    if getattr(user, "is_owner", False):
        return True
    return role_in(user, team) == MembershipRole.ADMIN


def can_edit_certificate(user, cert) -> bool:
    """Puede gestionar el cert si es Owner o Contributor+ en CUALQUIERA de sus
    grupos (el dueño ``team`` o los grupos adicionales ``groups``)."""
    if getattr(user, "is_owner", False):
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    group_ids = {cert.team_id}
    if cert.pk:
        group_ids |= set(cert.groups.values_list("id", flat=True))
    roles = user.memberships.filter(team_id__in=group_ids).values_list("role", flat=True)
    return any(r in EDIT_CERT_ROLES for r in roles)


def is_admin_anywhere(user) -> bool:
    """True si es Owner o tiene rol ADMIN en algún grupo."""
    if getattr(user, "is_owner", False):
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return user.memberships.filter(role=MembershipRole.ADMIN).exists()
