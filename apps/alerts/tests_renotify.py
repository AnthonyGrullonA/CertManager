"""Dedup de notificaciones: no re-enviar la misma alerta salvo escalada o N días."""
from datetime import timedelta
from types import SimpleNamespace

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.alerts.models import Alert, AlertDelivery
from apps.alerts.services import evaluate_alert
from apps.certificates.models import Certificate, CertificateRecipient
from apps.core.enums import AlertSeverity, AlertStatus, CertificateStatus, NotificationChannel
from apps.teams.models import Team


def _result(status, days):
    return SimpleNamespace(status=status, days_left=days, error_message="")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ALERT_RENOTIFY_DAYS=7,
)
class RenotifyTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Infra")  # notify_email=True por defecto
        self.cert = Certificate.objects.create(domain="api.cf.test", team=self.team)
        CertificateRecipient.objects.create(certificate=self.cert, email="dueno@cf.test")
        mail.outbox = []

    def _emails(self):
        return AlertDelivery.objects.filter(channel=NotificationChannel.EMAIL).count()

    def test_new_alert_sends_email(self):
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 20))
        self.assertEqual(Alert.objects.filter(status=AlertStatus.OPEN).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self._emails(), 1)

    def test_same_severity_within_window_does_not_resend(self):
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 20))
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 19))
        # Sigue una sola alerta abierta y NO se reenvió el correo.
        self.assertEqual(Alert.objects.filter(status=AlertStatus.OPEN).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self._emails(), 1)

    def test_escalation_resends(self):
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 20))
        evaluate_alert(self.cert, _result(CertificateStatus.CRITICO, 5))  # escala
        self.assertEqual(len(mail.outbox), 2)
        alert = Alert.objects.get(status=AlertStatus.OPEN)
        self.assertEqual(alert.severity, AlertSeverity.CRITICO)

    def test_renotify_after_window(self):
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 20))
        # Envejecer el último envío más allá de la ventana (created_at es auto_now_add).
        AlertDelivery.objects.update(created_at=timezone.now() - timedelta(days=8))
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 18))
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(ALERT_RENOTIFY_DAYS=0)
    def test_renotify_days_zero_always_resends(self):
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 20))
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 19))
        self.assertEqual(len(mail.outbox), 2)  # 0 = comportamiento previo (siempre)

    def test_healthy_resolves_open_alert(self):
        evaluate_alert(self.cert, _result(CertificateStatus.POR_VENCER, 20))
        evaluate_alert(self.cert, _result(CertificateStatus.VIGENTE, 200))
        self.assertEqual(Alert.objects.filter(status=AlertStatus.OPEN).count(), 0)
        self.assertEqual(Alert.objects.filter(status=AlertStatus.RESOLVED).count(), 1)
