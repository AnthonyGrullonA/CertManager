# Requisitos — CertManager

## 1. Requisitos funcionales (RF)

| ID | Requisito |
|----|-----------|
| RF-01 | Registrar certificados (dominio, puerto, ubicación, grupo, destinatarios, umbrales). |
| RF-02 | Chequear periódicamente cada certificado (handshake TLS) y calcular días restantes/estado. |
| RF-03 | Generar alertas ante vencimiento próximo, vencido o error de chequeo. |
| RF-04 | Notificar por plataforma, correo (SMTP), webhook (Teams/Slack) y SMS. |
| RF-05 | Gestionar grupos y membresías con roles (VIEWER/CONTRIBUTOR/ADMIN). |
| RF-06 | Gestionar usuarios y el rol Owner global. |
| RF-07 | Configurar parámetros globales (monitoreo, SMTP, integraciones, seguridad, LDAP). |
| RF-08 | Generar reportes (PDF/Excel/correo), programables. |
| RF-09 | Exponer API REST (certificados, grupos, alertas) autenticada por API key. |
| RF-10 | Registrar auditoría de acciones humanas y eventos de login. |
| RF-11 | Migrar certificados masivamente desde archivo (`cert.txt`). |
| RF-12 | Silenciar (snooze) alertas de un certificado temporalmente. |

## 2. Requisitos no funcionales (RNF)

| ID | Categoría | Requisito |
|----|-----------|-----------|
| RNF-01 | Seguridad | HTTPS forzado, RBAC, 2FA, auditoría, anti-SSRF, secretos por entorno. |
| RNF-02 | Disponibilidad | Objetivo ≥ 99% en horario hábil; `/health` para monitoreo; sin punto único salvo la BD (HA de Claro). |
| RNF-03 | Rendimiento | El chequeo masivo corre en horario valle (ventana configurable) para no impactar producción. |
| RNF-04 | Escalabilidad | Web escalable horizontalmente (varias réplicas); scheduler **1 instancia** (singleton). |
| RNF-05 | Mantenibilidad | Código probado (529 tests), CI con auditoría; migraciones versionadas. |
| RNF-06 | Portabilidad | 3 modos de despliegue (Linux/Docker/K8s) sobre el mismo artefacto. |
| RNF-07 | Observabilidad | Logs JSON estructurados, auditoría triplicada, integrables a Loki/SIEM. |
| RNF-08 | Compatibilidad | MySQL 8 (prod), SQLite (pruebas); Python 3.11+. |
| RNF-09 | Localización | UI en español e inglés (i18n). |
| RNF-10 | Recuperación | RTO ≤ 4 h, RPO ≤ 24 h (ver doc 08). |

## 3. Restricciones

- La **base de datos MySQL es externa** (la provee Claro); el aplicativo no la administra.
- TLS terminado por NGINX/Ingress con el certificado **`*.claro.com.do`**.
- El **superusuario de Django** es la única cuenta con acceso a `/admin`.
- Secretos **nunca** en el repositorio (van por entorno / gestor de secretos).

## 4. Supuestos

- Conectividad saliente a los hosts a monitorear (firewall), SMTP, LDAP, gateway SMS y webhooks (ver doc 02 §4).
- Disponibilidad del servicio MySQL de Claro.
