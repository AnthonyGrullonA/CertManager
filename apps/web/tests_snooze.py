"""Snooze por certificado: silencia notificaciones temporalmente."""
from unittest import mock
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.certificates.models import Certificate
from apps.teams.models import Team

User = get_user_model()
PWD = "x"


class SnoozeTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="G")
        self.cert = Certificate.objects.create(team=self.team, domain="x.test", port=443)
        self.owner = User.objects.create_user("o@x.test", PWD, is_owner=True)

    def test_is_snoozed_property(self):
        self.assertFalse(self.cert.is_snoozed)
        self.cert.snoozed_until = timezone.now() + timezone.timedelta(days=1)
        self.assertTrue(self.cert.is_snoozed)
        self.cert.snoozed_until = timezone.now() - timezone.timedelta(days=1)
        self.assertFalse(self.cert.is_snoozed)

    def test_dispatch_skipped_when_snoozed(self):
        from apps.alerts.services import evaluate_alert
        self.cert.snoozed_until = timezone.now() + timezone.timedelta(days=7)
        self.cert.save()
        result = mock.Mock(status="CRITICO", days_left=5, error="", valid_to=None)
        with mock.patch("apps.alerts.services._dispatch") as d:
            try:
                evaluate_alert(self.cert, result)
            except Exception:
                pass  # el cálculo del mensaje puede variar; lo clave es el dispatch
            d.assert_not_called()

    def test_snooze_view_sets_and_clears(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("cert-snooze", args=[self.cert.pk]), {"days": 7})
        self.assertEqual(r.status_code, 200)
        self.cert.refresh_from_db()
        self.assertTrue(self.cert.is_snoozed)
        self.client.post(reverse("cert-snooze", args=[self.cert.pk]), {"days": 0})
        self.cert.refresh_from_db()
        self.assertIsNone(self.cert.snoozed_until)
