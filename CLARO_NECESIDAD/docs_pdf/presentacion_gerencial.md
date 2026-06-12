---
marp: true
title: CertManager — Presentación ejecutiva
author: Equipo CertManager
paginate: true
backgroundColor: #ffffff
color: #1f2733
style: |
  :root { --brand:#DA291C; --brand-dark:#A81F15; --ink:#1f2733; --muted:#5b6675; --soft:#f6f8fa; }
  section {
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 24px; padding: 60px 70px; line-height: 1.45;
  }
  h1 { color: var(--brand-dark); font-size: 52px; margin: 0 0 10px; }
  h2 { color: var(--brand-dark); font-size: 34px; border-bottom: 3px solid var(--brand); padding-bottom: 8px; }
  h3 { color: var(--ink); font-size: 26px; }
  strong { color: var(--brand-dark); }
  a { color: var(--brand-dark); }
  code { background: var(--soft); padding: 1px 6px; border-radius: 4px; font-size: 0.85em; }
  table { font-size: 20px; border-collapse: collapse; }
  th { background: var(--brand); color:#fff; }
  th, td { border: 1px solid #e3e7ec; padding: 6px 12px; }
  section::after { color: var(--muted); font-weight: 600; }
  section.lead { background: linear-gradient(135deg,#fff 60%,#fbe9e7); }
  section.lead h1 { font-size: 64px; }
  .kpi { display:flex; gap:28px; margin-top:18px; }
  .kpi div { background:var(--soft); border-left:6px solid var(--brand); padding:14px 20px; border-radius:0 8px 8px 0; }
  .kpi b { color:var(--brand-dark); font-size:40px; display:block; }
  .tag { color: var(--muted); font-size: 20px; letter-spacing: 2px; text-transform: uppercase; }
---

<!-- _class: lead -->
<span class="tag">Claro · Aplicativo N1</span>

# CertManager

### Monitoreo de certificados SSL/TLS — Presentación ejecutiva

**Visibilidad, alertas y control de los certificados de toda la organización.**

`v1.0.0` · Confidencial — uso interno

---

## El problema

Un certificado SSL/TLS **vencido** = un servicio caído o inseguro, sin aviso.

- Cientos de certificados repartidos en dominios y servidores.
- Vencimientos que se descubren **cuando ya fallan** (incidente, no prevención).
- Sin visibilidad centralizada ni responsables claros por grupo.

> El costo de un certificado vencido no es el certificado: es la **indisponibilidad**.

---

## La solución: CertManager

Una plataforma que **vigila** cada certificado y **avisa a tiempo**.

- **Monitorea** automáticamente (handshake TLS) y calcula días restantes.
- **Alerta** por plataforma, correo, Teams/Slack y SMS antes de vencer.
- **Organiza** por grupos de soporte con roles y responsables.
- **Reporta** y expone una **API** para integrarse.

De *“nos enteramos cuando se cae”* a *“lo renovamos antes de que pase”*.

---

## Capacidades clave

| | |
|---|---|
| 🔎 **Monitoreo** | Chequeo periódico en horario valle, estado y días restantes |
| 🔔 **Alertas multicanal** | Plataforma · Correo · Webhook (Teams/Slack) · SMS |
| 👥 **Grupos y roles** | Owner global + VIEWER / CONTRIBUTOR / ADMIN por grupo |
| 📊 **Reportes** | PDF / Excel / correo, programables |
| 🔐 **Seguridad** | 2FA, RBAC, auditoría, HTTPS, anti-SSRF |
| 🔌 **API + LDAP** | Integración y autenticación corporativa |

---

## Arquitectura (alto nivel)

```
Usuarios / API  ──HTTPS 443──>  NGINX (TLS)  ──>  Aplicativo (Django)
                                                  Scheduler (chequeos)
                                         │ MySQL          │ TLS / SMTP / LDAP / SMS / Webhooks
                                         ▼                ▼
                                   Base de datos     Hosts monitoreados y canales
                                   (de Claro)
```

- **Monolito** simple de operar, sin servicios externos para funcionar.
- **3 modos de despliegue** sobre el mismo artefacto: **Linux · Docker · Kubernetes**.

---

## Seguridad y cumplimiento

- **HTTPS forzado** (HSTS, cookies seguras), CSP, anti-SSRF.
- **Accesos:** RBAC por grupo, **2FA**, bloqueo por fuerza bruta, expiración y timeout de sesión.
- **Auditoría** completa de acciones humanas (triplicada).
- **OWASP Top 10** mapeado · **0 CVEs** en dependencias · `check --deploy` limpio.
- Secretos **fuera del código**; admin técnico aislado del uso de negocio.

> Alineado con prácticas ISO/IEC 27001 (detalle en el paquete de entrega).

---

## Calidad — números

<div class="kpi">
<div><b>529</b>pruebas automatizadas (verde)</div>
<div><b>0</b>vulnerabilidades (pip-audit)</div>
<div><b>3/3</b>modos de despliegue verificados e2e</div>
</div>

- Integración continua: chequeos + migraciones + suite + auditoría de CVEs.
- Verificación end-to-end de despliegue **encontró y corrigió 5 defectos** antes de producción.

---

## Despliegue flexible

| Escenario | Para qué |
|-----------|----------|
| **Linux** (systemd + NGINX/TLS) | Producción en servidor |
| **Docker** (app + NGINX/TLS) | Producción contenida, fácil de operar |
| **Kubernetes** | Producción gestionada (Ingress/TLS) |
| **Windows / VDI** | Primera visibilidad y demo (sin admin) |

Base de datos **MySQL** de Claro · TLS con el wildcard **`*.claro.com.do`**.

---

## Entrega y gobierno

Paquete documental completo (`CLARO_NECESIDAD/`):

- Ficha técnica, arquitectura y flujo de datos
- Instalación, operación (runbook), respaldo y continuidad
- Seguridad y cumplimiento, accesos/roles, protección de datos
- Plan de pruebas, requisitos, gestión de cambios, **SBOM**
- Manual de usuario, soporte/SLA y **acta de entrega**

---

## Próximos pasos

1. Provisión por Claro: **MySQL**, **certificado TLS**, **firewall**.
2. Despliegue en el entorno objetivo (Docker/K8s/Linux).
3. Carga de la data real de certificados.
4. **Pentest** y **UAT** (equipos de Claro).
5. Puesta en producción.

---

<!-- _class: lead -->
# Gracias

**CertManager** — visibilidad y control de certificados para Claro.

Owner: `jairol_grullon@claro.com.do` · `v1.0.0` · Confidencial
