# CertManager

Plataforma de monitoreo de certificados **SSL/TLS** multi-grupo: chequea hosts,
avisa antes de que venzan (**plataforma / correo / webhook / SMS**), genera
reportes programados y expone una **API REST**. UI server-rendered (design system
**Forge UI** + HTMX), roles por grupo, plantillas de correo, 2FA, auditoría y
planificador en-proceso.

> El paquete interno conserva el nombre `certforge` por compatibilidad; el
> producto es **CertManager**.

---

## Stack

- **Django 5** · **DRF** (API con API keys) · server-rendered (**Forge UI** + Tailwind + **HTMX**)
- **MySQL 8** (producción, vars `DB_*` por separado) · **SQLite** (local / pruebas)
- Monitoreo, reportes y backups por **APScheduler** en-proceso (o `cron`)
- `cryptography` (parseo de certs) · `ldap3` (LDAP) · `pyotp` (2FA TOTP) · `reportlab`/`openpyxl` (PDF/Excel)
- **WhiteNoise** (estáticos, sin CDN) · **django-csp** · logging JSON (opcionalmente vía obsforge → Loki)

## Estructura del repo

```
config/        settings (base/local/prod/standalone), urls, wsgi/asgi
apps/
  core/        OrganizationSettings, ApiKey, AuditLog, middlewares (admin gate,
               2FA, expiración de contraseña, request log), backup_db
  accounts/    User (login por email) + Owner global, 2FA TOTP, lockout
  teams/       Team ("Grupo") + Membership (VIEWER/CONTRIBUTOR/ADMIN)
  certificates/Certificate (location, grupos M2M), recipients, checks
  monitoring/  SSLChecker + scheduler + commands (check_certificates,
               data_update_certs_app)
  alerts/      Alert, AlertDelivery, WebhookIntegration + notificadores
  mailtemplates/ reports/ web/   plantillas, reportes y vistas Forge UI
api/           router DRF (/api/certificates, /teams, /alerts)
CLARO_NECESIDAD/  documentación + .env de despliegue (ver §"Producción")
```

---

## Instalación

Hay un script por escenario en la **raíz** del repo. La base de datos de
producción es **externa** (MySQL); los scripts solo levantan el aplicativo.

| Escenario | Script | BD | TLS |
|-----------|--------|----|-----|
| Pruebas / migración en **Windows** | `install_windows.bat` | SQLite (auto) | no (dev) |
| **Docker** (app + NGINX TLS) | `install_docker.sh` | MySQL externa | NGINX 443 (incluido) |
| **Kubernetes** | `k8s/` + [manual](CLARO_NECESIDAD/04_aprovisionamiento_y_certificados.md) | MySQL externa | Ingress 443 |
| **Servidor Linux** (servicio) | `install_server.sh` | MySQL externa | NGINX (lo instala) |
| Desarrollo local | manual (abajo) | SQLite | no |

### 1) Pruebas en Windows (SQLite)

```bat
install_windows.bat       :: setup (venv + SQLite + Owner + migración) y arranca
run_windows.bat           :: re-arranca el server (sin reinstalar)
```
Perfil `standalone` (SQLite). Sirve en **`0.0.0.0:8000`** → accesible desde la red
por la **IP del equipo** (`http://<IP>:8000/`); Windows puede pedir permitir Python
en el **Firewall** (Permitir). Solo para pruebas internas (server de desarrollo de
Django); para producción, Linux/Docker/K8s.

> **Primera visibilidad en VDI/escritorio corporativo SIN admin:**
> [`PRESENTACION_VDI.md`](PRESENTACION_VDI.md) (Python per-usuario, sin servicios
> del sistema, demo por pantalla compartida).

### 2) Docker — solo el contenedor del app

