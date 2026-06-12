"""Avatares SVG generativos para CertManager (Forge UI).

Resuelve el bug "la foto de perfil no se ve": en vez de depender de storage, el
usuario puede elegir uno de un set de avatares SVG DETERMINISTAS, geométricos y
tecnológicos. Cada avatar se compone de:

- una **paleta** (par de tonos Forge) elegida por el índice, y
- una **forma** geométrica (nodo, circuito, hexágono, escudo, onda, ...).

El render es 100% inline (sin archivos, sin storage, sin runtime JS) y estable:
el mismo índice produce siempre el mismo SVG. ``avatar_choice`` se guarda en
``UserPreferences`` y los índices válidos son ``1..AVATAR_COUNT``.

Uso en plantilla::

    {% load forge_avatars %}
    {% avatar_svg 7 %}            {# tamaño por defecto (md) #}
    {% avatar_svg prefs.avatar_choice size="lg" %}
    {% for i in avatar_indices %}{% avatar_svg i size="sm" %}{% endfor %}
"""
from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# ---------------------------------------------------------------------------
# Paletas (par fondo/figura). Tonos tecnológicos legibles en chrome claro.
# El degradado da profundidad sin depender de tokens (el SVG es autónomo).
# ---------------------------------------------------------------------------
PALETTES = [
    ("#4338ca", "#818cf8"),  # indigo
    ("#0e7490", "#22d3ee"),  # cyan
    ("#047857", "#34d399"),  # emerald
    ("#b45309", "#fbbf24"),  # amber
    ("#be123c", "#fb7185"),  # rose
    ("#6d28d9", "#a78bfa"),  # violet
    ("#1d4ed8", "#60a5fa"),  # blue
    ("#0f766e", "#2dd4bf"),  # teal
    ("#a16207", "#facc15"),  # gold
    ("#9f1239", "#f472b6"),  # magenta
]

# Tamaños (px). Espejo de las clases .forge-avatar--*.
SIZES = {"xs": 22, "sm": 28, "md": 36, "lg": 44, "xl": 64}

# Color de la figura sobre el fondo (blanco translúcido = look "glass" técnico).
_FG = "rgba(255,255,255,0.92)"
_FG_SOFT = "rgba(255,255,255,0.55)"


def _node(p):
    """Nodo + satélites (grafo / red)."""
    return (
        f'<circle cx="32" cy="32" r="9" fill="{_FG}"/>'
        f'<circle cx="14" cy="18" r="4.5" fill="{p}"/>'
        f'<circle cx="50" cy="18" r="4.5" fill="{p}"/>'
        f'<circle cx="32" cy="52" r="4.5" fill="{p}"/>'
        f'<path d="M32 32 14 18M32 32 50 18M32 32 32 52" stroke="{_FG_SOFT}" stroke-width="2.5"/>'
    )


def _hex(p):
    """Hexágono concéntrico."""
    return (
        f'<path d="M32 12 50 22V42L32 52 14 42V22Z" fill="{_FG}"/>'
        f'<path d="M32 22 41 27V37L32 42 23 37V27Z" fill="{p}"/>'
    )


def _circuit(p):
    """Trazas de circuito con pads."""
    return (
        f'<path d="M12 24H28V12M52 24H40V40H24" stroke="{_FG}" stroke-width="3" fill="none"/>'
        f'<circle cx="28" cy="12" r="4" fill="{_FG}"/>'
        f'<circle cx="52" cy="24" r="4" fill="{_FG}"/>'
        f'<circle cx="24" cy="40" r="4" fill="{p}"/>'
    )


