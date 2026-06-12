"""Tests de la pantalla Login (Forge UI).

Usan el URLconf real del proyecto (``config.urls``, que ya cablea
``apps.web.urls_login``), de modo que ``login`` resuelve a ``CustomLoginView``.
Se ejercita con ``reverse()`` y el ``Client`` directamente; no se necesita un
URLconf de prueba aparte.

Tras el overhaul de UI/UX el login tiene un **único botón** (sin SSO corporativo
aparte) y **sin enlace de recuperación de contraseña**: el backend prueba
``ModelBackend`` y luego ``DatabaseLDAPBackend`` automáticamente.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

User = get_user_model()


class LoginViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "Forge-Login-2026!"
        cls.user = User.objects.create_user(
            email="maria@certforge.io", password=cls.password, is_owner=True
        )

    # --- Render ----------------------------------------------------------
    def test_get_login_renders_forge_ui(self):
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "registration/login.html")
        self.assertContains(resp, "forge.css")
        self.assertContains(resp, 'rel="icon"')
        self.assertContains(resp, "img/favicon.svg")
        # Marca + chips de estado, sin credenciales demo.
        self.assertContains(resp, "Iniciar sesión")
        # El control "Recordarme" se retiró por petición del usuario.
        self.assertNotContains(resp, 'name="remember"')
        self.assertContains(resp, 'name="username"')  # email mantiene name=username
        self.assertContains(resp, "status-ok-solid")

    def test_login_has_no_demo_credentials(self):
        resp = self.client.get(reverse("login"))
        self.assertNotContains(resp, "maria@certforge.io")
        self.assertNotContains(resp, "supersecret")

    def test_login_has_password_toggle(self):
        resp = self.client.get(reverse("login"))
        self.assertContains(resp, "data-forge-pw-toggle")

    # --- Un solo botón, sin SSO ni recuperación --------------------------
    def test_login_has_single_submit_button_no_sso(self):
        resp = self.client.get(reverse("login"))
        # Un único botón de envío en el formulario (el primario).
        self.assertEqual(resp.content.count(b'type="submit"'), 1)
        self.assertNotContains(resp, "SSO corporativo")
        self.assertNotContains(resp, 'name="sso"')

    def test_login_has_no_forgot_password_link(self):
        resp = self.client.get(reverse("login"))
        self.assertNotContains(resp, "Olvidaste tu contraseña")

    def test_password_reset_routes_removed(self):
        # Las rutas de recuperación se eliminaron de urls_login.
        for name in (
            "password_reset",
            "password_reset_done",
            "password_reset_complete",
        ):
            with self.assertRaises(NoReverseMatch):
                reverse(name)

    # --- Autenticación ---------------------------------------------------
    def test_valid_credentials_redirect_to_dashboard(self):
        resp = self.client.post(
            reverse("login"),
            {"username": self.user.email, "password": self.password, "remember": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("dashboard"))

    def test_invalid_credentials_show_error_block(self):
        resp = self.client.post(
            reverse("login"),
            {"username": self.user.email, "password": "wrong-pass"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Credenciales inválidas")
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    # --- Sesión (sin "Recordarme") ---------------------------------------
    def test_login_persists_session(self):
        # Sin "Recordarme": la sesión usa la duración por defecto (no expira al
        # cerrar el navegador).
        resp = self.client.post(
            reverse("login"),
            {"username": self.user.email, "password": self.password},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        dash = self.client.get(reverse("dashboard"))
        self.assertTrue(dash.wsgi_request.user.is_authenticated)


class EmailAuthFormTests(TestCase):
    def test_username_field_labelled_correo_and_keeps_name(self):
        from apps.accounts.forms_auth import EmailAuthenticationForm

        form = EmailAuthenticationForm()
        self.assertEqual(form.fields["username"].label, "Correo")
        # El name del campo sigue siendo "username" (clave del POST/backends).
        self.assertIn("username", form.fields)
