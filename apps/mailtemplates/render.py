"""Render de una EmailTemplate a (asunto, texto, HTML) sustituyendo variables.

``render_email(template, context)`` devuelve un ``RenderedEmail`` o ``None`` si
``template`` es None (los emisores caen entonces al texto plano actual → 100%
compatible). El HTML es tabla-based con estilos inline (compatible con clientes
de correo) y encabezado de marca tomado de ``OrganizationSettings``.
"""
from __future__ import annotations

import html as _html
import re
from collections import namedtuple

from .variables import variables_for

RenderedEmail = namedtuple("RenderedEmail", "subject text html")

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def resolve_template(explicit, kind):
    """Plantilla a usar: la explícita (si activa) → la predeterminada del tipo →
    None (el emisor cae al texto plano actual)."""
    if explicit is not None and getattr(explicit, "is_active", False):
        return explicit
    from .models import EmailTemplate

    return EmailTemplate.objects.usable(kind=kind).filter(is_default=True).first()


def substitute(text, ctx) -> str:
    """Reemplaza ``{{var}}`` por su valor del contexto (desconocidas → vacío)."""
    if not text:
        return ""
    return _VAR_RE.sub(lambda m: str(ctx.get(m.group(1), "")), str(text))


def _label(kind, field) -> str:
    return variables_for(kind).get(field, {}).get("label", field)


def _org():
    try:
        from apps.core.models import OrganizationSettings

        return OrganizationSettings.load()
    except Exception:  # noqa: BLE001
        return None


def render_email(template, context, *, org=None) -> "RenderedEmail | None":
    if template is None:
        return None
    ctx = context or {}
    kind = template.kind
    org = org or _org()
    org_name = getattr(org, "org_name", "") or "CertManager"

    subject = substitute(template.subject, ctx)
    text_lines: list[str] = []
    rows: list[str] = [
        f'<tr><td style="padding:16px 24px;background:#dc2626;color:#ffffff;'
        f'font-weight:700;font-size:18px;font-family:Arial,Helvetica,sans-serif">'
        f'{_html.escape(org_name)}</td></tr>'
    ]

    for b in (template.blocks or []):
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        props = b.get("props") or {}
        if t == "heading":
            v = substitute(props.get("text", ""), ctx)
            text_lines.append(v)
            rows.append(
                f'<tr><td style="padding:10px 24px 2px"><h2 style="margin:0;'
                f'font-size:20px;color:#0f172a;font-family:Arial,Helvetica,sans-serif">'
                f'{_html.escape(v)}</h2></td></tr>'
            )
        elif t == "text":
            v = substitute(props.get("text", ""), ctx)
            text_lines.append(v)
            rows.append(
                f'<tr><td style="padding:6px 24px;color:#334155;font-size:14px;'
                f'line-height:1.6;font-family:Arial,Helvetica,sans-serif">'
                f'{_html.escape(v)}</td></tr>'
            )
        elif t == "data":
            field = b.get("field", "")
            label = props.get("label") or _label(kind, field)
            val = str(ctx.get(field, ""))
            text_lines.append(f"{label}: {val}")
            rows.append(
                f'<tr><td style="padding:4px 24px;font-size:14px;color:#334155;'
                f'font-family:Arial,Helvetica,sans-serif"><strong>'
                f'{_html.escape(label)}:</strong> {_html.escape(val)}</td></tr>'
            )
        elif t == "button":
            label = substitute(props.get("label", "Abrir"), ctx)
            href = substitute(props.get("href", "#"), ctx)
            text_lines.append(f"{label}: {href}")
            rows.append(
                f'<tr><td style="padding:14px 24px"><a href="{_html.escape(href)}" '
                f'style="background:#dc2626;color:#ffffff;padding:10px 18px;'
                f'border-radius:8px;text-decoration:none;font-size:14px;'
                f'font-family:Arial,Helvetica,sans-serif">{_html.escape(label)}</a></td></tr>'
            )
        elif t == "divider":
            rows.append(
                '<tr><td style="padding:8px 24px"><hr style="border:none;'
                'border-top:1px solid #e2e8f0;margin:0"></td></tr>'
            )
        elif t == "spacer":
            rows.append('<tr><td style="height:16px;line-height:16px">&nbsp;</td></tr>')
        elif t == "footer":
            v = substitute(props.get("text", ""), ctx)
            text_lines.append(v)
            rows.append(
                f'<tr><td style="padding:16px 24px;color:#94a3b8;font-size:12px;'
                f'border-top:1px solid #e2e8f0;font-family:Arial,Helvetica,sans-serif">'
                f'{_html.escape(v)}</td></tr>'
            )
        # "logo" ya está cubierto por el encabezado de marca.

    text = "\n".join(line for line in text_lines if line) or subject
    html_body = (
        '<!DOCTYPE html><html><body style="margin:0;background:#f8fafc">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;margin:0 auto;background:#ffffff;'
        'border:1px solid #e2e8f0;border-radius:12px;overflow:hidden">'
        + "".join(rows)
        + "</table></body></html>"
    )
    return RenderedEmail(subject=subject, text=text, html=html_body)
