"""Respaldo de la base de datos con retención.

- SQLite: copia binaria consistente del archivo (usa la API de backup de sqlite3,
  segura aunque la app esté escribiendo).
- Otros motores (MySQL/PostgreSQL): vuelca a ``dumpdata`` JSON comprimido
  (portátil, sin depender de mysqldump/pg_dump en el host).

Conserva los últimos ``BACKUP_KEEP`` respaldos y borra los más viejos. Pensado
para correr por el scheduler (cada ``SCHEDULER.BACKUP_HOURS``) o a mano:

    python manage.py backup_db [--keep N] [--dir RUTA]
"""
from __future__ import annotations

import gzip
import os
import sqlite3

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Respalda la base de datos con retención (SQLite: copia; otros: dumpdata)."

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, default=None, help="Cuántos respaldos conservar.")
        parser.add_argument("--dir", default=None, help="Directorio destino.")

    def handle(self, *args, **options):
        backup_dir = options["dir"] or getattr(settings, "BACKUP_DIR", str(settings.BASE_DIR / "backups"))
        keep = options["keep"] if options["keep"] is not None else getattr(settings, "BACKUP_KEEP", 14)
        os.makedirs(backup_dir, exist_ok=True)
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")

        engine = connection.settings_dict.get("ENGINE", "")
        if "sqlite3" in engine:
            path = self._backup_sqlite(backup_dir, stamp)
        else:
            path = self._backup_dumpdata(backup_dir, stamp)

        self._prune(backup_dir, keep)
        size_kb = os.path.getsize(path) // 1024
        self.stdout.write(self.style.SUCCESS(f"Backup creado: {path} ({size_kb} KB). Conservando {keep}."))

    def _backup_sqlite(self, backup_dir, stamp):
        src = connection.settings_dict["NAME"]
        dest = os.path.join(backup_dir, f"db-{stamp}.sqlite3")
        # API de backup de sqlite3: copia consistente incluso con escrituras activas.
        source = sqlite3.connect(src)
        try:
            target = sqlite3.connect(dest)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        return dest

    def _backup_dumpdata(self, backup_dir, stamp):
        dest = os.path.join(backup_dir, f"dump-{stamp}.json.gz")
        with gzip.open(dest, "wt", encoding="utf-8") as fh:
            call_command(
                "dumpdata",
                "--natural-foreign",
                "--natural-primary",
                exclude=["contenttypes", "auth.permission", "sessions.session"],
                stdout=fh,
            )
        return dest

    def _prune(self, backup_dir, keep):
        if keep <= 0:
            return
        files = sorted(
            (f for f in os.listdir(backup_dir) if f.startswith(("db-", "dump-"))),
            reverse=True,
        )
        for stale in files[keep:]:
            try:
                os.remove(os.path.join(backup_dir, stale))
            except OSError:
                pass
