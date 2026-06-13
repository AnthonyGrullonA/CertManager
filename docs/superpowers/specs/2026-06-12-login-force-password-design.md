# Cambio de contraseña forzado en el flujo del login — 2026-06-12

## Problema

Tras entrar con la contraseña temporal (reset del Owner), el usuario era
redirigido al Perfil. Se quiere una pantalla del propio flujo de login —
"Contraseña nueva" / "Repite la contraseña" — con validadores visuales en vivo
que avisen en la misma pantalla si la contraseña no cumple.

## Decisiones (opción A aprobada)

- **Pantalla nueva** `accounts/cambiar-contrasena/` (name
  `password-force-change`), mismo chrome del login (espejo de la pantalla 2FA
  `two_factor_verify.html`).
- **Checklist JS en vivo** (sin tocar el servidor): mínimo N caracteres (N
  real de `OrganizationSettings.password_min_length`, vía `data-min-length`),
  "no solo números" y "las contraseñas coinciden"; cada regla pasa de ✗ a ✓
  por tecla y el botón se habilita cuando todo está verde. Las reglas que solo
  el servidor evalúa (contraseña común, similar al correo) se validan al
  enviar y el error aparece en la misma pantalla.
- **Servidor autoritativo**: `SetPasswordForm` de Django (sin re-pedir la
  temporal: la acaba de teclear en el login).

## Cambios

1. **Vista** `ForcePasswordChangeView` (`apps/accounts/views.py`):
   - GET: requiere usuario autenticado con `must_change_password`; si no lo
     tiene -> redirect al dashboard; anónimo -> login.
   - POST válido: guarda, limpia `must_change_password`, mantiene la sesión
     (`update_session_auth_hash`) y redirige al dashboard.
   - POST inválido: re-renderiza con errores del servidor en pantalla.
2. **URL** en `urls_login.py`: `accounts/cambiar-contrasena/`.
3. **Middleware** (`PasswordExpiryMiddleware`): el caso `must_change_password`
   redirige a esta pantalla (antes: Perfil). La ruta nueva entra en las
   exenciones para no crear bucle. El caso de contraseña expirada NO cambia.
4. **Template** `registration/password_force_change.html`: layout del login,
   campos "Contraseña nueva" y "Repite la contraseña", checklist en vivo (JS
   vanilla inline), errores de servidor sobre el campo.
5. El banner "contraseña temporal" del Perfil se conserva (la ruta /perfil/
   sigue exenta), pero deja de ser el destino del redirect.

## Tests

- Con flag: cualquier página redirige a la pantalla nueva; la pantalla carga
  con `data-min-length` de la organización y ambos campos.
- Sin flag: la pantalla redirige al dashboard; anónimo va al login.
- POST válido: contraseña cambia, flag se limpia, navega normal.
- POST inválido (corta / no coincide / común): 200 con error visible y flag
  intacto.
- El cambio desde Perfil sigue limpiando el flag (regresión).
