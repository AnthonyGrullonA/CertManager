"""Tests de las mejoras plug-and-play: healthcheck y endurecimiento de SQLite."""
from django.db import connection
from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_health_ok_no_auth(self):
        resp = self.client.get(reverse("health"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["database"])

    def test_health_path_literal(self):
        # Debe vivir en /health/ (endpoint de healthcheck para orquestadores).
        self.assertEqual(reverse("health"), "/health/")


class SqlitePragmaTests(TestCase):
    """Verifica que la señal de endurecimiento aplica PRAGMAs en SQLite."""

    def test_pragmas_applied_on_sqlite(self):
        if connection.vendor != "sqlite":
            self.skipTest("Solo aplica a SQLite")
        with connection.cursor() as cur:
            cur.execute("PRAGMA foreign_keys")
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("PRAGMA busy_timeout")
            self.assertEqual(cur.fetchone()[0], 5000)
