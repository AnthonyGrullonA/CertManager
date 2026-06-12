# SBOM y licencias — CertManager

Inventario de software de terceros (Software Bill of Materials). Estado de CVEs:
**`pip-audit` → 0 vulnerabilidades conocidas** a la fecha de entrega.

## 1. Dependencias Python (runtime)

| Paquete | Uso | Licencia |
|---------|-----|----------|
| Django (>=5.0,<5.3) | Framework web | BSD-3-Clause |
| djangorestframework | API REST | BSD |
| django-filter | Filtros de API | BSD |
| django-environ | Configuración por entorno | MIT |
| cryptography | Parseo de certificados | Apache-2.0 / BSD |
| python-dateutil | Recurrencia de reportes | Apache-2.0 / BSD |
| APScheduler (>=3.10,<4) | Planificador en-proceso | MIT |
| pyotp | 2FA TOTP | MIT |
| qrcode[pil] | QR de 2FA | BSD |
| requests | Envío de webhooks | Apache-2.0 |
| Pillow | Imágenes (avatares/logo) | MIT-CMU (HPND) |
| django-csp | Cabeceras CSP | BSD |
| whitenoise[brotli] | Estáticos | MIT |
| ldap3 | LDAP/AD | LGPL-3.0 |
| drf-spectacular | OpenAPI/Swagger | BSD |
| reportlab | PDF | BSD |
| openpyxl | Excel | MIT |
| **Producción:** mysqlclient | Driver MySQL | GPL-2.0 (con excepción FOSS) |
| **Producción:** gunicorn | Servidor WSGI | MIT |
| **Opcional:** obsforge[django] | Observabilidad (índice privado Claro) | Privada/corporativa |

## 2. Dependencias frontend (build)

| Paquete | Uso | Licencia |
|---------|-----|----------|
| tailwindcss (^3.4) | Generación del CSS (solo build) | MIT |
| htmx (servido localmente) | Interactividad UI | BSD-2 / Zero-Clause |
| Chart.js (umd, local) | Gráficos del dashboard/reportes | MIT |

## 3. Imagen base (Docker)

| Capa | Imagen | Licencia |
|------|--------|----------|
| Build CSS | `node:20-alpine` | MIT (Node) / varias |
| Runtime | `python:3.13-slim` | PSF / varias |
| Reverse proxy | `nginx:1.27-alpine` | BSD-2 |

## 4. Notas de licenciamiento

- El stack es **mayormente permisivo** (MIT/BSD/Apache).
- `mysqlclient` es **GPL-2.0** con la *FOSS License Exception* de Oracle: su uso
  como driver de una aplicación no obliga a liberar el código del aplicativo.
- `ldap3` es **LGPL-3.0**: se usa como librería (enlace dinámico), sin modificarla.
- `obsforge` es **privada de Claro** y **opcional** (la app funciona sin ella).
- El **aplicativo CertManager** es propiedad de Claro (definir/incluir `LICENSE` en
  el repositorio corporativo según política de Claro).

## 5. Generar el SBOM detallado

```bash
pip freeze                 # versiones exactas instaladas
pip-audit                  # CVEs
pip install pip-licenses && pip-licenses --format=markdown   # licencias detalladas
```
