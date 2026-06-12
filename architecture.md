# Arquitectura técnica — CertForge

Bases técnicas de **CertForge**, la plataforma Django que reemplaza al sistema
legacy de monitoreo de certificados (`certapp_old/`). Complementa a `ui.md`
(que cubre UI/UX con el design system **Forge UI**). Este documento cubre stack,
estructura, modelo de datos, monitoreo, API, seguridad y migración de datos.

---

## 1. Stack y decisiones

| Área | Decisión |
|------|----------|
| Framework | Django 5.x |
| Frontend | **Híbrido**: templates server-rendered (Forge UI) + **DRF** para API, exportes e interacciones dinámicas |
| Interactividad | HTMX para acciones in-page (probar ahora, filtros, alertas) sobre los templates |
| Base de datos | **SQLite** en local; **MySQL 8** en contenedor (settings por entorno) |
| Monitoreo | **Management command + cron** (`check_certificates`) |
| Tareas asíncronas | Ninguna obligatoria en fase 1 (el command corre por cron) |
| Config/secretos | `django-environ` + `.env` (sin secretos en el código) |
| Parsing de certs | `ssl` (stdlib) + `cryptography` para cadena, SAN, fingerprint, algoritmo |
| Empaquetado | Docker + docker-compose (web + MySQL 8) |

> **Por qué híbrido:** el render en servidor encaja con lo que produce Claude
> Design y mantiene un solo despliegue; la API DRF habilita exportes, integraciones
> y futuros clientes sin reescribir el frontend.

---

## 2. Estructura del proyecto

```
certforge/                      # raíz del proyecto Django
├── manage.py
├── config/
│   ├── settings/
│   │   ├── base.py             # común a todos los entornos
│   │   ├── local.py            # SQLite, DEBUG=True
│   │   └── prod.py             # MySQL, seguridad endurecida
│   ├── urls.py                 # urls raíz (web + /api + /admin)
│   ├── wsgi.py · asgi.py
├── apps/
│   ├── core/                   # base abstracta, enums de estado, settings singleton
│   ├── accounts/               # User custom (login por email) + rol global OWNER
│   ├── teams/                  # Team ("Grupo") + Membership (ADMIN/MEMBER)
│   ├── certificates/           # Certificate, CertificateRecipient, CertificateCheck
│   ├── monitoring/             # servicio SSL + commands check_certificates / import_legacy
│   ├── alerts/                 # Alert, AlertDelivery, WebhookIntegration
│   └── reports/                # ScheduledReport + exportadores
├── api/                        # router DRF que agrega los viewsets de cada app
├── templates/                  # plantillas Forge UI
├── static/                     # CSS/JS/assets
├── requirements/
│   ├── base.txt · local.txt · prod.txt
├── .env.example
├── Dockerfile · docker-compose.yml
└── README.md
```

Las apps viven bajo el paquete `apps/`; cada `AppConfig` declara
`name = "apps.<app>"` y conserva un `label` corto (`core`, `accounts`, …).

---

## 3. Modelo de datos

### 3.1 Diagrama de relaciones (resumen)

```
User ──< Membership >── Team ──< Certificate ──< CertificateRecipient
 │  (is_owner global)    │  (role)      │   │
 │                       │              │   └──< CertificateCheck (historial)
 │                       │              │
 │                       │              └──< Alert ──< AlertDelivery
 │                       │                     └─ read_by (M2M User)
 │                       └──< WebhookIntegration (o global)
 └─ created_by en Team/Certificate/Report

OrganizationSettings (singleton)      ScheduledReport ── created_by/Team
```

### 3.2 Entidades

**`accounts.User`** (extiende `AbstractUser`, login por email)
- `email` (único, USERNAME_FIELD), `first_name`, `last_name`
- `is_owner` (bool) — rol **global** Owner: ve y gestiona todo
- `is_active`, timestamps
- El rol por grupo vive en `Membership`, no aquí.

**`teams.Team`** ("Grupo")
- `name`, `slug`, `description`, `created_by` (FK User)
- Defaults heredables: `default_threshold_days` (int), `default_critical_days` (int),
  `notify_platform` / `notify_email` / `notify_webhook` (bool)
- `default_recipients` (lista de correos, JSON)

**`teams.Membership`**
- `user` (FK), `team` (FK), `role` ∈ {ADMIN, MEMBER}
- `unique_together(user, team)`

