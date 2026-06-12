"""Utilidades de logging: formateador JSON + resolución del directorio de logs.

Los logs se escriben en formato JSON (una línea por evento) para que sean
parseables por agregadores (Loki/obsforge, ELK, etc.) y se sincronicen con la
observabilidad. ``resolve_log_dir`` elige ``/var/log/certmanager`` si es
escribible y, si no (p. ej. en un pod de Kubernetes sin permiso o en local),
degrada a ``BASE_DIR/logs`` — nunca rompe el arranque.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# Campos propios de LogRecord que NO son "extra" del usuario.
_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Serializa cada registro a una línea JSON con timestamp ISO-8601 UTC,
    nivel, logger, mensaje, excepción (si hay) y cualquier campo ``extra``."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                data[key] = value
            except (TypeError, ValueError):
                data[key] = str(value)
        return json.dumps(data, ensure_ascii=False)


def resolve_log_dir(preferred: str, fallback: str) -> str | None:
    """Devuelve el primer directorio escribible de (preferido, fallback), creándolo
    si hace falta. Si ninguno es escribible, devuelve None (solo log a stdout)."""
    for candidate in (preferred, fallback):
        if not candidate:
            continue
        try:
            path = Path(candidate)
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return str(path)
        except Exception:  # noqa: BLE001 — permiso/FS de solo lectura: probar el siguiente
            continue
    return None
