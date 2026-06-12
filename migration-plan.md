# CertForge — Plan de migración a Forge UI (fuente de verdad, Etapa 2)

Plan consolidado por el equipo (workflow `certforge-discovery`: 12 mapeadores de
pantalla + backend/devops/seguridad + líder técnico + QA técnico + QA funcional).
Veredicto de QA: **aprobado con cambios** (incorporados). Este documento manda
sobre la implementación de la Etapa 2.

Referencias: `ui.md` (UX), `architecture.md` (backend), `CertForge — Forge UI
Design System/` (tokens, componentes, ui_kit), `certapp_old/` (legacy funcional).

---

## Decisiones del usuario (congeladas)

1. **Async:** MVP **síncrono + cron** (management-command). Celery/Redis diferido.
2. **Notificaciones — "Limpiar" conservando registro:** **no destructivo por
   usuario** (ver diseño abajo). El requisito estrella.
3. **"Probar ahora" / "Notificar":** un **Miembro puede** sobre certs de su grupo.
   Endurecer: **denylist anti-SSRF** (bloquea rangos internos/metadata
   169.254.169.254) + **rate-limit**, y **`ALLOW_LEGACY_RENEGOTIATION=False`** por
   defecto.
4. **Tema:** **solo modo claro** en el chrome (dark queda a nivel de tokens, sin
   toggle).
5. **Responsables/avatares:** **destinatarios (`CertificateRecipient`) con usuario
   vinculado + Admins del grupo como fallback**.
6. **Reportes:** **multi-formato simultáneo** (PDF+Excel+CSV) por reporte →
   añade **WeasyPrint** (PDF) + openpyxl (Excel). `ScheduledReport` gana `send_time`
   y lista de formatos.
7. **Dashboard:** la primera ventana **(≤7d) incluye los vencidos** (días < 0). El
   drill-down se alinea a los buckets reales (sin discrepancias barra↔listado).
8. **Configuración + Auth:** SMTP/webhooks/monitoreo/organización **reales**.
   Autenticación: **Django auth primario + LDAP configurable** (`django-auth-ldap`,
   activable por entorno) para acceso corporativo; el botón "SSO corporativo" del
   login se cablea al flujo LDAP. **2FA / API keys**: placeholder/diferido.
9. **Tests primero:** suite de caracterización (login/dashboard/listado/partial
   HTMX) **antes** de tocar código; tests de RBAC/panel en sus propios pasos.
10. **Acceso solo-Owner** (Usuarios/Configuración): ocultar en sidebar **+ 403** en
    acceso directo.
11. **Scope:** Owner ve "Todos los grupos"; no-Owner ve **solo sus grupos**.
    Precedencia `team` (querystring) › cookie › default. Topbar muestra rol efectivo.
12. **Acciones masivas:** selección persiste en el filtro actual; **"Eliminar"
    masivo confirma** (modal); "Asignar a grupo" abre selector.
13. **Búsqueda global (MVP):** por **dominio**; SAN diferido (denormalizar
    `last_check.san` luego).
14. **Secretos:** SMTP/webhook **write-only/enmascarados** en UI; cabeceras de
    seguridad por settings. Añadir **Pillow** (avatar/logo).
15. **CSS en prod:** Docker **multi-stage** (`build:css` → `collectstatic`).
16. **Grupos:** añadir `default_check_interval` a `Team`.
17. **Detalle de cert:** **datos reales** de `CertificateCheck` (no portar el mock
    del kit: SHA-1/cadena/SAN/historial inventados); pestañas con estado vacío real.

---

## Diseño: limpiar notificaciones conservando el registro (no destructivo)

**Principio:** separar el **evento compartido** (`Alert` + `AlertDelivery`, fuente
de verdad, nunca se borra) del **estado personal** de cada usuario.

**Modelo (apps/alerts):**
```python
class AlertUserState(TimeStampedModel):
    alert = FK(Alert, related_name="user_states")
    user = FK(AUTH_USER_MODEL, related_name="alert_states")
    read_at = DateTimeField(null=True)
    dismissed_at = DateTimeField(null=True)   # 'limpiada' del panel
    # UniqueConstraint(alert, user)
```
+ `UserPreferences.panel_cleared_at` (sello por usuario, para "Limpiar todo" sin
crear N filas). Migrar `Alert.read_by` (M2M) → `AlertUserState.read_at` y deprecar
`read_by` (actualizar `AlertViewSet.read` en el mismo paso).

**Visibilidad:**
- **Campana/panel (topbar):** alertas del ámbito con `status=OPEN`,
  `dismissed_at IS NULL` y `created_at > panel_cleared_at`. El **badge = ese
  conteo**. "Limpiar" las saca al instante.
- **Centro de Alertas (`/alerts/`) y Reportes:** **siempre todo el histórico**
  (incluidas las limpiadas, mostradas **tenues + tag "Archivada"**). `dismissed` es
  solo presentación, nunca un filtro que elimine. → se conserva el registro.
- `read_at` controla resaltado de no-leídas; **"Marcar leída" ≠ "Limpiar"** (no
  vacía el panel).

**Endpoints (web HTMX + CSRF):** `POST /alerts/<id>/read/`,
`POST /alerts/<id>/dismiss/`, `POST /alerts/read-all/`,
`POST /alerts/clear-panel/`, `GET /alerts/panel/`.
**RBAC:** read/dismiss/clear/read-all = estado personal → cualquier usuario con
visibilidad del ámbito (corrige el bug actual que exige ADMIN). Resolver/snooze =
recurso compartido → Admin/Owner.