```bash
cp CLARO_NECESIDAD/.env.example CLARO_NECESIDAD/.env   # completar (BD externa, etc.)
./install_docker.sh           # build + up (web + scheduler)
./install_docker.sh logs      # ver logs   ·   ./install_docker.sh down
```
Usa `docker-compose.app.yml`: levanta **web + scheduler + NGINX con TLS** y sirve
en **443** (redirige 80→443) con el wildcard `*.claro.com.do` (colocar en `./tls/`).
**No** levanta BD; la toma de las vars `DB_*` del `.env`. Dónde poner el
certificado y los 3 modos (Linux/Docker/K8s):
[`CLARO_NECESIDAD/04`](CLARO_NECESIDAD/04_aprovisionamiento_y_certificados.md).

### 3) Servidor Linux como servicio

```bash
cp CLARO_NECESIDAD/.env.example CLARO_NECESIDAD/.env   # completar
sudo ./install_server.sh
```
Instala paquetes de sistema, venv, compila el CSS, migra, e instala **systemd**
(`certmanager` = gunicorn, `certmanager-scheduler` = tareas) + **NGINX** con TLS y
redirección 80→443. Ajustá `TLS_CERT`/`TLS_KEY` (o pásalos por entorno).

### 4) Desarrollo local (manual)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/local.txt
cp .env.example .env                 # ajusta DJANGO_SECRET_KEY
npm ci && npm run build:css          # compila static/css/forge.css
python manage.py migrate
python manage.py createsuperuser     # superusuario Django (solo /admin)
python manage.py runserver
```
El **Owner** de la app (gestiona grupos/usuarios/config) es un usuario con
`is_owner=True`; el superusuario de Django es solo para `/admin`.

---

## Bootstrap de datos (Owner + configuración)

Una vez instalado, carga de forma **idempotente** el Owner, la configuración por
defecto y **migra el monitoreo** desde `./cert.txt`. Coloca el `cert.txt` en la
raíz y corre el bootstrap (es **la migración de la data**, no un paso opcional;
solo está pendiente del `cert.txt` actualizado):

```bash
# con cert.txt en la raíz -> Owner + configuración + migración del monitoreo
./data_update_certs_app.sh
# Docker:  docker compose -f docker-compose.app.yml exec web ./data_update_certs_app.sh

