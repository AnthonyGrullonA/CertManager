"""La página de Ayuda (FAQ) carga para usuarios autenticados y trae contenido."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

U = get_user_model()


class FaqTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = U.objects.create_user(email="u@x.io", password="pw")

    def test_requires_login(self):
        resp = self.client.get(reverse("faq"))
        self.assertEqual(resp.status_code, 302)  # redirige al login

    def test_loads_with_content(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("faq"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "preguntas frecuentes")
        self.assertContains(resp, "¿Cómo agrego un certificado a monitorear?")
        self.assertContains(resp, "Plantillas de correo")
        self.assertContains(resp, "verificación en dos pasos")
        self.assertContains(resp, "¿Cómo exporto los certificados a CSV?")
        self.assertContains(resp, "LDAP")
        self.assertContains(resp, "Usuarios y acceso")
        self.assertContains(resp, "Panel y navegación")
        self.assertContains(resp, "¿Cómo configuro el webhook de Teams o Slack?")
