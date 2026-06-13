"""Blindaje del sistema de páginas de estado/error (catálogo + render + handlers).

Garantiza que: todo el catálogo renderiza sin excepción, los iconos existen, los
tonos/http_status son válidos, los handlers devuelven el status correcto con el
reference_id en el HTML, y handler500 NUNCA propaga (fallback texto plano).
"""
from unittest import mock

from django.test import RequestFactory, TestCase, override_settings

from apps.core import errors
from apps.core.errors import ERROR_CATALOG, VALID_TONES, get_meta, render_status
from apps.web.templatetags.forge_icons import FORGE_ICON_PATHS

rf = RequestFactory()


class CatalogIntegrityTests(TestCase):
    def test_every_entry_valid(self):
        for key, e in ERROR_CATALOG.items():
            self.assertIn(e["icon"], FORGE_ICON_PATHS, f"icono inexistente en {key}: {e['icon']}")
            self.assertIn(e["tone"], VALID_TONES, f"tono inválido en {key}: {e['tone']}")
            self.assertIsInstance(e["http_status"], int, f"http_status no int en {key}")
            self.assertIn(e["category"], {"http", "business", "operational", "tenant", "ux"})

    def test_covers_full_http_range(self):
        # 4xx/5xx clave presentes (muestra representativa del 100%).
        for code in [400, 401, 402, 403, 404, 405, 409, 410, 418, 422, 429, 451,
                     500, 501, 502, 503, 504, 507, 508, 511]:
            self.assertIn(f"http-{code}", ERROR_CATALOG)


class RenderTests(TestCase):
    def test_all_keys_render_without_exception(self):
        req = rf.get("/algo/")
        for key in ERROR_CATALOG:
            resp = render_status(req, key)
            self.assertEqual(resp.status_code, get_meta(key).http_status)

    def test_render_without_obsforge(self):
        # Simula obsforge ausente: el helper debe caer a uuid sin romper.
        req = rf.get("/x/")
        with mock.patch.object(errors, "_obsforge_correlation_id", return_value=None):
            resp = render_status(req, "http-500")
        self.assertEqual(resp.status_code, 500)
        self.assertContains(resp, "ref:", status_code=500)

    def test_ref_card_has_support_fields(self):
        req = rf.get("/ruta/x/")
        resp = render_status(req, "http-404")
        body = resp.content.decode()
        self.assertIn("ref:", body)
        self.assertIn("/ruta/x/", body)       # path
        self.assertIn("GET", body)            # method
        self.assertIn("404", body)            # status
        self.assertIn("Copiar", body)         # botón copiar

    def test_actions_single_red_home_button(self):
        # Toda página de error muestra UN solo botón rojo "Ir al inicio",
        # centrado, sin "Reintentar" ni botón duplicado.
        for key in ["http-404", "http-500", "webhook-error", "http-403"]:
            body = render_status(rf.get("/x/"), key).content.decode()
            # Sin botón Reintentar (data-retry es su marcador; la palabra puede
            # aparecer en el texto del mensaje, p.ej. "Reintentaremos").
            self.assertNotIn("data-retry", body, key)
            self.assertNotIn("btn-ghost", body, key)  # sin botón duplicado
            self.assertEqual(body.count(">Ir al inicio<"), 1, key)
            self.assertRegex(
                body, r'<a class="btn-primary" href="/"[^>]*>Ir al inicio</a>'
            )

    def test_reference_id_uses_request_reference_id(self):
        req = rf.get("/x/")
        req.reference_id = "abc123def456"
        resp = render_status(req, "http-403")
        self.assertContains(resp, "abc123def456", status_code=403)

    def test_render_never_propagates_on_template_error(self):
        # Si el template falla, render_status cae a texto plano (no propaga).
        req = rf.get("/x/")
        with mock.patch("apps.core.errors.render_to_string", side_effect=RuntimeError("boom")):
            resp = render_status(req, "http-500")
        self.assertEqual(resp.status_code, 500)
        self.assertIn(b"500", resp.content)


class HandlerTests(TestCase):
    def test_handlers_status_codes(self):
        req = rf.get("/x/")
        self.assertEqual(errors.bad_request(req).status_code, 400)
        self.assertEqual(errors.permission_denied(req).status_code, 403)
        self.assertEqual(errors.page_not_found(req).status_code, 404)
        self.assertEqual(errors.server_error(req).status_code, 500)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_404_end_to_end(self):
        resp = self.client.get("/ruta-que-no-existe-xyz/")
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "Página no encontrada", status_code=404)
        self.assertContains(resp, "Detalle para soporte", status_code=404)


@override_settings(MAINTENANCE_MODE=True)
class MaintenanceTests(TestCase):
    def test_maintenance_returns_503(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 503)
        self.assertContains(resp, "En mantenimiento", status_code=503)

    def test_health_exempt_from_maintenance(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
