# CertManager — Guía de tests

Qué cubre la suite, cómo correrla y qué prueba cada archivo.

**Estado:** **519 tests · verde.** Sin dependencias externas (no toca red ni BD
real: usa SQLite efímera y backends en memoria/consola).

---

## 1. Cómo correr los tests

### Entorno canónico (igual que el CI)
```bash
OBSFORGE_ENABLED=0 DJANGO_SETTINGS_MODULE=config.settings.local \
  DJANGO_SECRET_KEY=ci-test-key python manage.py test
```
- **`config.settings.local`** → SQLite + `DEBUG=True` (estáticos sin hash, para que
  las aserciones de plantillas no dependan del manifest).
- **`OBSFORGE_ENABLED=0`** → no carga la librería privada de observabilidad.
- **NO usar `--parallel`** → algunos tests comparten singletons (OrganizationSettings)
  y caché de lockout; en paralelo dan falsos negativos.

### Local (venv)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/local.txt
OBSFORGE_ENABLED=0 python manage.py test
```

### En contenedor (sin venv local)
```bash
docker run --rm -v "$PWD:/app" -w /app \
  -e DJANGO_SETTINGS_MODULE=config.settings.local \
  -e DJANGO_SECRET_KEY=ci-test-key -e OBSFORGE_ENABLED=0 -e RUN_MIGRATIONS=0 \
  certmanager:latest python manage.py test --verbosity 1
