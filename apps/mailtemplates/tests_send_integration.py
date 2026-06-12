"""Integración del render en el envío de alertas: HTML+texto con plantilla,
texto plano sin ella (compatibilidad)."""
from django.core import mail
from django.test import TestCase

from apps.alerts.models import Alert
from apps.alerts.services import _send_email
from apps.certificates.models import Certificate
from apps.core.enums import AlertSeverity
from apps.mailtemplates.models import EmailTemplate
from apps.teams.models import Team

CERT_BLOCKS = [
    {"type": "text", "props": {"text": "El cert {{dominio}} {{frase_estado}}."}},
    {"type": "data", "field": "dominio"},
    {"type": "data", "field": "estado"},
    {"type": "data", "field": "dias_restantes"},
    {"type": "data", "field": "vence_el"},
]


class AlertEmailRenderTests(TestCase):
    def setUp(self):
        # Las plantillas predeterminadas sembradas (migración 0002) se limpian para
        # probar deterministamente el fallback a texto plano y la plantilla explícita.
        EmailTemplate.objects.filter(is_default=True).delete()
        self.team = Team.objects.create(name="G")
        self.cert = Certificate.objects.create(team=self.team, domain="a.example.com", port=443)
        self.alert = Alert.objects.create(
            certificate=self.cert, severity=AlertSeverity.CRITICO, message="x"
        )
        mail.outbox = []

    def test_plain_text_without_template(self):
        _send_email(self.alert, "to@x.io", self.cert, "mensaje plano")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.body, "mensaje plano")
        self.assertEqual(getattr(msg, "alternatives", []), [])

    def test_html_with_template(self):
        tpl = EmailTemplate.objects.create(
            name="cert", kind="CERT", subject="{{dominio}} — {{estado}}", blocks=CERT_BLOCKS
        )
        self.cert.email_template = tpl
        self.cert.save(update_fields=["email_template"])
        _send_email(self.alert, "to@x.io", self.cert, "mensaje plano")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "a.example.com — Sin chequear")
        self.assertTrue(msg.alternatives)
        html, mime = msg.alternatives[0]
        self.assertEqual(mime, "text/html")
        self.assertIn("a.example.com", html)

    def test_default_template_used_when_no_explicit(self):
        EmailTemplate.objects.create(
            name="def", kind="CERT", subject="DEF {{dominio}}", blocks=CERT_BLOCKS, is_default=True
        )
        _send_email(self.alert, "to@x.io", self.cert, "mensaje plano")
        self.assertTrue(mail.outbox[0].alternatives)
        self.assertEqual(mail.outbox[0].subject, "DEF a.example.com")
