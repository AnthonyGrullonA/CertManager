# Avatar por defecto: eliminar el estado "sin avatar" (2026-06-12)

## Problema

Cuando un usuario no ha elegido avatar (`UserPreferences.avatar_choice = 0`),
la UI cae a las iniciales y se ve distorsionada. En vez de arreglar el
renderizado de iniciales, se elimina el estado: todo usuario tiene siempre un
avatar SVG asignado.

## Decisión

Avatar **pseudo-aleatorio determinista por email**: el índice se deriva de un
hash del email (`1..AVATAR_COUNT`). A la vista es aleatorio (usuarios distintos
reciben avatares distintos), pero es estable y reproducible: la migración da el
mismo resultado en cualquier ambiente y no requiere mocks en tests.

## Cambios

1. **Helper** `default_avatar_choice(email)` en `apps/accounts/models.py`:
   hash estable del email → índice `1..AVATAR_COUNT` (import perezoso de
   `AVATAR_COUNT` desde `apps.web.templatetags.forge_avatars` para evitar
   ciclos). Debe usar un hash estable entre procesos (no `hash()` nativo, que
   está salteado por `PYTHONHASHSEED`).
2. **Señal** `create_user_preferences`: crea las preferencias con
   `avatar_choice=default_avatar_choice(instance.email)` en vez de 0.
3. **Migración de datos** en `accounts`: backfill de todo `UserPreferences`
   con `avatar_choice=0` usando el mismo criterio. Reversible como no-op.
4. **Formulario** (`AvatarChoiceForm.clean_avatar_choice`): rechaza 0; solo
   acepta `1..AVATAR_COUNT`.
5. **Perfil** (`templates/perfil/_section_avatar.html`): se elimina el botón
   "quitar avatar" (posteaba `avatar_choice=0`).

## Lo que NO cambia

- `components/_avatar.html` conserva el fallback a iniciales: el componente
  también se usa para destinatarios de certificados que no son usuarios (p.ej.
  `detalle/_tab_panel.html`) y no tienen preferencias. Para usuarios reales el
  fallback ya no se activará.
- No hay subida de fotos ni storage: siguen siendo SVG generativos por índice.

## Tests

- El helper devuelve índices válidos, deterministas y distribuidos.
- La señal asigna el avatar derivado del email al crear el usuario.
- El form rechaza `0` y fuera de rango.
- La migración puebla los registros existentes en 0.
