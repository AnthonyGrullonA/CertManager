"""Acceso al admin de Django + redirecciones de login (work-stream A).

- Solo el superusuario real entra al admin; los Owner/Admin de la app no.
- Acceso directo a /admin/ sin ser superuser → dashboard (o login si anónimo).
- Visitar el login ya autenticado → dashboard.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AdminAccessTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="root@certforge.local", password="x"
        )
        self.owner = User.objects.create_user(
            email="owner@app.local", password="x", is_owner=True
        )

    def test_superuser_reaches_admin(self):
        self.client.force_login(self.superuser)
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 200)

    def test_app_owner_redirected_to_dashboard(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/admin/")
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])

    def test_app_owner_is_not_staff(self):
        self.assertFalse(self.owner.is_staff)
        self.assertFalse(self.owner.is_superuser)


class LoginRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@app.local", password="x")

    def test_authenticated_user_redirected_from_login(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("login"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)
