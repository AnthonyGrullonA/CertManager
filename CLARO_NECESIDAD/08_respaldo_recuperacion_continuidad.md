# Respaldo, recuperación y continuidad — CertManager

## 1. Activos a respaldar

| Activo | Dónde | Criticidad |
|--------|-------|------------|
| **Base de datos MySQL** | Servidor MySQL (Claro) | **Alta** (toda la data) |
| Configuración (`.env`, certificado TLS) | Servidor / gestor de secretos | Alta |
| `cert.txt` (fuente de migración) | Archivo del operador | Media |
| Logs (`/var/log/certmanager`) | Servidor | Baja (operativo) |
| Código / artefacto | Repositorio + registro de imágenes | Media (reconstruible) |

> La app **no** guarda estado fuera de la MySQL (los estáticos se regeneran con
> `collectstatic`). Respaldar la MySQL respalda prácticamente todo.

## 2. Respaldo

- **MySQL (responsable: Claro/DBA):** según la política corporativa de respaldo
  de bases de datos (recomendado: diario + binlog para PITR).
- **Backup integrado de la app** (complementario): el scheduler ejecuta
  `backup_db` diario; para MySQL genera un `dumpdata` comprimido en `BACKUP_DIR`
  con retención `BACKUP_KEEP` (def. 14). Manual:
  ```bash
  python manage.py backup_db
  ```
- **Configuración/secretos:** versionar el `.env` en el gestor de secretos
  corporativo (NO en el repo). El certificado wildcard ya está en su almacén.

## 3. Recuperación (DRP)

### Objetivos
| Métrica | Objetivo propuesto |
|---------|--------------------|
| **RTO** (tiempo de recuperación) | ≤ 4 horas |
| **RPO** (pérdida máxima de datos) | ≤ 24 horas (o el del respaldo MySQL de Claro) |

### Procedimiento de restauración
1. Restaurar la **MySQL** desde el respaldo (DBA de Claro).
2. Desplegar el aplicativo (Linux/Docker/K8s) apuntando a esa BD (`DB_*`).
3. `migrate` (no-op si la BD ya está al día) + `collectstatic`.
4. Reinstalar el certificado TLS y el `.env`.
5. Arrancar servicios y validar `GET /health/`.
6. Verificar un chequeo de certificado ("Probar ahora").

> Si solo se pierde el **aplicativo** (no la BD): basta redesplegar y reapuntar a
> la MySQL existente — los datos no se pierden.

## 4. Continuidad (BCP)

- **Punto único de falla:** la MySQL externa → la cubre la HA del servicio de BD de Claro.
- **Scheduler:** debe correr **1 instancia** (lock por archivo evita duplicados);
  ante caída, reiniciar (los chequeos se recuperan en la siguiente ventana).
- **Degradación tolerada:** si fallan SMTP/webhook/SMS, las alertas se registran
  como `FAILED` (AlertDelivery) y se reintentan; el aplicativo no se cae.
- **Sin dependencia de servicios externos** para operar (el scheduler es en-proceso).

## 5. Pruebas de recuperación

Recomendado validar la restauración en un entorno de staging al menos
**semestralmente**: restaurar un respaldo MySQL, desplegar y verificar `/health` +
un chequeo. Registrar evidencia (fecha, RTO real, responsable).
