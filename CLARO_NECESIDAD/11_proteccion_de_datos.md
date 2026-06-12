# Protección de datos — CertManager

## 1. Datos personales tratados

| Dato | Origen | Finalidad |
|------|--------|-----------|
| **Correo electrónico** (usuarios) | Alta de usuario | Autenticación e identificación |
| **Nombre** (usuarios) | Perfil | Identificación en la UI |
| **Correos de destinatarios** | `cert.txt` / configuración | Envío de alertas (grupos de soporte) |
| **IP de origen** | Requests | Auditoría de seguridad (login, acciones) |
| Secreto TOTP (2FA) | Enrolamiento | Segundo factor de autenticación |

> El aplicativo **no** trata datos sensibles especiales (salud, biometría),
> **ni** datos financieros/de pago. El alcance es operativo/técnico.

## 2. Minimización y exactitud

- Solo se almacena lo necesario para operar (correos, nombres, IP de auditoría).
- Los certificados monitoreados son **infraestructura** (dominios), no datos personales.

## 3. Seguridad de los datos

- Contraseñas con hash (PBKDF2); API keys con hash; secretos TOTP/SMTP/LDAP no
  expuestos en claro en la UI (write-only).
- Transmisión cifrada (HTTPS/TLS).
- Acceso por RBAC; auditoría de accesos y cambios.
- En logs con `obsforge` (preset prod) se **redacta PII** (correo/IP) en el stream;
  el dato real queda en `audit.log` y en la tabla `AuditLog` (acceso restringido).

## 4. Retención

| Dato | Retención |
|------|-----------|
| Usuarios | Mientras estén activos; al darse de baja se desactivan (no se borran, por trazabilidad). |
| Auditoría (`AuditLog`) | Según política de Claro (recomendado ≥ 1 año). |
| Logs en fichero | Rotación 10 MB × 10 (audit × 20). |
| Logs en Loki | Según retención del clúster (def. ejemplo 7 días). |
| Historial de chequeos | Acumulativo (purga opcional futura). |

## 5. Derechos de los titulares

Las solicitudes de acceso/rectificación/supresión de un usuario las atiende el
**Owner** desde la pantalla Usuarios (editar/desactivar) y, de requerirse borrado
físico, el DBA de Claro sobre la BD, conforme a la política de protección de datos
corporativa.

## 6. Cumplimiento

Tratamiento alineado con la política de protección de datos de Claro y, según
aplique, la **Ley 172-13** (RD) de protección de datos personales. La definición
de bases legales, plazos y encargados corresponde al área legal/cumplimiento de Claro.
