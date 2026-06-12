# Seguridad y cumplimiento — CertManager

Detalle técnico ampliado en `docs/security/owasp-top10-2025.md`.

## 1. Controles de seguridad implementados

| Categoría | Control |
|-----------|---------|
| **Transporte** | HTTPS forzado, HSTS (1 año, includeSubDomains, preload), `SECURE_SSL_REDIRECT`, cookies `Secure` (sesión y CSRF). |
| **Cabeceras** | CSP (enforce), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, Referrer-Policy. |
| **Autenticación** | Login local + LDAP/AD; **bloqueo por fuerza bruta**; **2FA TOTP** (opcional/exigible); mensajes de credenciales genéricos. |
| **Política de contraseñas** | Longitud mínima configurable, **expiración** opcional, validadores Django (similaridad, comunes, numéricas). |
| **Sesión** | Cookies HttpOnly+Secure, **timeout por inactividad** configurable, cierre de sesión. |
| **Autorización (RBAC)** | Owner global + roles por grupo (VIEWER/CONTRIBUTOR/ADMIN); `for_user` recorta querysets; admin de Django restringido al superusuario. |
| **API** | API keys con **hash** (nunca en claro), prefijo de ámbito (`cf_live_`/`cf_ro_`), permisos por scope, throttle. |
| **Anti-SSRF** | Validación de host en chequeos SSL y entrega de webhooks (rechaza loopback/metadata/rangos internos). |
| **Secretos** | Fuera del código (variables de entorno / gestor de secretos); secretos write-only en la UI; repo sin secretos. |
| **Auditoría** | `AuditLog` append-only de acciones humanas + eventos de login (triplicado: tabla, `audit.log`, stream). |
| **CSRF** | Protección Django en todas las vistas con formularios. |
| **Inyección** | ORM de Django (consultas parametrizadas); sin SQL crudo en rutas de usuario. |

## 2. OWASP Top 10 (2025) — resumen

| # | Categoría | Estado |
|---|-----------|--------|
| A01 | Control de acceso roto | ✅ RBAC por grupo, gate de admin |
| A02 | Fallas criptográficas | ✅ TLS/HSTS, secretos por entorno; **CSP usa `unsafe-inline`** (residual, ver §4) |
| A03 | Inyección | ✅ ORM parametrizado |
| A04 | Diseño inseguro | ✅ anti-SSRF, RBAC, defaults seguros |
| A05 | Mala configuración | ✅ `check --deploy` limpio en prod |
| A06 | Componentes vulnerables | ✅ `pip-audit` en CI — **0 CVEs** |
| A07 | Fallas de autenticación | ✅ lockout, 2FA, políticas de contraseña/sesión |
| A08 | Integridad de datos/software | ✅ migraciones versionadas, repo controlado |
| A09 | Fallas de logging/monitoreo | ✅ auditoría triplicada + logs estructurados |
| A10 | SSRF | ✅ validación de host en chequeos/webhooks |

## 3. Verificaciones realizadas (evidencia)

- `python manage.py check --deploy` (perfil prod): **sin hallazgos de seguridad**.
- `pip-audit`: **0 vulnerabilidades** conocidas en dependencias.
- Barrido de secretos del repositorio: **sin secretos hardcodeados**.
- Suite de pruebas de seguridad (lockout, 2FA, expiración, timeout, RBAC, anti-SSRF): verde.

## 4. Riesgos residuales / recomendaciones

| Residual | Recomendación |
|----------|----------------|
| CSP con `unsafe-inline` (script/estilo) | Endurecer a nonces (refactor; el design usa estilos inline). |
| Pentest formal no realizado | Ejecutar pentest por el equipo de seguridad de Claro antes de prod. |
| Gestión de secretos básica (entorno) | Integrar Vault/SealedSecrets (K8s). |
| Repositorio público (temporal) | Migrar a repositorio **privado** corporativo. |

## 5. Matriz de cumplimiento (referencia ISO/IEC 27001 — Anexo A)

| Control | Cómo lo cubre el aplicativo |
|---------|------------------------------|
| A.5 Políticas / A.8 Gestión de activos | Esta documentación + ficha técnica |
| A.8.2 / A.8.3 Control de acceso | RBAC, 2FA, lockout, políticas de contraseña |
| A.8.5 Autenticación segura | LDAP/AD, 2FA TOTP |
| A.8.15 Registro (logging) | Auditoría triplicada, logs estructurados |
| A.8.16 Monitoreo | `/health`, logs a Loki, alertas |
| A.8.24 Criptografía | TLS, HSTS, hash de API keys |
| A.8.28 Codificación segura | ORM, CSP, CSRF, anti-SSRF, `pip-audit` en CI |
| A.5.30 Continuidad TIC | Doc 08 (RTO/RPO, DRP/BCP) |

> Mapeo orientativo; la certificación formal corresponde al área de cumplimiento de Claro.