---

## Modelos / campos nuevos

- `apps/alerts`: **`AlertUserState`** + migración `read_by` → `read_at`.
- `apps/accounts`: **`UserPreferences`** (OneToOne): language, timezone,
  table_density, notify_platform/email/webhook, personal_webhook_url, avatar
  (ImageField), `panel_cleared_at`.
- `apps/core/enums`: `TableDensity` (CÓMODO/COMPACTO).
- `apps/certificates`: `@property validity_percent` (sin columna).
- `apps/teams`: `Team.objects.for_user()` + campo `default_check_interval`.
- `apps/core` `OrganizationSettings`: ventana horaria, dominio, logo (ImageField),
  password_min_length, require_2fa (placeholder), session_timeout, sso/ldap flags;
  `WebhookIntegration.rich_format`.
- `apps/reports` `ScheduledReport`: `send_time` + multi-formato.

---

## Orden de construcción (16 pasos, con Definition of Done)

> Regla anti-conflicto: los archivos compartidos (settings, `config/urls.py`,
> `base.html`, `api/*`, `*/models.py`) se tocan **solo** en fundamentos (1-3) o en
> la integración única (14). Las pantallas viven en módulos `views_*.py` y
> templates **disjuntos**.

| # | Tarea | Rol | Depende |
|---|-------|-----|---------|
| 0 | Suite de caracterización (login, dashboard 200, listado+filtros, partial HTMX) ANTES de tocar código | qa+lead | — |
| 1 | Fundamentos devops/assets: tokens CSS, dark unificado a `data-theme`, Geist self-host, iconos Lucide `{% icon %}`, WhiteNoise/STORAGES/seguridad, requirements (Pillow/WeasyPrint/django-csp/django-auth-ldap) | devops | 0 |
| 2 | Fundamentos backend: modelos+migraciones; `read_by`→`AlertUserState` reversible + actualizar `AlertViewSet.read`; RBAC consolidado (IsScopedAlertViewer, validate_team, create Team solo Owner, anti mass-assignment, throttling, anti-SSRF, legacy reneg False); **único editor de `api/`** | backend | 0 |
| 3 | Fundamentos shell+globales: `base.html` (AppShell, CSRF/HTMX, ToastHost + handler responseError), `_sidebar`, `_topbar` (campana con Limpiar), context processor (scope con precedencia), partials (incl `_drawer_test`), mapeo de estado | frontend-lead | 1,2 |
| 4 | Login + password reset (EmailAuthenticationForm, recordarme, ocultar demo; LDAP en botón corporativo). No edita `config/urls.py` | frontend | 3 |
| 5 | Alertas: centro + endpoints read/dismiss/read-all/clear-panel + campana (Limpiar, tag Archivada). Tests del panel | backend+frontend | 3 |
| 6 | Dashboard Forge UI (KpiCards, ChartCards, CertTable, ActivityFeed); drill con semántica unificada; "Chequear todo" atado al scope | frontend | 3 |
| 7 | Certificados (listado) + CertTable; CRUD modal; bulk (confirmación, selección, anti-SSRF+throttle); export | frontend+backend | 3,6 |
| 8 | CertDetalle: tabs HTMX (Resumen/Cadena-SAN/Técnico/Historial/Alertas), Notificar (endpoint), Probar ahora (drawer), Editar. SOLO `last_check` real | frontend+backend | 2,7 |
| 9 | Grupos: lista + GroupHealthMini + modal Nuevo grupo | frontend+backend | 3 |
| 10 | Usuarios (solo Owner): lista + búsqueda + modal Invitar + acciones | frontend+backend | 3 |
| 11 | Configuración (solo Owner): 5 paneles HTMX (Monitoreo/SMTP/Integraciones/Organización/Seguridad), secretos write-only | frontend+backend | 3 |
| 12 | Perfil: datos/preferencias/notificaciones/mis grupos, guardados parciales, cambiar contraseña, foto | frontend+backend | 3 |
| 13 | Reportes: preview+export síncrono (PDF reportlab/WeasyPrint, Excel, CSV) + CRUD programados (send_time, multi-formato), scheduler Celery DIFERIDO | backend+frontend | 3 |
| 14 | **Integración urls** (único responsable): `apps/web/urls.py` + `config/urls.py` (CustomLoginView + include reports); enlazar nav del sidebar | backend-lead | 4-13 |
| 15 | Hardening + verificación final: throttle/anti-SSRF en web, paridad visual, collectstatic prod, suite completa, scope coherente, 3 estados por pantalla | backend+devops+qa | 14 |

**Ejecución:** en chunks con verificación entre cada uno —
**Fundamentos (0-3) → Pantallas (4-13) → Integración+Hardening (14-15)**.

---

## Riesgos principales (mitigaciones en el plan)

- Doble dark mode (`.dark` vs `[data-theme]`) → unificar a `data-theme` en paso 1
  (mitigado además por entregar solo-claro).
- `ManifestStaticFilesStorage` rompe arranque si falta un asset → iconos inline +
  fuentes con rutas relativas + verificar `collectstatic` en CI.
- Conflictos en archivos compartidos → concentrados en pasos 1-3 y 14.
- RBAC/SSRF/DoS → corregidos en paso 2 antes de exponer escritura.
- Sin tests hoy → suite de caracterización (paso 0) + DoD por paso.
- El DS es React/JSX: se usa **solo como referencia** de tokens/paths/markup;
  nunca se arrastra el bundle a la app HTMX.
