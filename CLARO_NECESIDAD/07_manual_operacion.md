# Manual de operación (Runbook) — CertManager

Procedimientos para operar el aplicativo en producción. Asume despliegue Linux
(systemd) o Docker/K8s. Comandos relativos al directorio del aplicativo.

## 1. Servicios

| Servicio | Función | Linux (systemd) |
|----------|---------|-----------------|
| Web | Gunicorn (HTTP) | `certmanager.service` |
| Scheduler | Tareas (chequeos, reportes, backups) | `certmanager-scheduler.service` |
| NGINX | TLS 443 + proxy | `nginx.service` |

## 2. Arranque / parada / estado

```bash
sudo systemctl start|stop|restart certmanager certmanager-scheduler
sudo systemctl status certmanager certmanager-scheduler
sudo systemctl reload nginx
```
Docker: `docker compose -f docker-compose.app.yml up -d | down | restart`.
Kubernetes: `kubectl -n certmanager rollout restart deploy/certmanager-web`.

## 3. Salud

```bash
curl -fsS https://<FQDN>/health/      # {"status":"ok","database":true}
```
- `200` = OK · `503` = BD no responde. Integrar en el monitoreo de uptime de Claro.

## 4. Logs

- **stdout** (JSON, una línea por evento) → recogido por el stack del clúster.
- **Fichero:** `/var/log/certmanager/app.log` y `audit.log` (rotados 10 MB × 10).
```bash
journalctl -u certmanager -n 100 -f          # Linux
docker compose -f docker-compose.app.yml logs -f web
kubectl -n certmanager logs -f deploy/certmanager-web
```
Loggers clave: `certmanager.audit` (auditoría), `certmanager.request` (requests),
`certmanager.monitoring` (chequeos), `certmanager.alerts` (entregas), `django.request` (errores 500).

## 5. Tareas programadas (scheduler)

| Tarea | Frecuencia | Control |
|-------|------------|---------|
| Chequeo de certificados | Diario en la **ventana horaria** (def. 02:00) o cada N h | Configuración → Monitoreo |
| Reportes programados | Cada N min | Configuración / Reportes |
| Backup de BD | Diario | `SCHEDULER_BACKUP_HOURS` |

Ejecutar manualmente:
```bash
python manage.py check_certificates       # chequeo inmediato de todos
python manage.py send_scheduled_reports
python manage.py backup_db
```
> Cambiar la frecuencia/ventana requiere **reiniciar `certmanager-scheduler`**.

## 6. Operaciones comunes

| Operación | Comando |
|-----------|---------|
| Crear/actualizar Owner + config | `./data_update_certs_app.sh --skip-certs` |
| Migrar/cargar certificados | colocar `cert.txt` y `./data_update_certs_app.sh` |
| Cambiar contraseña de un usuario | `python manage.py changepassword <email>` |
| Aplicar migraciones (tras upgrade) | `python manage.py migrate` |
| Recolectar estáticos (tras upgrade) | `python manage.py collectstatic --no-input` |

## 7. Troubleshooting

| Síntoma | Causa probable / acción |
|---------|--------------------------|
| `/health` → 503 | BD caída/inalcanzable → revisar MySQL y `DB_*` (firewall 3306). |
| 500 en una página | `django.request` ERROR con traceback (`exc`) en logs → revisar. |
| Chequeos no corren | Scheduler caído o ventana horaria mal → `systemctl status certmanager-scheduler`. |
| Alertas no llegan | Ver `certmanager.alerts` (ERROR de entrega) + config SMTP/webhook/SMS. |
| 301 en bucle | Proxy sin `X-Forwarded-Proto: https` → revisar NGINX. |
| Certificado de un host marca ERROR | Host inalcanzable / SSRF bloqueado / timeout → ver `last_error` del cert. |

## 8. Mantenimiento / upgrade

1. Respaldar la BD (ver doc 08).
2. Desplegar el nuevo artefacto/imagen.
3. `migrate` + `collectstatic`.
4. Reiniciar `certmanager` y `certmanager-scheduler`.
5. Validar `/health` y un chequeo de prueba.
