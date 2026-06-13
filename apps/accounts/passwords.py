"""Generación de contraseñas temporales (reset por el Owner).

La temporal se muestra UNA vez y se fuerza su cambio en el siguiente login
(``User.must_change_password``), así que prioriza poder copiarse/teclearse sin
errores: alfabeto sin caracteres ambiguos (``l/1/I/O/0``). Nunca se persiste en
claro.
"""
from __future__ import annotations

import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

TEMP_PASSWORD_LENGTH = 14
# Letras/dígitos legibles + símbolos seguros en correo/copy-paste.
_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789#%+=@"


def generate_temp_password(length: int = TEMP_PASSWORD_LENGTH) -> str:
    """Contraseña temporal aleatoria que pasa los validadores de Django.

    Reintenta si una combinación particular no valida (p.ej. sin dígitos para
    un validador de complejidad); con este largo/alfabeto es casi imposible
    necesitar más de un intento.
    """
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        try:
            validate_password(candidate)
            return candidate
        except ValidationError:
            continue
