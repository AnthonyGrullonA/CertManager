# Plan y evidencias de pruebas — CertManager

Guía técnica completa en `docs/testing.md`.

## 1. Estrategia

| Nivel | Cómo |
|-------|------|
| Unitarias / integración | Suite Django (`manage.py test`), BD efímera, sin red. |
| Sistema / configuración | `check`, `check --deploy`, `makemigrations --check`. |
| Seguridad | Pruebas de lockout, 2FA, expiración/timeout, RBAC, anti-SSRF. |
| End-to-end de despliegue | Build + arranque real en Docker/Linux/Windows contra BD. |
| Dependencias | `pip-audit` (CVEs) en CI. |

## 2. Resultados (evidencia)

| Prueba | Resultado |
|--------|-----------|
| **Suite automatizada** | **529 pruebas — PASS** (sin `--parallel`) |
| `manage.py check` | Sin issues |
| `makemigrations --check --dry-run` | Sin migraciones pendientes |
| `check --deploy` (prod) | Sin hallazgos de seguridad |
| `pip-audit` | **0 vulnerabilidades** |
| Aprovisionamiento **Docker** e2e | PASS (NGINX TLS 443 → app → MySQL; bootstrap; migración) |
| Aprovisionamiento **Linux** e2e | PASS (systemd/gunicorn/NGINX TLS → 200) |
| Aprovisionamiento **Windows** e2e | PASS (standalone/SQLite → runserver) |
| Configuración funcional e2e (todos los paneles) | PASS |

## 3. Cobertura por área (≈529 pruebas)

API/RBAC, autenticación/2FA/seguridad, certificados y monitoreo, alertas,
reportes y plantillas, configuración, grupos/usuarios, dashboard, y sondas de
regresión. Desglose por archivo en `docs/testing.md`.

## 4. Hallazgos corregidos durante la verificación e2e

Las pruebas de despliegue detectaron y se corrigieron **5 defectos** previos a
producción:
1. Secretos (`.env`/clave privada) horneados en la imagen Docker → excluidos.
2. `/health/` redirigía en bucle (NGINX sin `X-Forwarded-Proto`) → corregido.
3. Bootstrap `--skip-certs` exigía `cert.txt` → corregido.
4. NGINX `server_name *` inválido (Linux) → corregido.
5. Scheduler marcado "unhealthy" en Docker → corregido.

## 5. Cómo reproducir

```bash
OBSFORGE_ENABLED=0 DJANGO_SETTINGS_MODULE=config.settings.local \
  DJANGO_SECRET_KEY=ci-test python manage.py test
```
CI: `.github/workflows/ci.yml` ejecuta la suite + auditoría en cada cambio.

## 6. Pruebas pendientes (responsable Claro)

- **Pentest formal** (equipo de seguridad).
- **Pruebas de aceptación de usuario (UAT)** con el Owner.
- **Despliegue real en el clúster de Kubernetes** de Claro (manifiestos validados estructuralmente).