```

### Subconjuntos y un solo test
```bash
python manage.py test apps.web.tests_security            # un archivo
python manage.py test apps.web.tests_security.PasswordExpiryTests   # una clase
python manage.py test apps.web.tests_security.PasswordExpiryTests.test_redirects_when_expired  # un método
python manage.py test apps.monitoring apps.alerts        # varias apps
python manage.py test --verbosity 2                      # ver cada test
```

### CI
`.github/workflows/ci.yml` corre la suite en cada push/PR (Python 3.13,
`config.settings.local`, `OBSFORGE_ENABLED=0`) + `pip-audit`.

---

## 2. Inventario: qué prueba cada archivo

> `apps/web/test_urls_*.py` **no** son tests: son *URLconf de prueba* (fixtures que
> los tests cargan con `@override_settings(ROOT_URLCONF=...)`).

### Acceso, roles y API (RBAC / A01)
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `api/tests.py` | 18 | API REST: RBAC por grupo, **anti-SSRF** en el chequeo, autorización de alertas. |
| `apps/teams/tests_permissions.py` | 6 | Permisos por rol de grupo (VIEWER / CONTRIBUTOR / ADMIN). |
| `apps/web/tests_roles_gate.py` | 9 | Bloqueo de vistas según el rol del usuario en el grupo. |
| `apps/web/tests_apikeys.py` | 20 | Aprovisionamiento de **API keys**: hash, scope (`cf_live`/`cf_ro`), secreto visible una vez. |
| `apps/web/tests_admin_access.py` | 5 | El admin de Django queda **solo** para el superusuario; redirecciones de login. |

### Autenticación y cuentas (A07)
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `apps/web/tests_security.py` | 14 | **Lockout** por fuerza bruta, **2FA exigido** por la organización, **expiración de contraseñas**, auditoría de login. |
| `apps/web/tests_2fa.py` | 9 | Enrolar/confirmar/desactivar **2FA TOTP**. |
| `apps/web/tests_login.py` | 10 | Pantalla de login Forge UI (errores, recordarme, mensajes genéricos). |
| `apps/web/tests_perfil.py` | 21 | Perfil: datos personales, preferencias, avatar, **cambio de contraseña**. |

### Certificados y monitoreo (núcleo)
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `apps/web/tests_certificados.py` | 29 | Pantalla **Certificados**: listado, filtros, crear/editar, monitoreo on/off, bulk. |
| `apps/web/tests_detalle.py` | 33 | **Detalle** del certificado: tabs, hero, edición, refresco HTMX, navegación. |
| `apps/web/tests_cert_features.py` | 6 | Reactivar certs, manejo entre grupos. |
| `apps/certificates/tests_multigroup.py` | 9 | **Grupos M2M aditivos**: visibilidad y gestión desde cualquier grupo del cert, sin duplicar. |
| `apps/web/tests_snooze.py` | 3 | **Silenciar** alertas de un cert (snooze). |
| `apps/monitoring/tests_scheduler.py` | 3 | Scheduler en-proceso: singleton por `flock`, no duplica jobs. |
| `apps/monitoring/tests_bootstrap.py` | 10 | `data_update_certs_app`: Owner (no superusuario), config por defecto, **ubicación** (ntp/ntt→Servidor, claro→netscaler), **grupos `sp*`** + normalización, destinatarios, **idempotencia**. |

### Alertas y notificaciones
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `apps/web/tests_alerts.py` | 50 | **Centro de Alertas** + panel de notificaciones: estados por usuario, leer/descartar/resolver/snooze. |
| `apps/alerts/tests.py` | 1 | Migración de datos `read_by` → `AlertUserState`. |
| `apps/alerts/tests_renotify.py` | 6 | **Re-notificación**: por escalada de severidad y por tiempo (`ALERT_RENOTIFY_DAYS`). |
| `apps/web/tests_sms.py` | 5 | Panel de configuración **SMS** (mismas reglas que webhooks) y despacho del notificador. |

### Reportes y plantillas de correo
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `apps/web/tests_reportes.py` | 30 | Pantalla **Reportes**: crear/editar, destinatarios, export PDF/Excel. |
| `apps/web/tests_reportes_actions.py` | 4 | Acciones rápidas sobre reportes. |
| `apps/reports/tests_scheduling.py` | 10 | Lógica de **vencimiento/recurrencia** de reportes programados. |
| `apps/mailtemplates/tests_models.py` | 11 | Modelos de **plantillas de correo** (builder por bloques). |
| `apps/mailtemplates/tests_views.py` | 9 | Editor de plantillas (HTMX). |
| `apps/mailtemplates/tests_send_integration.py` | 3 | Render + envío; **fallback a texto plano** sin plantilla. |

### Configuración y núcleo
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `apps/web/tests_config.py` | 38 | **Configuración**: 5 paneles HTMX (Monitoreo/SMTP/Integraciones/Seguridad/LDAP), **solo Owner**, secretos write-only. |
| `apps/core/tests_status.py` | 11 | Catálogo de páginas de estado/error + handlers (404/500/maintenance). |
| `apps/core/tests_backup.py` | 1 | Comando `backup_db` (copia consistente + retención). |
| `apps/core/tests_plugnplay.py` | 3 | Arranque **plug-and-play** (SQLite zero-config / standalone). |

### Grupos y usuarios (UI)
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `apps/web/tests_grupos.py` | 16 | Pantalla **Grupos**: listar/crear, owner + miembros. |
| `apps/web/tests_grupos_usuarios_detail.py` | 10 | **Detalle** de grupo y de usuario (overview + gestión inline). |
| `apps/web/tests_usuarios.py` | 27 | Pantalla **Usuarios** (solo Owner): crear, roles, activar/desactivar. |
| `apps/web/tests_usuarios_ui.py` | 16 | Fidelidad de UI de Usuarios (layout espejo del kit). |

### Dashboard y varios
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `apps/web/tests.py` | 18 | Suite de **caracterización** base (smoke de vistas principales). |
| `apps/web/tests_dashboard.py` | 23 | **Dashboard**: KPIs, listas, estados. |
| `apps/web/tests_avatars.py` | 12 | Avatares **SVG generativos** (templatetag + componente). |
| `apps/web/tests_faq.py` | 2 | Página de FAQ. |

### Sondas de regresión (consolidation probes)
| Archivo | Tests | Cubre |
|---------|-------|-------|
| `api/tests_consolidation_probe.py` | 3 | Fija el comportamiento consolidado de la API (anti-regresión). |
| `apps/certificates/tests_consolidation_probe.py` | 2 | Idem, modelo de certificados. |
| `apps/web/tests_consolidation_probe.py` | 3 | Idem, capa web. |

---

## 3. Convenciones

- **Aislamiento:** cada test corre en su transacción; la BD de test es efímera
  (SQLite, se crea y destruye). No se tocan servicios externos.
- **Sin red:** el chequeo SSL, SMTP, webhooks y SMS se prueban con dobles/mocks o
  verificando el registro en BD, no haciendo llamadas reales.
- **Singletons:** varios tests usan `OrganizationSettings` (pk=1) y la caché de
  lockout → por eso **no** se corre en paralelo.
- **Auditoría/logging:** durante los tests el `JsonFormatter` emite a stdout
  (ruido informativo esperado); no afecta el resultado.
- **Caracterización y probes:** `tests.py` y `*_consolidation_probe.py` fijan
  comportamiento existente para detectar regresiones, más que una sola unidad.

---

## 4. Solución de problemas

| Síntoma | Causa / arreglo |
|---------|------------------|
| Falla `forge.css` / `forge-table.js` no encontrado | Estás corriendo con un settings que usa **ManifestStaticFilesStorage** (prod/standalone). Usa `config.settings.local`. |
| `ModuleNotFoundError: obsforge` | Falta `OBSFORGE_ENABLED=0` (o el índice privado). Exporta la variable. |
| Falsos fallos intermitentes | Quitaste `--parallel`? No debe usarse (singletons compartidos). |
| `SECRET_KEY` no definido | Exporta `DJANGO_SECRET_KEY` (cualquier valor para test). |
