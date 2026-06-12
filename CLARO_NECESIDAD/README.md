# CertManager — Paquete de entrega y gobierno (Aplicativo N1)

Documentación de control normativo para la **entrega del aplicativo CertManager**
(monitoreo de certificados SSL/TLS) al equipo/cliente. Todos los documentos están
aterrizados en esta aplicación real.

- **Aplicativo:** CertManager · **Versión de entrega:** 1.0.0
- **Tipo:** Aplicación web (Django) + API REST · monitoreo de certificados
- **Propietario funcional (Owner):** `jairol_grullon@claro.com.do`
- **Criticidad:** Media (operativo/seguridad; no transaccional)

---

## Índice de documentos

### A. Identificación y arquitectura
| Doc | Contenido |
|-----|-----------|
| [`05_ficha_tecnica.md`](05_ficha_tecnica.md) | Ficha técnica del aplicativo (datos clave en una página). |
| [`06_arquitectura.md`](06_arquitectura.md) | Arquitectura, componentes e integraciones. |
| [`01_diagrama_flujo_datos.md`](01_diagrama_flujo_datos.md) | Diagrama de alto nivel del flujo de datos. |

### B. Despliegue
| Doc | Contenido |
|-----|-----------|
| [`02_necesidades_instalacion.md`](02_necesidades_instalacion.md) | Requisitos de servidor, paquetes, **egress/ingress (firewall)**, BD externa. |
| [`03_cambios_para_produccion.md`](03_cambios_para_produccion.md) | Checklist de configuración para producción + carga de datos. |
| [`04_aprovisionamiento_y_certificados.md`](04_aprovisionamiento_y_certificados.md) | Servir en 443/TLS con `*.claro.com.do`; dónde colocar el certificado (Linux/Docker/K8s). |
| [`../k8s/`](../k8s/) | Manifiestos de Kubernetes. |
| [`.env.example`](.env.example) | Plantilla de configuración de producción. |

### C. Operación y continuidad
| Doc | Contenido |
|-----|-----------|
| [`07_manual_operacion.md`](07_manual_operacion.md) | Runbook: arranque/parada, monitoreo, tareas, troubleshooting. |
| [`08_respaldo_recuperacion_continuidad.md`](08_respaldo_recuperacion_continuidad.md) | Respaldo, recuperación (RTO/RPO) y continuidad. |

### D. Seguridad y cumplimiento
| Doc | Contenido |
|-----|-----------|
| [`09_seguridad_y_cumplimiento.md`](09_seguridad_y_cumplimiento.md) | Controles de seguridad, OWASP Top 10, matriz de cumplimiento. |
| [`10_gestion_accesos_y_roles.md`](10_gestion_accesos_y_roles.md) | RBAC, políticas de acceso/contraseña/2FA, matriz RACI. |
| [`11_proteccion_de_datos.md`](11_proteccion_de_datos.md) | Datos personales tratados, retención y privacidad. |

### E. Calidad y requisitos
| Doc | Contenido |
|-----|-----------|
| [`12_plan_y_evidencias_de_pruebas.md`](12_plan_y_evidencias_de_pruebas.md) | Plan de pruebas y evidencias (suite + e2e). |
| [`13_requisitos.md`](13_requisitos.md) | Requisitos funcionales y no funcionales (RNF). |

### F. Gobierno y entrega
| Doc | Contenido |
|-----|-----------|
| [`14_gestion_de_cambios_y_versiones.md`](14_gestion_de_cambios_y_versiones.md) | Control de versiones, ramas, releases y cambios. |
| [`15_sbom_y_licencias.md`](15_sbom_y_licencias.md) | Inventario de dependencias (SBOM) y licencias. |
| [`17_soporte_y_sla.md`](17_soporte_y_sla.md) | Niveles de soporte, contacto y escalamiento. |
| [`18_acta_de_entrega.md`](18_acta_de_entrega.md) | Acta de entrega-recepción (para firmar). |

### G. Usuario y referencia
| Doc | Contenido |
|-----|-----------|
| [`16_manual_de_usuario.md`](16_manual_de_usuario.md) | Manual de usuario (pantallas, roles, tareas). |
| [`19_glosario.md`](19_glosario.md) | Glosario de términos. |
| [`../PRESENTACION_VDI.md`](../PRESENTACION_VDI.md) | Primera visibilidad en VDI sin admin. |

---

## Aprobaciones a solicitar (resumen)

1. **MySQL 8** externa (host/usuario/clave/BD) — doc 02 §3.
2. **Aperturas de firewall** egress/ingress — doc 02 §4 y §6.
3. **Certificado TLS** `*.claro.com.do` — doc 04 §2.
4. (Opcional) índice privado `obsforge` + mirrors PyPI/npm — doc 02 §5.