**`certificates.Certificate`**
- Identidad: `domain`, `port` (default 443), `team` (FK), `is_active`, `created_by`
- Config de alerta: `alert_threshold_days` (null → hereda del team),
  `critical_threshold_days` (null → hereda), overrides de canales
  `notify_platform/email/webhook` (Bool nullable → hereda del team)
- `tags` (JSON), `notes`
- **Denormalizado del último chequeo** (para listar sin joins):
  `status`, `days_left`, `valid_from`, `valid_to`, `issuer`, `subject`,
  `last_checked_at`, `next_check_at`, `last_error`,
  `last_check` (FK a CertificateCheck, opcional)
- Propiedades: `effective_threshold`, `effective_critical`, `effective_channels`
  (resuelven herencia team→cert)
- `unique_together(team, domain, port)`

**`certificates.CertificateRecipient`**
- `certificate` (FK), `email`, `user` (FK opcional)
- `unique_together(certificate, email)` — soporta múltiples destinatarios por dominio

**`certificates.CertificateCheck`** (historial; fuente de verdad)
- `certificate` (FK), `checked_at`, `status`, `days_left`
- `valid_from`, `valid_to`, `issuer`, `subject`
- Técnicos: `serial`, `fingerprint_sha256`, `signature_algorithm`, `key_size`
- `san` (JSON, dominios alternos), `chain` (JSON, cadena de confianza)
- `error_message`, `latency_ms`
- Índices por `(certificate, checked_at)`

**`alerts.Alert`**
- `certificate` (FK), `severity` ∈ {POR_VENCER, CRITICO, VENCIDO, ERROR},
  `status` ∈ {OPEN, RESOLVED, SNOOZED}, `message`
- `read_by` (M2M User) — estado leído/no leído en plataforma
- `resolved_at`, `snoozed_until`, timestamps

**`alerts.AlertDelivery`**
- `alert` (FK), `channel` ∈ {PLATFORM, EMAIL, WEBHOOK}, `target` (correo/url),
  `status` ∈ {PENDING, SENT, FAILED}, `sent_at`, `error`

**`alerts.WebhookIntegration`**
- `team` (FK, null = global), `webhook_type` ∈ {TEAMS, SLACK, GENERIC},
  `name`, `url`, `is_active`

**`reports.ScheduledReport`**
- `name`, `template` ∈ {INVENTORY, EXPIRING, EXPIRED, HISTORY, BY_GROUP}
- `filters` (JSON), `frequency` ∈ {DAILY, WEEKLY, MONTHLY},
  `format` ∈ {PDF, EXCEL, CSV}, `recipients` (JSON correos)
- `team` (FK, null = todos), `created_by`, `is_active`, `last_run_at`

**`core.OrganizationSettings`** (singleton)
- SMTP: `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password` (cifrado/oculto),
  `smtp_from`, `smtp_use_tls`
- Monitoreo: `check_interval_hours`, `connect_timeout`, `retries`
- `org_name`, `timezone`, `default_language`
- Acceso vía `OrganizationSettings.load()` (un solo registro)

### 3.3 Enums compartidos (`core.enums`)

`CertificateStatus`: `VIGENTE · POR_VENCER · CRITICO · VENCIDO · ERROR · SIN_CHEQUEAR`
(alineado con la paleta de estado de Forge UI).
`MembershipRole`, `AlertSeverity`, `AlertStatus`, `NotificationChannel`,
`DeliveryStatus`, `WebhookType`, `ReportTemplate`, `ReportFrequency`, `ReportFormat`.

---

## 4. Monitoreo (servicio + command)

### 4.1 Servicio de chequeo SSL (`monitoring/services.py`)

`SSLChecker.check(domain, port, timeout)` → `CheckResult`:
1. Abre conexión TLS (con `OPENSSL_CONF`/contexto que permita renegociación legacy
   donde haga falta, como el `openssl.cnf` del legacy).
2. Obtiene el cert (`getpeercert()` + `binary_form=True`).
3. Con `cryptography`: parsea validez, emisor, sujeto, SAN, serial, fingerprint
   SHA-256, algoritmo de firma, tamaño de clave, cadena.
4. Calcula `days_left` y deriva el `status` según umbral/critical.
5. Maneja errores equivalentes al legacy (`SSLCertVerificationError`,
   `CertificateError`, `gaierror`, `socket.error`) → status `ERROR` con causa.

Es **puro/aislado**: no escribe en BD ni envía correos; devuelve datos. Esto lo
hace testeable y reutilizable por el command y por "Probar ahora" (API).

### 4.2 `check_certificates` (management command)

