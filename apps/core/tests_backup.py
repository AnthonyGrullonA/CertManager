"""Test del comando backup_db (copia + retención)."""
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class BackupDbTests(TestCase):
    def test_creates_backup_and_keeps_retention(self):
        with tempfile.TemporaryDirectory() as d:
            for _ in range(3):
                call_command("backup_db", "--dir", d, "--keep", "2", stdout=StringIO())
            files = [f for f in os.listdir(d) if f.startswith(("db-", "dump-"))]
            # Se crearon respaldos y se conservan como máximo 2 (retención).
            self.assertGreaterEqual(len(files), 1)
            self.assertLessEqual(len(files), 2)
