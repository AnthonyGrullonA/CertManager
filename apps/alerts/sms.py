"""Envío de SMS por gateway FTP (legacy).

El gateway corporativo consume un archivo dejado por FTP. ``send_sms`` deposita
una línea ``numero|texto`` en el archivo remoto configurado. Es best-effort: ante
cualquier fallo de red/FTP devuelve (False, detalle) sin lanzar, para no tumbar
la evaluación de alertas.
"""
from __future__ import annotations

import ftplib
import io
import logging

logger = logging.getLogger("certmanager.sms")

FTP_TIMEOUT = 10


def send_sms(config, text, number=None):
    """Deposita un SMS en el gateway FTP. Devuelve (ok: bool, detalle: str)."""
    if config is None or not getattr(config, "enabled", False):
        return False, "El gateway SMS está deshabilitado."
    if not config.ftp_host:
        return False, "El gateway SMS no tiene host configurado."
    number = (number or config.default_number or "").strip()
    if not number:
        return False, "No hay número de destino (configura el número por defecto)."

    payload = f"{number}|{text}\r\n".encode("utf-8", "replace")
    remote = config.remote_filename or "sms.log"
    try:
        ftp = ftplib.FTP(timeout=FTP_TIMEOUT)
        ftp.connect(config.ftp_host, 21)
        ftp.login(config.ftp_user or "anonymous", config.ftp_password or "")
        try:
            ftp.storbinary(f"STOR {remote}", io.BytesIO(payload))
        finally:
            try:
                ftp.quit()
            except Exception:  # noqa: BLE001
                ftp.close()
        return True, f"SMS depositado en el gateway ({number})."
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo enviando SMS por FTP: %s", exc)
        return False, f"No se pudo contactar el gateway SMS: {exc}"
