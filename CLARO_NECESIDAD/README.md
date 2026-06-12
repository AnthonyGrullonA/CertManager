# CLARO_NECESIDAD — Documentación de despliegue (Aplicativo N1: CertManager)

Carpeta con todo lo que el equipo de Claro necesita para instalar y aprobar el
despliegue de **CertManager** (monitoreo de certificados SSL/TLS).

## Contenido

| Archivo | Qué es |
|---------|--------|
| [`01_diagrama_flujo_datos.md`](01_diagrama_flujo_datos.md) | Diagrama de alto nivel del flujo de datos (Mermaid + ASCII + detalle). |
| [`02_necesidades_instalacion.md`](02_necesidades_instalacion.md) | Alcance, requisitos del servidor, paquetes, **egress/ingress (firewall)**, BD externa. |
| [`03_cambios_para_produccion.md`](03_cambios_para_produccion.md) | Checklist de cambios y configuración para producción. |
| [`.env.example`](.env.example) | Plantilla del `.env` de producción (cópiala a `.env` y complétala). |
| `.env` | Configuración real (NO versionada — contiene secretos). |

## Scripts de instalación (en la raíz del repo)

| Script | Para qué |
|--------|----------|
| `install_server.sh` | Instala en un **servidor Linux** como servicio (Gunicorn + Scheduler vía systemd, NGINX con TLS). DB externa. |
| `install_docker.sh` + `docker-compose.app.yml` | Levanta **solo el contenedor** del aplicativo con Docker. DB externa. |
| `install_windows.bat` | Arranca local en **Windows con SQLite** para **pruebas**. |
| `data_update_certs_app.sh` | Bootstrap: Owner + configuración por defecto + carga de certificados (`cert.txt`). |

> **`cert.txt` es un paso manual:** lo coloca el responsable en la raíz del repo
> (no se versiona). Formato y ejecución documentados en
> [`03_cambios_para_produccion.md` §7](03_cambios_para_produccion.md).

## Resumen de aprobaciones a solicitar

1. **Base de datos MySQL 8** externa (host/usuario/clave/BD) — ver doc 02 §3.
2. **Aperturas de firewall**: egress (hosts a monitorear :443, SMTP, LDAP, SMS-FTP, webhooks) e ingress (:443) — doc 02 §4 y §6.
3. **Certificado TLS** del FQDN del aplicativo — doc 02 §7.
4. (Opcional) acceso al **índice privado** para `obsforge` y a mirrors PyPI/npm — doc 02 §5.
