"""Permisos de plantillas de correo.

- Ver / adjuntar / crear: cualquier usuario autenticado (uso global).
- Editar / borrar: Owner global, un Admin de grupo (cualquiera) o el creador.
"""
from __future__ import annotations

from apps.teams.permissions import is_admin_anywhere


def can_create_template(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


def can_edit_template(user, tpl) -> bool:
    if getattr(user, "is_owner", False):
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if tpl.created_by_id and tpl.created_by_id == user.id:
        return True
    return is_admin_anywhere(user)
