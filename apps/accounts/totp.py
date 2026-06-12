"""Utilidades TOTP (2FA) — RFC 6238 sobre pyotp + QR con qrcode.

Aísla la dependencia de pyotp/qrcode para que vistas y tests usen una API simple.
"""
from __future__ import annotations

import base64
from io import BytesIO

import pyotp
import qrcode

ISSUER = "CertManager"


def new_secret() -> str:
    """Nuevo secreto Base32 para un dispositivo TOTP."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    """URI ``otpauth://`` para Google/Microsoft Authenticator."""
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_data_uri(uri: str) -> str:
    """PNG del QR como data-URI embebible en un <img src=...>."""
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def verify(secret: str, code: str) -> bool:
    """Valida un código TOTP (tolera ±1 ventana para desfases de reloj)."""
    if not secret or not code:
        return False
    return bool(pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1))
