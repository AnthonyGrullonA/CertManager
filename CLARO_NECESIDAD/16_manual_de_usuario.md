# Manual de usuario — CertManager

## 1. Acceso

1. Abrir `https://<FQDN>/` (p.ej. `https://certmanager.claro.com.do`).
2. Iniciar sesión con tu **correo** y contraseña (o credenciales del directorio si LDAP está activo).
3. Si la organización exige **2FA**, la primera vez se enrola un código TOTP (app autenticadora).

## 2. Pantallas

| Pantalla | Para qué |
|----------|----------|
| **Dashboard** | Resumen: total de certs, por estado (vigente/por vencer/crítico/vencido/error), próximos a vencer. |
| **Certificados** | Listado con estado, dominio, grupo, ubicación, días restantes; filtros; crear/editar; "Probar ahora"; monitoreo on/off. |
| **Detalle de certificado** | Hero con días restantes, emisor, puerto, ubicación; historial de chequeos; notificar; editar. |
| **Grupos** | Grupos y sus miembros (roles). |
| **Usuarios** (solo Owner) | Crear/editar usuarios, asignar roles, activar/desactivar. |
| **Alertas** | Centro de alertas y panel de notificaciones (leer/descartar/resolver/snooze). |
| **Reportes** | Crear y programar reportes (PDF/Excel/correo). |
| **Configuración** (solo Owner) | Monitoreo, Correo (SMTP), Integraciones, Seguridad, LDAP. |
| **Perfil** | Datos, preferencias, idioma, **cambio de contraseña**, **activar 2FA**. |

## 3. Estados de un certificado

| Estado | Significado |
|--------|-------------|
| Vigente | Lejos del vencimiento |
| Por vencer | Dentro del umbral de alerta |
| Crítico | Dentro del umbral crítico |
| Vencido | Expirado |
| Error | No se pudo chequear (host inalcanzable, etc.) |
| Sin chequear | Aún no se ejecutó un chequeo |

## 4. Tareas comunes

- **Agregar un certificado:** Certificados → Nuevo → dominio, puerto, grupo, destinatarios, umbrales.
- **Probar ahora:** en la lista o el detalle, ejecuta un chequeo inmediato.
- **Silenciar alertas (snooze):** en el detalle, silenciar hasta una fecha.
- **Configurar notificaciones:** Configuración → Correo/Integraciones (SMTP, webhook, SMS).
- **Cambiar mi contraseña / activar 2FA:** Perfil.
- **Cambiar idioma:** Perfil → Preferencias.

## 5. Notificaciones

Cuando un certificado entra en riesgo, se notifica por los canales activos del
certificado: **plataforma** (campana), **correo**, **webhook** (Teams/Slack) y/o
**SMS**. Las alertas se resuelven solas cuando el certificado vuelve a estar sano.

## 6. API REST (para integradores)

- Endpoints: `/api/certificates/`, `/api/teams/`, `/api/alerts/`, docs en `/api/docs/`.
- Autenticación: `Authorization: Api-Key cf_live_…` (las claves se crean en `/settings/api/`, solo Owner).
