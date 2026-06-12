# Soporte y niveles de servicio (SLA) — CertManager

> Propuesta base; los valores definitivos se acuerdan con Claro en el contrato/acta.

## 1. Horario y canales

| Concepto | Valor (propuesto) |
|----------|--------------------|
| Horario de soporte | Días hábiles, horario de oficina (definir zona/horas) |
| Canal | Correo / ticket (definir) |
| Contacto del Owner | `jairol_grullon@claro.com.do` |

## 2. Clasificación de incidentes y tiempos

| Severidad | Definición | Respuesta | Resolución objetivo |
|-----------|------------|-----------|---------------------|
| **S1 — Crítico** | Aplicativo caído / sin acceso para todos | 1 h | 4 h |
| **S2 — Alto** | Función principal afectada (no chequea, no notifica) | 4 h | 1 día hábil |
| **S3 — Medio** | Función secundaria o a un grupo | 1 día hábil | 3 días hábiles |
| **S4 — Bajo** | Consulta, cosmético, mejora | 2 días hábiles | Según planificación |

## 3. Disponibilidad objetivo

- **≥ 99%** en horario hábil (excluye ventanas de mantenimiento y fallas de
  servicios externos provistos por Claro — MySQL, red, SMTP/LDAP).
- Salud verificable en `GET /health/`.

## 4. Escalamiento

1. **Nivel 1 — Operación (Claro):** revisar servicios (`systemctl`/pods), logs y `/health` (doc 07).
2. **Nivel 2 — Plataforma/Infra (Claro):** MySQL, red/firewall, certificados, recursos.
3. **Nivel 3 — Proveedor (dev):** defectos de aplicación (con logs/evidencia).

## 5. Exclusiones

- Fallas de infraestructura provista por Claro (BD, red, DNS, SMTP, LDAP, gateway SMS).
- Cambios no autorizados sobre la configuración o el entorno.
- El **server de desarrollo** (modo VDI/pruebas) no tiene SLA.

## 6. Mantenimiento

Las ventanas de mantenimiento (upgrades, parches) se coordinan con el Owner y se
ejecutan preferentemente en **horario valle**, con respaldo previo (doc 08).
