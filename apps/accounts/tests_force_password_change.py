"""Pantalla de cambio de contraseña forzado en el flujo del login.

Spec 2026-06-12-login-force-password-design.md:
- Con ``must_change_password`` cualquier página redirige a
  ``password-force-change`` (pantalla con el chrome del login).
- La pantalla trae anclas para los validadores visuales en vivo
  (``data-min-length`` real de la organización, reglas por ``data-rule``).
- POST válido: cambia la contraseña, limpia el flag, mantiene sesión.
- POST inválido: errores del servidor en la misma pantalla, flag intacto.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

URL_NAME = "password-force-change"


class ForcePasswordChangeAccessTests(TestCase):
    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse(URL_NAME))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])

    def test_without_flag_redirects_to_dashboard(self):
        user = User.objects.create_user("ok@certforge.test", "x")
        self.client.force_login(user)
        resp = self.client.get(reverse(URL_NAME))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")


class ForcePasswordChangeScreenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("temp@certforge.test", "x")
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        self.client.force_login(self.user)
        self.url = reverse(URL_NAME)

    def test_screen_renders_fields_and_live_rules(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Contraseña nueva")
        self.assertContains(resp, "Repite la contraseña")
        # Anclas del checklist en vivo, con el mínimo real de la organización.
        self.assertContains(resp, 'data-min-length="8"')
        self.assertContains(resp, 'data-rule="length"')
        self.assertContains(resp, 'data-rule="notnumeric"')
        self.assertContains(resp, 'data-rule="match"')

    def test_valid_post_changes_password_and_clears_flag(self):
        resp = self.client.post(
            self.url,
            {"new_password1": "NuevaClave#2026!", "new_password2": "NuevaClave#2026!"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password("NuevaClave#2026!"))
        # La sesión sigue viva y ya navega normal.
        self.assertEqual(self.client.get(reverse("certificate-list")).status_code, 200)

    def test_mismatch_shows_error_in_screen(self):
        resp = self.client.post(
            self.url,
            {"new_password1": "NuevaClave#2026!", "new_password2": "Otra#2026!"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "no coinciden")
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)
        self.assertTrue(self.user.check_password("x"))

    def test_weak_password_rejected_server_side(self):
        # Solo números: lo rechaza NumericPasswordValidator aunque pase el largo.
        resp = self.client.post(
            self.url, {"new_password1": "73519284607381", "new_password2": "73519284607381"}
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)

    def test_force_screen_not_blocked_by_middleware(self):
        # La propia pantalla está exenta del redirect (sin bucle).
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
