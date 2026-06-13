# Eliminar el rol "Admin de grupo" + campos de identidad duplicados — 2026-06-12

## Decisión del Owner

El rol Admin de grupo no debe existir: el Owner es quien maneja la plataforma.
En la práctica el rol confundía (su única diferencia real — gestionar miembros,
editar el grupo y resolver alertas compartidas — no resultaba usable) y para
certificados ya se comportaba idéntico a Colaborador.

## Parte 1 — Campos de identidad duplicados en las cards

Cuando el usuario no tiene nombre cargado, `get_full_name|default:email`
duplica el correo ("correo · correo" en selects; línea-nombre + línea-correo
idénticas en filas). Regla única: **si no hay nombre, el correo se muestra UNA
sola vez**. Se corrige en:

- `grupos/_members.html`: opción del select de agregar ("Nombre · correo" solo
  si hay nombre) y línea de correo de cada fila (solo si hay nombre).
- `usuarios/_row.html`: línea de correo solo si hay nombre.
- `usuarios/detail.html`: correo bajo el H1 solo si hay nombre.
- `perfil/_section_avatar.html`: correo bajo display_name solo si hay nombre.

## Parte 2 — Eliminación del rol

1. **Enum** (`apps/core/enums.py`): `MembershipRole` queda VIEWER y
   CONTRIBUTOR. **Migración** en `teams`: `UPDATE role ADMIN -> CONTRIBUTOR`.
2. **Permisos** (`apps/teams/permissions.py`): `EDIT_CERT_ROLES = (CONTRIBUTOR,)`;
   se eliminan `is_team_admin` / `is_admin_anywhere`.
3. **Solo Owner** a partir de ahora: gestionar miembros y editar/crear grupos
   (`views_grupos`), resolver alertas compartidas (`views_alerts`), permisos
   admin de plantillas (`mailtemplates/permissions.py`) y de la API
   (`api/permissions.py`).
4. **Responsables de un cert sin destinatarios**: el fallback pasa de "Admins
   del grupo" a "Colaboradores del grupo" (tag "grupo" en vez de "admin") en
   `views_detalle._responsables` y `views_certificates._decorate_responsables`.
5. **UI**: columna "Admin(s)" del overview de Grupos se elimina; el chip de rol
   de Usuarios queda Owner > Colaborador > Visualizador > Miembro
   (`accounts.User.group_role` y `usuarios/_role_chip.html`); el selector de
   rol (invitar/editar/miembros) pierde la opción automáticamente (usa
   `MembershipRole.choices`).
6. **Bootstrap** (`data_update_certs_app`): la membresía del Owner en su grupo
   pasa a CONTRIBUTOR (su poder ya es global).
7. **Tests**: los que codificaban capacidades del Admin de grupo se reescriben
   al nuevo contrato (gestión solo-Owner); se actualizan fixtures que usaban
   ADMIN.

## Lo que NO cambia

- Owner global y Colaborador/Visualizador conservan sus capacidades actuales.
- `is_staff` sigue siendo solo el superusuario del admin de Django.
