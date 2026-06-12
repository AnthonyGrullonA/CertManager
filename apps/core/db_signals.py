"""Endurecimiento de SQLite para uso multiusuario (WAL + timeouts).

Cuando la BD es SQLite (modo standalone / "un solo contenedor"), aplicamos PRAGMAs
de producción en cada conexión nueva: WAL para permitir lecturas concurrentes con
una escritura, busy_timeout para tolerar bloqueos breves y foreign_keys ON.

No afecta a MySQL/Postgres (se ignora por vendor) ni a la BD en memoria de los
tests (se omite WAL para no interferir con el manejo transaccional del runner).

IMPORTANTE: WAL requiere almacenamiento LOCAL/de bloque (ext4, volumen Docker). NO
funciona sobre sistemas de archivos de red (NFS/SMB): ahí daría
``sqlite3.OperationalError`` o corrupción. El default (volumen Docker /data) es
seguro; si DEBÉS poner la BD en NFS, usá MySQL, o forzá journal_mode=DELETE.
"""
from __future__ import annotations

from django.db.backends.signals import connection_created
from django.dispatch import receiver


@receiver(connection_created)
def _apply_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    name = str(connection.settings_dict.get("NAME", "") or "")
    is_memory = (name == ":memory:") or ("memory" in name)
    cursor = connection.cursor()
    # Útiles también en memoria/dev: esperar ante bloqueos y respetar FKs.
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    if not is_memory:
        # WAL solo en BD de archivo (en memoria no aplica y rompería los tests).
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
