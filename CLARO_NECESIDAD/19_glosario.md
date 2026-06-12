# Glosario — CertManager

| Término | Definición |
|---------|------------|
| **Certificado SSL/TLS** | Credencial digital que identifica un servicio y cifra la conexión; tiene fecha de expiración. |
| **Chequeo** | Conexión TLS al host para leer su certificado y calcular días restantes/estado. |
| **Umbral de alerta / crítico** | Días antes del vencimiento a partir de los cuales el certificado se marca "por vencer" / "crítico". |
| **Owner** | Rol global con acceso total al aplicativo (grupos, usuarios, configuración). |
| **Grupo (Team)** | Agrupación de certificados y usuarios con roles. |
| **Rol (VIEWER/CONTRIBUTOR/ADMIN)** | Nivel de permiso de un usuario dentro de un grupo. |
| **RBAC** | Control de acceso basado en roles. |
| **2FA / TOTP** | Segundo factor de autenticación con código temporal (app autenticadora). |
| **Lockout** | Bloqueo temporal de acceso tras varios intentos fallidos. |
| **Alerta** | Notificación de un certificado en riesgo (por vencer/vencido/error). |
| **Webhook** | URL que recibe notificaciones (Teams/Slack) por HTTPS. |
| **Gateway SMS** | Servicio que envía SMS; aquí se alimenta dejando un archivo por FTP. |
| **Scheduler** | Planificador en-proceso (APScheduler) que ejecuta chequeos, reportes y backups. |
| **Ventana horaria** | Franja preferida (horario valle) para los chequeos masivos. |
| **Gunicorn** | Servidor de aplicación WSGI que ejecuta Django. |
| **NGINX** | Reverse proxy que termina TLS (443) y redirige al aplicativo. |
| **WhiteNoise** | Componente que sirve los archivos estáticos desde la app (sin CDN). |
| **API key** | Clave para autenticar consumidores de la API REST (se guarda hasheada). |
| **SSRF** | Server-Side Request Forgery; el aplicativo valida hosts para mitigarlo. |
| **HSTS** | Cabecera que obliga al navegador a usar HTTPS. |
| **CSP** | Content-Security-Policy; cabecera que restringe orígenes de scripts/estilos. |
| **AuditLog** | Registro append-only de acciones humanas y eventos de login. |
| **obsforge** | Librería corporativa de observabilidad (opcional). |
| **Loki / Promtail / Grafana** | Stack de logs (almacén / recolector / visualización). |
| **RTO / RPO** | Tiempo objetivo de recuperación / Pérdida máxima de datos aceptable. |
| **SBOM** | Software Bill of Materials; inventario de dependencias. |
| **standalone / prod** | Perfiles de configuración: pruebas (SQLite) / producción (MySQL). |
| **VDI** | Virtual Desktop Infrastructure; escritorio virtual corporativo. |
