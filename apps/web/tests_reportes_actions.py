"""Tests de "Enviar prueba" y "Preview de un programado" (work-stream C)."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.certificates.models import Certificate
from apps.core.enums import CertificateStatus, ReportFrequency, ReportTemplate
from apps.reports.models import ScheduledReport
from apps.teams.models import Team

User = get_user_model()
URLCONF = "apps.web.test_urls_reportes"


@override_settings(ROOT_URLCONF=URLCONF, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ScheduledActionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(email="o@cf.test", password="x", is_owner=True)
        cls.team = Team.objects.create(name="Infra")
        Certificate.objects.create(
            domain="a.cf.test", team=cls.team, status=CertificateStatus.VIGENTE, days_left=90,
        )
        cls.report = ScheduledReport.objects.create(
            name="Inventario semanal", template=ReportTemplate.INVENTORY,
            frequency=ReportFrequency.WEEKLY, formats=["CSV"], created_by=cls.owner,
            recipients=["equipo@cf.test"],
        )

    def setUp(self):
        self.client.force_login(self.owner)
        mail.outbox = []

    def test_preview_scheduled_renders(self):
        resp = self.client.get(reverse("report-preview-scheduled", args=[self.report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Inventario semanal")
        # Trae el formulario de enviar prueba.
        self.assertContains(resp, "Enviar prueba")
        self.assertContains(resp, reverse("report-test-send", args=[self.report.pk]))

    def test_test_send_sends_email_to_address(self):
        resp = self.client.post(
            reverse("report-test-send", args=[self.report.pk]),
            {"email": "qa@cf.test"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("qa@cf.test", mail.outbox[0].to)
        self.assertTrue(mail.outbox[0].attachments)  # adjunto generado

    def test_test_send_rejects_invalid_email(self):
        resp = self.client.post(
            reverse("report-test-send", args=[self.report.pk]),
            {"email": "no-es-correo"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "inválido")
        self.assertEqual(len(mail.outbox), 0)

    def test_scheduled_actions_scoped(self):
        """Un usuario sin visibilidad del reporte recibe 404."""
        outsider = User.objects.create_user(email="x@cf.test", password="x")
        self.client.force_login(outsider)
        resp = self.client.get(reverse("report-preview-scheduled", args=[self.report.pk]))
        self.assertEqual(resp.status_code, 404)
