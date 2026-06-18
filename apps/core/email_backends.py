"""Backend de correo SMTP compatible con servidores en modo FIPS.

En un host con OpenSSL en modo FIPS, MD5 está prohibido. La autenticación SMTP
``CRAM-MD5`` usa HMAC-MD5, así que ``smtplib.SMTP.login`` revienta con
``[digital envelope routines] ... unsupported (md5 in FIPS mode)`` ANTES de
probar PLAIN/LOGIN (el bucle de ``login`` solo captura ``SMTPAuthenticationError``,
no el ``ValueError`` de MD5).

Este backend quita ``CRAM-MD5`` de los mecanismos anunciados por el servidor, de
modo que ``smtplib`` elige ``PLAIN``/``LOGIN`` (seguros sobre STARTTLS/SSL y
FIPS-aprobados). No necesita root ni desactivar FIPS.
"""
from __future__ import annotations

import smtplib

from django.core.mail.backends.smtp import EmailBackend


def _login_without_cram_md5(self, user, password, *, initial_response_ok=True):
    """``login`` de smtplib pero descartando CRAM-MD5 de lo anunciado."""
    self.ehlo_or_helo_if_needed()
    feats = self.esmtp_features.get("auth")
    if feats:
        self.esmtp_features["auth"] = " ".join(
            m for m in feats.split() if m.upper() != "CRAM-MD5"
        )
    return super(type(self), self).login(
        user, password, initial_response_ok=initial_response_ok
    )


class _FipsSafeSMTP(smtplib.SMTP):
    login = _login_without_cram_md5


class _FipsSafeSMTP_SSL(smtplib.SMTP_SSL):
    login = _login_without_cram_md5


class FipsSafeEmailBackend(EmailBackend):
    """EmailBackend SMTP que evita CRAM-MD5 (incompatible con FIPS)."""

    @property
    def connection_class(self):
        return _FipsSafeSMTP_SSL if self.use_ssl else _FipsSafeSMTP
