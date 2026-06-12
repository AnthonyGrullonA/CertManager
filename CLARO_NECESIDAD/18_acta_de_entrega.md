# Acta de entrega-recepción — CertManager

**Aplicativo:** CertManager (monitoreo de certificados SSL/TLS) · **Versión:** 1.0.0

**Fecha de entrega:** ____ / ____ / ______

## 1. Partes

| Rol | Nombre | Organización | Firma |
|-----|--------|--------------|-------|
| Entrega (proveedor/dev) | ____________________ | ____________ | __________ |
| Recibe (Owner) | Jairol Grullón | Claro | __________ |
| Plataforma / Infra | ____________________ | Claro | __________ |
| Seguridad / Cumplimiento | ____________________ | Claro | __________ |

## 2. Alcance entregado

- [x] Código fuente del aplicativo (repositorio).
- [x] Artefacto/imagen desplegable (Dockerfile) + manifiestos Kubernetes.
- [x] Scripts de aprovisionamiento (Linux/Docker/Windows) + bootstrap de datos.
- [x] Documentación completa de entrega y gobierno (carpeta `CLARO_NECESIDAD/`).
- [x] Suite de pruebas (529) + CI con auditoría de dependencias.

## 3. Verificaciones realizadas

| Verificación | Resultado |
|--------------|-----------|
| Suite de pruebas | 529 PASS |
| `check --deploy` (prod) | Sin hallazgos de seguridad |
| `pip-audit` (CVEs) | 0 vulnerabilidades |
| Secretos en repositorio | Ninguno |
| Aprovisionamiento e2e (Docker/Linux/Windows) | PASS |

## 4. Requisitos a cargo de Claro (prerrequisitos de producción)

- [ ] Base de datos **MySQL 8** externa provista (host/usuario/clave/BD).
- [ ] **Aperturas de firewall** (egress/ingress) — doc 02.
- [ ] **Certificado TLS `*.claro.com.do`** instalado — doc 04.
- [ ] `DJANGO_SECRET_KEY` generado y `.env` de producción completado.
- [ ] (Opcional) índice privado `obsforge` / mirrors PyPI-npm.

## 5. Pendientes / observaciones acordadas

| # | Pendiente | Responsable | Fecha |
|---|-----------|-------------|-------|
| 1 | Pentest formal | Seguridad Claro | ______ |
| 2 | Despliegue en clúster K8s real | Plataforma Claro | ______ |
| 3 | Migración del repositorio al entorno corporativo | Claro | ______ |
| 4 | Carga de `cert.txt` actualizado (migración del monitoreo) | Owner | ______ |
| 5 | UAT (pruebas de aceptación) | Owner | ______ |

## 6. Declaración

Las partes dejan constancia de la entrega-recepción del aplicativo y su
documentación según el alcance descrito. Las observaciones de la sección 5 quedan
registradas para su seguimiento.

_Firmas en la sección 1._