# Aún sin el cert.txt actualizado -> deja Owner + configuración listos:
./data_update_certs_app.sh --skip-certs
```
Reglas aplicadas: monitoreo por **plataforma + correo**; **ubicación** según el
dominio (`ntp`/`ntt` → *Servidor*, `claro.com.do` → *netscaler*); **grupos** desde
los correos de soporte `sp*` (el Owner es ADMIN solo de `sp_canales_electronicos`);
todos los correos quedan como destinatarios. Detalle en
[`CLARO_NECESIDAD/03_cambios_para_produccion.md` §7](CLARO_NECESIDAD/03_cambios_para_produccion.md).

---

## Producción (despliegue en Claro)

La carpeta **[`CLARO_NECESIDAD/`](CLARO_NECESIDAD/)** tiene todo lo que pide
infraestructura:

- **`01_diagrama_flujo_datos.md`** — diagrama de alto nivel del flujo de datos.
- **`02_necesidades_instalacion.md`** — requisitos del servidor, paquetes,
  **egress/ingress (firewall)**, BD MySQL externa, conectividad de build.
- **`03_cambios_para_produccion.md`** — checklist + carga del `cert.txt`.
- **`.env.example`** — plantilla; el `.env` real va gitignored (secretos).

`config.settings.prod` exige `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS` y los datos de
BD (`DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`), y fuerza HTTPS (HSTS, cookies
`Secure`) tras un proxy con `X-Forwarded-Proto`.
Healthcheck sin auth en `GET /health/` (200 si la BD responde, 503 si no).

---

## Monitoreo, reportes y backups (scheduler)

El planificador es **en-proceso** (APScheduler): chequeo de certificados, reportes
programados y backup de la BD. En los despliegues corre como proceso aparte
(`manage.py run_scheduler`).

Los parámetros de **Configuración → Monitoreo** controlan el comportamiento real:
**Timeout** y **Reintentos** los usa cada chequeo (`run_check`); **Frecuencia** y
**Ventana horaria** los usa el daemon. Cambiar frecuencia/ventana requiere
reiniciar `run_scheduler` (se leen al arrancar).

**Ventana horaria de chequeo** (Configuración → Monitoreo): el chequeo masivo
abre una conexión TLS a **cada** host monitoreado, así que conviene correrlo en
**horario valle** para no competir con el tráfico productivo ni generar ruido en
los sistemas vigilados. Si hay una ventana definida (por defecto **02:00–05:00**),
el scheduler agenda el chequeo **diario a la hora de inicio** (cron). Si se deja
vacía, corre por **intervalo** (`SCHEDULER.CERT_CHECK_HOURS`, 24h). Cambiar la
ventana requiere reiniciar el `run_scheduler`.

Alternativa por `cron` del sistema (en vez del scheduler en-proceso):

```cron
0 6 * * *    cd /ruta && /ruta/.venv/bin/python manage.py check_certificates
*/30 * * * * cd /ruta && /ruta/.venv/bin/python manage.py send_scheduled_reports
0 3 * * *    cd /ruta && /ruta/.venv/bin/python manage.py backup_db
```

---

## Seguridad (OWASP)

Ver `docs/security/owasp-top10-2025.md`. Resumen:

- **Acceso (A01):** RBAC por grupo (`for_user` recorta querysets); admin Django solo superusuario.
- **Auth (A07):** bloqueo por fuerza bruta, **2FA TOTP** (opcional/exigible), **expiración** y **longitud mínima** de contraseñas, **timeout de sesión** por inactividad — todo configurable en **Configuración → Seguridad** y aplicado de verdad. Mensajes genéricos.
- **CSP (A02):** cabeceras Content-Security-Policy. **Secretos** fuera del código (entorno) y write-only en la UI.
- **Auditoría (A09):** `AuditLog` append-only de acciones humanas + eventos de login.
- **SSRF:** validación de host en el chequeo SSL y en la entrega de webhooks.

---

## Logs y observabilidad

Todos los logs salen en **JSON** (una línea por evento) a **stdout** y a fichero
rotado (`${LOG_DIR}/app.log` y `audit.log`; `LOG_DIR` por defecto
`/var/log/certmanager`, degrada a `<repo>/logs` si no es escribible).

- **Auditoría** (`certmanager.audit`) — cada acción humana, por triplicado: tabla
  `AuditLog`, `audit.log` y stream.
- **Requests** (`certmanager.request`) — un evento por request (web y `/api/`) con
  `status`, `duration_ms`, `actor_email`, `ip`, `reference_id` (= `X-Request-ID`).
- **API** (`certmanager.api`) — cada llamada autenticada (key, scope, usuario).
- **Funcionamiento** — `certmanager.monitoring` (chequeos; WARNING si fallan) y
  `certmanager.alerts` (entregas; **ERROR** si fallan). Los 500 los registra
  `django.request` en ERROR con el traceback en `exc`.

Con **obsforge** (índice privado, `OBSFORGE_ENABLED=1`) esas mismas líneas se
sintetizan por el bridge del root y se enriquecen con tracing; obsforge pasa a ser
el único dueño de stdout (el preset `prod` redacta PII). Sin obsforge, el
`JsonFormatter` propio emite JSON plano que **Promtail** parsea hacia **Loki**.

---

## API

- `GET/POST /api/certificates/` · `POST /api/certificates/{id}/test/` · `GET …/checks/`
- `GET/POST /api/teams/` · `GET /api/alerts/` · docs OpenAPI en `/api/docs/`

Autenticación por **API key** (`Authorization: Api-Key cf_live_…` o `X-Api-Key`):
`cf_live_…` total · `cf_ro_…` solo lectura. Se aprovisiona en `/settings/api/`
(solo Owner; el secreto se muestra una vez; solo se guarda el hash).

---

## Tests

```bash
OBSFORGE_ENABLED=0 python manage.py test     # NO usar --parallel
```
**519 tests** en verde (settings `config.settings.local`). Qué cubre cada uno y
cómo correr subconjuntos: **[`docs/testing.md`](docs/testing.md)**.
CI en GitHub Actions (`.github/workflows/ci.yml`).
