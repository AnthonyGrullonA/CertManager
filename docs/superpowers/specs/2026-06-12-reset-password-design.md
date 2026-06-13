# Reset de contraseña con temporal (Owner) — 2026-06-12

## Problema

El Owner administra los usuarios pero no tiene forma de restablecerle la
contraseña a alguien que la olvidó. Se necesita un botón que genere una
contraseña temporal, la muestre una sola vez y, opcionalmente, la envíe por
correo al usuario.

## Decisiones

- **Forzar cambio al siguiente login** (opción A aprobada): flag
  `User.must_change_password`; se reutiliza `PasswordExpiryMiddleware` para
  redirigir al Perfil, donde el banner existente se adapta. Al cambiar la
  contraseña desde Perfil, el flag se limpia.
- **La temporal nunca se persiste en claro**: se muestra una vez en el partial
  de éxito y, si se marcó el checkbox, se envía por correo en esa misma
  petición.
- **Sin BCC de auditoría** en ese correo: copiar el buzón de auditoría
  filtraría la contraseña.

## Cambios

1. **Modelo** (`apps/accounts/models.py`): `must_change_password`
   (BooleanField, default False) + migración.
2. **Generador** (`apps/accounts/passwords.py`, nuevo):
   `generate_temp_password()` — 14 caracteres con `secrets`, alfabeto sin
   ambiguos (`l/1/I/O/0`), garantiza pasar `validate_password`.
3. **Middleware** (`apps/core/middleware.py`): `PasswordExpiryMiddleware`
   también redirige cuando `user.must_change_password` está activo
   (independiente de si la expiración está habilitada), con
   `?password_reset=1`. Mismas exenciones (perfil/login/logout/superuser).
4. **Perfil**: `profile.html` muestra banner si `password_reset=1`
   ("contraseña temporal: debes definir la tuya"); `password_change` limpia el
   flag al guardar.
5. **Vista** `UserResetPasswordView` (`apps/web/views_usuarios.py`, solo
   Owner) + URL `users/<pk>/reset-password/` (`user-reset-password`):
   - GET: modal de confirmación (`usuarios/_reset_modal.html`) con checkbox
     "Enviar por correo al usuario".
   - POST: genera temporal, `set_password`, `must_change_password=True`,
     guarda; si `send_email`, envía con `smtp_connection()` +
     `default_from_email()`, sin BCC; si el envío falla, el partial lo avisa
     pero igual muestra la contraseña. Éxito: `usuarios/_reset_success.html`
     con la temporal copiable (elemento `#temp-password`).
   - Guardas: a sí mismo -> 400 ("usa tu Perfil"); usuario sin contraseña
     local usable (LDAP) -> 400 ("credencial gestionada en el directorio");
     no-Owner -> 403 (mixin existente).
6. **UI** (`usuarios/detail.html`): botón "Restablecer contraseña" junto a
   "Editar"; solo se pinta si el target no es el propio Owner y tiene
   contraseña local usable.

## Lo que NO cambia

- 2FA no se toca (restablecer contraseña no desactiva TOTP).
- El flujo LDAP sigue igual: esas credenciales no se gestionan aquí.
- El cambio de contraseña vía Perfil y la política de expiración existentes.

## Tests

- Generador: largo, alfabeto, pasa validadores, no repite.
- POST resetea: la temporal mostrada autentica, flag activo, partial la
  muestra una sola vez.
- Checkbox: correo a `outbox` con la temporal, sin BCC; sin checkbox no envía.
- Guardas: self/LDAP -> 400; no-Owner -> 403.
- Middleware: con flag activo cualquier página redirige a Perfil; el cambio de
  contraseña en Perfil limpia el flag y deja navegar.