def _shield(p):
    """Escudo (seguridad)."""
    return (
        f'<path d="M32 12c6 4 12 4 16 4v14c0 12-9 17-16 20-7-3-16-8-16-20V16c4 0 10 0 16-4z" fill="{_FG}"/>'
        f'<path d="m25 32 5 5 10-11" stroke="{p}" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def _wave(p):
    """Onda / señal."""
    return (
        f'<path d="M10 36c6-14 12-14 18 0s12 14 18 0 12-14 8 0" stroke="{_FG}" stroke-width="3.5" fill="none" stroke-linecap="round"/>'
        f'<circle cx="32" cy="36" r="3.5" fill="{_FG}"/>'
    )


def _grid(p):
    """Cuadrícula de bloques (datos)."""
    cells = ""
    for r in range(2):
        for c in range(2):
            fill = _FG if (r + c) % 2 == 0 else p
            cells += f'<rect x="{16 + c * 18}" y="{16 + r * 18}" width="14" height="14" rx="3" fill="{fill}"/>'
    return cells


def _orbit(p):
    """Órbita con planeta."""
    return (
        f'<circle cx="32" cy="32" r="6" fill="{_FG}"/>'
        f'<ellipse cx="32" cy="32" rx="18" ry="9" stroke="{_FG_SOFT}" stroke-width="2.5" fill="none" transform="rotate(-25 32 32)"/>'
        f'<circle cx="48" cy="24" r="3.5" fill="{p}"/>'
    )


def _bolt(p):
    """Rayo (energía)."""
    return (
        f'<path d="M34 12 20 36h10l-4 16 18-26H32z" fill="{_FG}"/>'
    )


def _layers(p):
    """Capas apiladas."""
    return (
        f'<path d="M32 14 52 24 32 34 12 24z" fill="{_FG}"/>'
        f'<path d="M12 32 32 42 52 32" stroke="{_FG}" stroke-width="3" fill="none"/>'
        f'<path d="M12 40 32 50 52 40" stroke="{p}" stroke-width="3" fill="none"/>'
    )


def _prism(p):
    """Prisma / diamante facetado."""
    return (
        f'<path d="M32 12 50 28 32 52 14 28z" fill="{_FG}"/>'
        f'<path d="M32 12 32 52M14 28H50" stroke="{p}" stroke-width="2.5"/>'
    )


# Formas disponibles (combinadas con paletas -> AVATAR_COUNT variantes).
SHAPES = [_node, _hex, _circuit, _shield, _wave, _grid, _orbit, _bolt, _layers, _prism]

# Total de avatares deterministas (10 formas x 10 paletas = 100, expuestos 50).
AVATAR_COUNT = 50


def _resolve(index: int):
    """(forma, paleta_oscura, paleta_clara) a partir de un índice 1..N estable."""
    i = (int(index) - 1) % AVATAR_COUNT
    shape = SHAPES[i % len(SHAPES)]
    dark, light = PALETTES[(i // len(SHAPES)) % len(PALETTES)]
    return shape, dark, light


@register.simple_tag(name="avatar_svg")
def avatar_svg(index, size="md"):
    """Renderiza el avatar SVG nº ``index`` (1..AVATAR_COUNT) inline.

    ``size`` admite las claves de ``SIZES`` (xs/sm/md/lg/xl) o un entero de px.
    Índices <= 0 devuelven cadena vacía (el caller cae a iniciales/foto).
    """
    try:
        idx = int(index)
    except (TypeError, ValueError):
        return ""
    if idx <= 0:
        return ""

    if isinstance(size, str):
        px = SIZES.get(size, SIZES["md"])
    else:
        try:
            px = int(size)
        except (TypeError, ValueError):
            px = SIZES["md"]

    shape, dark, light = _resolve(idx)
    gid = f"cfav{idx}"
    svg = (
        f'<svg class="forge-avatar__svg" width="{px}" height="{px}" '
        f'viewBox="0 0 64 64" role="img" aria-hidden="true" '
        f'style="display:block;border-radius:50%;">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{light}"/>'
        f'<stop offset="1" stop-color="{dark}"/>'
        f'</linearGradient></defs>'
        f'<rect width="64" height="64" rx="32" fill="url(#{gid})"/>'
        f'{shape(light)}'
        f'</svg>'
    )
    return mark_safe(svg)


@register.simple_tag(name="avatar_indices")
def avatar_indices():
    """Lista ``[1..AVATAR_COUNT]`` para pintar la grilla del picker en Perfil."""
    return list(range(1, AVATAR_COUNT + 1))
