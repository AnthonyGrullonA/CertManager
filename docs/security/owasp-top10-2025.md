# Auditoría OWASP Top 10:2025 — CertManager

Mapeo de la aplicación contra las diez categorías del [OWASP Top 10:2025](https://owasp.org/Top10/2025/),
con la evidencia en el código y el estado de cada control. Leyenda: ✅ cubierto ·
🟡 cubierto con notas/residual · ⛔ pendiente.

Última revisión tras el endurecimiento (lockout de login, exigencia de 2FA, CSP
enforce, auditoría, secretos fuera del código). Suite: 495 tests.

---

## A01:2025 — Broken Access Control ✅

- **RBAC por grupo:** `apps/teams/permissions.py` (`can_view`, `can_edit_certs`,
  `is_team_admin`, `can_edit_certificate`). Roles VIEWER/CONTRIBUTOR/ADMIN.
- **Recorte de querysets:** `Certificate.objects.for_user` / `Team.objects.for_user`
  limitan cada listado/detalle a lo que el usuario puede ver (no hay IDOR: un
  no-miembro recibe 404, no 403, en el detalle de grupo).
- **Owner global** vs **superusuario Django:** el admin de Django está restringido
  al superusuario por `AdminAccessMiddleware`; los Owner/Admin de la app no acceden
  a `/admin`.
- **Secciones solo-Owner:** Usuarios y Configuración (`OwnerRequiredMixin` →
  403 a autenticados sin permiso, sin filtrar existencia).
- **Anti-escalada:** el formulario de edición de usuario NO expone `is_owner`/
  `is_staff`; no es posible auto-promoverse.
- **SSRF** (incluido en esta categoría en 2025): `validate_public_host` bloquea
  rangos internos/metadata en el chequeo SSL (`apps/monitoring/services.py`) y en la
  entrega de webhooks (`apps/alerts/services.py`, `apps/web/views_config.py`).
- Tests: `tests_roles_gate`, `tests_grupos_usuarios_detail`, `tests_usuarios`.

## A02:2025 — Security Misconfiguration ✅

- **CSP en modo enforce** por defecto (`config/settings/base.py`), `default-src 'self'`,
  `object-src 'none'`, `frame-ancestors 'none'`; `CSP_REPORT_ONLY=1` solo para
  diagnóstico.
- **Cabeceras seguras en prod** (`config/settings/prod.py`): HSTS (1 año, subdominios,
  preload), `SECURE_SSL_REDIRECT`, cookies `Secure`, `SECURE_PROXY_SSL_HEADER`.
- **Cookies:** `SESSION_COOKIE_HTTPONLY`, `CSRF_COOKIE_HTTPONLY`, `X-Frame-Options`.
- **DEBUG=False** y `ALLOWED_HOSTS`/`SECRET_KEY` obligatorios en prod (el arranque
  falla si faltan).
- **Secretos fuera del código:** credenciales de integración vía entorno
  (`CF_SEED_*`); ningún secreto en el repo (ver A04). Admin Django desbrandeado.

## A03:2025 — Software Supply Chain Failures 🟡

- Dependencias declaradas en `requirements/{base,local,prod}.txt`; `obsforge`
  (índice privado) es **opcional** y solo se carga si está presente.
- HTMX y otros JS están **vendorizados** en `static/js/` (no se cargan desde CDN
  en runtime → sin dependencia de terceros en la entrega).
- CI en GitHub Actions corre la suite y `makemigrations --check` en cada cambio.
- **Residual:** los pines son por rango (`>=`), no exactos; no hay lockfile de pip
  ni escaneo de vulnerabilidades automatizado. **Recomendado:** fijar versiones
  (`pip-compile`/`requirements.lock`) y añadir `pip-audit`/Dependabot al CI.

## A04:2025 — Cryptographic Failures ✅

- **Contraseñas** con el hasher por defecto de Django (PBKDF2) y validadores
  (`AUTH_PASSWORD_VALIDATORS`).
- **Secretos en BD** (SMTP/FTP/LDAP/webhook) son **write-only**: la UI nunca los
  muestra en claro (placeholder `●●● configurado`); un POST vacío los conserva.
- **API keys:** solo se almacena el **hash**; el secreto se muestra una sola vez.
- **2FA TOTP** (RFC 6238) por `pyotp`.
- **TLS forzado** en prod (HSTS + redirect). El chequeo de certificados parsea con
  `cryptography` (no openssl shell).
- **Limpieza histórica:** credenciales y correos internos del legacy removidos del
  código y de las migraciones (genericizados).

## A05:2025 — Injection ✅

- **SQL:** acceso exclusivamente por el ORM de Django (consultas parametrizadas);
  no hay SQL crudo con interpolación.
- **XSS:** plantillas Django con auto-escape; no se usa `|safe` sobre entrada de
  usuario. El builder de plantillas de correo renderiza por bloques controlados.
- **Command/LDAP injection:** sin `os.system`/`shell=True`; el bind LDAP usa
  `ldap3` con parámetros, no concatenación de filtros con entrada cruda.
- **Cabeceras/headers:** el envío de SMS por FTP escribe `numero|texto` codificado;
  el webhook hace `requests.post(json=...)` (sin construir cuerpos a mano).

## A06:2025 — Insecure Design ✅

- **Defensa en profundidad por diseño:** RBAC + recorte de queryset + 404 en vez de
  403 para no filtrar existencia.
- **Throttle** en "Probar ahora" (anti-DoS/SSRF) y **lockout** de login.
- **Acciones no destructivas:** "Limpiar" alertas no borra histórico; `Alert`/
  `AlertDelivery` nunca se eliminan. Pausar monitoreo es reversible.
- **Multi-tenant lógico:** ámbito por grupo con precedencia de scope congelada en
  el context processor.
- **Errores explícitos** con `X-Request-ID` para trazabilidad (sin filtrar stack).

## A07:2025 — Authentication Failures ✅

- **Bloqueo por fuerza bruta:** `CustomLoginView` cuenta fallos por (IP, correo) en
  caché y bloquea N intentos durante un periodo (`LOGIN_LOCKOUT_*`).
- **2FA TOTP** opcional, y **exigible por organización** (`require_2fa` +
  `Require2FAMiddleware` redirige a enrolar).
- **Mensajes genéricos:** "Credenciales inválidas" no revela si el correo existe
  (anti enumeración).
- **Sesiones:** cookies `HttpOnly`/`Secure`, expiración configurable; LDAP corporativo
  soportado.
- Tests: `tests_security` (lockout, require_2fa), `tests_2fa`.

## A08:2025 — Software or Data Integrity Failures ✅

- **CSRF** activado globalmente (`CsrfViewMiddleware`) + `CSRF_TRUSTED_ORIGINS`
  configurable; HTMX envía el token por `hx-headers`.
- **Integridad de estáticos:** `ManifestStaticFilesStorage` (hash de contenido) en
  prod → un asset alterado cambia de URL; cache-busting por mtime en dev.
- **Sin deserialización insegura:** no se usa `pickle`/`yaml.load` sobre entrada;
  los datos vienen por formularios/JSON validados (DRF serializers, Django forms).
- **CI** verifica que no falten migraciones (estado del esquema consistente con los
  modelos).

## A09:2025 — Security Logging and Alerting Failures ✅

- **AuditLog append-only** (`apps/core/models.py`): registra quién creó/editó/borró
  certificados, grupos, membresías, plantillas, reportes e integraciones, vía señales
  que solo capturan **acciones humanas** (el scheduler no genera ruido).
- **Eventos de autenticación:** login OK / fallido / bloqueado se auditan con IP.
- **Visible** en `/admin` (solo lectura, solo superusuario).
- **Trazabilidad de errores:** `RequestIDMiddleware` propaga `X-Request-ID`.
- Tests: `tests_security` (auditoría de acción humana vs sistema).
- **Residual recomendado:** exportar el AuditLog a un SIEM/centralización externa y
  alertar sobre patrones (p. ej. ráfaga de `login_failed`).

## A10:2025 — Mishandling of Exceptional Conditions ✅

- **Errores explícitos y seguros:** páginas de estado centralizadas; el frontend
  muestra el motivo (código + detalle del servidor + `Ref: X-Request-ID`) sin
  exponer trazas (DEBUG=False en prod).
- **Fail-safe:** la auditoría, el envío de SMS y de webhooks capturan excepciones y
  **no tumban** el flujo del usuario (best-effort con registro del fallo).
- **Healthcheck** `GET /health/` devuelve 503 si la BD no responde (degradación
  observable).
- **Aislamiento del scheduler:** cada job corre en `try/except` y cierra conexiones
  viejas; un fallo no detiene el planificador.
- **Validación de entrada:** formularios y serializers devuelven 422/400 con el
  mensaje específico en vez de fallar de forma genérica.

---

## Residuales / mejoras recomendadas (no bloqueantes)

1. **A03 — Fijar dependencias** (lockfile) y añadir `pip-audit`/Dependabot al CI.
2. **A09 — Centralizar el AuditLog** en un SIEM y alertar sobre anomalías.
3. **A02 — CSP sin `unsafe-inline`:** migrar handlers/estilos inline a nonces para
   eliminar `unsafe-inline` (refactor del chrome; hoy se mantiene por compatibilidad
   con HTMX y los handlers del layout).
