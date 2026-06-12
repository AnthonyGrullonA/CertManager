"""Helpers de plantilla de Forge UI (PASO 3).

- ``status_family``: traduce un estado backend (``CertificateStatus`` /
  ``AlertSeverity``) a su familia semántica de Forge UI (``ok/warn/crit/exp/
  err/none``), que es como los tokens CSS resuelven el color
  (``--status-<familia>-*``).
- ``avatar_tint``: tinte determinista (índice estable a partir del nombre) para
  el avatar de iniciales, espejo de ``Avatar.jsx`` del design system.
- ``initials``: iniciales (máx. 2) de un nombre, con fallback al correo.
"""
from __future__ import annotations

from django import template

register = template.Library()

# Mapeo estado backend -> familia Forge (única fuente de verdad de la capa web).
# CertificateStatus y AlertSeverity comparten claves (POR_VENCER, CRITICO, ...).
# Esquema de color: rojo = PELIGRO real (crítico/vencido), naranja = ATENCIÓN
# (error), gris = pendiente (sin chequear). Las alertas usan su propio
# _severity_family para los badges de su listado.
STATUS_FAMILY = {
    "VIGENTE": "ok",        # verde
    "POR_VENCER": "warn",   # ámbar
    "CRITICO": "exp",       # rojo (peligro)
    "VENCIDO": "exp",       # rojo (peligro)
    "ERROR": "crit",        # naranja (atención)
    "SIN_CHEQUEAR": "none", # gris (pendiente)
}

# Tintes de avatar (variables CSS de tokens). Espejo de TINTS en Avatar.jsx.
AVATAR_TINTS = [
    "--brand-600",
    "--status-ok-fg",
    "--status-warn-fg",
    "--status-err-fg",
    "--status-crit-fg",
    "--slate-600",
]


@register.filter(name="status_family")
def status_family(value):
    """Familia semántica Forge (``ok/warn/crit/exp/err/none``) de un estado."""
    if value is None:
        return "none"
    return STATUS_FAMILY.get(str(value).upper(), "none")


@register.simple_tag(name="avatar_tint")
def avatar_tint(name=""):
    """Variable CSS de tinte determinista a partir del nombre (hash estable)."""
    source = name or ""
    h = 0
    for ch in source:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return AVATAR_TINTS[h % len(AVATAR_TINTS)]


@register.filter(name="initials")
def initials(name, email=""):
    """Iniciales (máx. 2) del nombre; cae al correo si no hay nombre."""
    source = (name or "").strip()
    if source:
        parts = source.split()[:2]
        result = "".join(p[0] for p in parts if p).upper()
        if result:
            return result
    if email:
        return email[0].upper()
    return "?"
