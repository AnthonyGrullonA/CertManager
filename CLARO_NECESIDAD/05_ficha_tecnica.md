# Ficha técnica — CertManager

| Campo | Valor |
|-------|-------|
| **Nombre del aplicativo** | CertManager |
| **Versión de entrega** | 1.0.0 |
| **Descripción** | Monitoreo de certificados SSL/TLS multi-grupo con alertas, reportes y API REST. |
| **Tipo** | Aplicación web (server-rendered) + API REST |
| **Criticidad** | Media (operativo / seguridad; no transaccional, sin datos de pago) |
| **Propietario funcional (Owner)** | `jairol_grullon@claro.com.do` |
| **Lenguaje / framework** | Python 3.11+ (probado en 3.13) · Django 5.2 · Django REST Framework |
| **UI** | Server-rendered (design system Forge UI) + Tailwind + HTMX |
| **Servidor de aplicación** | Gunicorn (WSGI) detrás de NGINX |
| **Base de datos** | MySQL 8 (producción) · SQLite (pruebas) |
| **Tareas programadas** | APScheduler en-proceso (`manage.py run_scheduler`) |
| **Autenticación** | Local (email+contraseña) y/o LDAP/Active Directory · API por API key |
| **Roles** | Owner global + por grupo: VIEWER / CONTRIBUTOR / ADMIN |

## Funcionalidades principales

- **Monitoreo:** conexión TLS periódica a cada host, parseo del certificado, días restantes, estado.
- **Alertas:** plataforma (in-app), correo (SMTP), webhook (Teams/Slack), SMS (gateway FTP).
- **Reportes** programados (PDF / Excel / correo).
- **Gestión** de certificados, grupos, usuarios, plantillas de correo.
- **API REST** (certificados, grupos, alertas) autenticada por API key.

## Interfaces externas

| Interfaz | Protocolo / Puerto | Sentido |
|----------|--------------------|---------|
| Usuarios / API | HTTPS 443 | Entrante |
| Base de datos MySQL | TCP 3306 | Saliente |
| Hosts monitoreados | TLS (443 u otro por cert) | Saliente |
| SMTP | 587/465/25 | Saliente |
| LDAP / AD | 389 / 636 | Saliente |
| Gateway SMS | FTP 21 | Saliente |
| Webhooks | HTTPS 443 | Saliente |

## Datos que gestiona

Certificados (dominios, umbrales, estado), destinatarios (correos), grupos,
usuarios, alertas, reportes, plantillas de correo, configuración, registro de
auditoría. **No** procesa datos de tarjeta ni pagos.

## Dimensionamiento mínimo

2 vCPU / 2 GB RAM / 10 GB disco (recomendado 4 vCPU / 4 GB). Ver doc 02 §2.

## Estado de calidad

- **529 pruebas automatizadas** (verde).
- CI: chequeo de sistema + migraciones + suite + auditoría de CVEs (`pip-audit`).
- `pip-audit`: **0 vulnerabilidades** conocidas en dependencias.
- Despliegue verificado end-to-end en Docker, Linux y Windows.