- Recorre `Certificate.is_active=True` (filtros opcionales `--team`, `--domain`).
- Por cada uno: llama `SSLChecker`, crea un `CertificateCheck`, actualiza los
  campos denormalizados del `Certificate` y `next_check_at`.
- Evalúa transición de estado → crea/actualiza `Alert` y encola `AlertDelivery`
  (plataforma/correo/webhook) según canales efectivos y umbrales.
- Idempotente y seguro para correr por **cron** (ej. `0 6 * * *`).
- `--dry-run` para no notificar.

### 4.3 Notificadores (`alerts/services.py`)

- `EmailNotifier` (usa SMTP de `OrganizationSettings`, plantillas).
- `WebhookNotifier` (Teams/Slack/genérico).
- `PlatformNotifier` (crea/actualiza Alert in-app).
- Cada envío registra un `AlertDelivery` con su resultado.

---

## 5. API (DRF)

- App `api/` con un `DefaultRouter` que agrega viewsets de cada app.
- Endpoints núcleo (fase 1):
  - `/api/certificates/` (CRUD + filtros por estado/team/vencimiento)
  - `/api/certificates/{id}/test/` (acción "Probar ahora" → ejecuta SSLChecker)
  - `/api/certificates/{id}/checks/` (historial)
  - `/api/teams/`, `/api/memberships/`
  - `/api/alerts/` (+ marcar leída / resolver / snooze)
  - `/api/reports/` (programados) y `/api/reports/run/` (export on-demand)
- **Permisos**: clases DRF que aplican el modelo de roles (Owner global,
  Admin/Member por team) y filtran querysets por pertenencia.
- Auth de API: sesión (mismo dominio que la web) + Token para integraciones.

---

## 6. Seguridad y permisos

- **Custom User** con login por email; contraseñas con el hasher de Django.
- **Modelo de roles** centralizado:
  - `Owner` (global): acceso total.
  - `Admin` (por team): CRUD de certs y miembros de su team.
  - `Member` (por team): lectura + "Probar ahora".
- Mixins/permissions reutilizables para vistas web y DRF que filtran por team.
- **Secretos fuera del código**: SMTP/webhooks por `.env` / settings; en UI nunca
  se muestran en claro (solo "configurado"). Las credenciales del legacy
  (SocketLabs/FTP) **no se migran**; se reconfiguran y rotan.
- `prod.py`: `DEBUG=False`, `ALLOWED_HOSTS`, cookies seguras, HSTS, etc.

---

## 7. Migración de datos legacy (`import_legacy` command)

Objetivo: cargar los certificados de `certapp_old/` en el nuevo modelo.

1. **Owner + Team por defecto**: crea (si no existen) el usuario Owner y un Team
   `"General"` (owner = Owner). Todos los certs legacy quedan ahí inicialmente.
2. **Fuentes**: `certapp_old/cert.txt` (4 campos `dominio|correo|umbral|puerto`)
   y `certapp_old/DM.txt` (3 campos, puerto = 443).
3. **Limpieza**: trim de espacios; puerto inválido/no numérico → 443.
4. **Deduplicación** por `(dominio, puerto)` → ~187 certs únicos; los múltiples
   correos del mismo dominio se cargan como `CertificateRecipient`.
5. **Umbral**: del campo correspondiente; `critical` queda en default del team.
6. **Idempotente**: re-ejecutable con `get_or_create` (no duplica certs ni
   recipients). Flags: `--source`, `--team`, `--owner-email`, `--dry-run`.
7. **No migra**: SMS/FTP ni credenciales en claro.

> Tras importar, un `check_certificates` inicial poblará estado/validez reales.

---

## 8. Roadmap de implementación (post-bases)

1. **Bases (este paso):** scaffold + modelos + commands + servicio SSL.
2. Migraciones + `import_legacy` + primer `check_certificates`.
3. Auth y layout base (Forge UI) + dashboard.
4. CRUD de certificados + detalle + "Probar ahora".
5. Teams/usuarios/roles.
6. Alertas (plataforma/correo/webhook).
7. Reportes + exportes + programados.
8. API DRF completa + permisos finos.
9. Endurecimiento, tests e2e, despliegue.

---

## 9. Notas

- Fase 1 **no** incluye SMS (legacy vía FTP) ni SSO; quedan como futuro.
- El doc de UI/UX es `ui.md`; la referencia funcional legacy está en
  `certapp_old/` (ver su `README.md`).
- Python 3.14 detectado localmente: si la versión instalada no es compatible con
  Django 5.x, usar un entorno con Python 3.12/3.13 para correr el proyecto.
