"""Tests del canal SMS: panel de configuración, regla de gating (igual que
webhook) y despacho del notificador."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.enums import NotificationChannel
from apps.core.models import SmsGatewayConfig
from apps.teams.models import Team

User = get_user_model()
PWD = "x"


class SmsPanelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@x.test", PWD, is_owner=True)
        self.client.force_login(self.owner)

    def test_panel_saves_sms_config(self):
        resp = self.client.post(
            reverse("settings-panel", args=["integraciones"]),
            {
                "panel": "sms",
                "enabled": "on",
                "ftp_host": "ftp.sms.test",
                "ftp_user": "u",
                "ftp_password": "secreto",
                "default_number": "8090000000",
                "remote_filename": "sms.log",
            },
        )
        self.assertEqual(resp.status_code, 200)
        cfg = SmsGatewayConfig.load()
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.ftp_host, "ftp.sms.test")
        self.assertEqual(cfg.ftp_password, "secreto")  # write-only, guardado

    def test_password_is_write_only(self):
        cfg = SmsGatewayConfig.load()
        cfg.ftp_host = "ftp.sms.test"
        cfg.ftp_password = "previo"
        cfg.save()
        # POST con password vacío conserva el previo.
        self.client.post(
            reverse("settings-panel", args=["integraciones"]),
            {"panel": "sms", "ftp_host": "ftp.sms.test", "ftp_password": "",
             "remote_filename": "sms.log"},
        )
        self.assertEqual(SmsGatewayConfig.load().ftp_password, "previo")


class SmsGatingTests(TestCase):
    """La opción SMS del certificado solo aparece si el gateway está configurado
    (misma regla que webhook)."""

    def setUp(self):
        self.owner = User.objects.create_user("owner@x.test", PWD, is_owner=True)
        Team.objects.create(name="G1")
        self.client.force_login(self.owner)

    def test_sms_option_hidden_when_not_configured(self):
        resp = self.client.get(reverse("cert-create"))
        self.assertNotContains(resp, "notify_sms")

    def test_sms_option_visible_when_gateway_enabled(self):
        cfg = SmsGatewayConfig.load()
        cfg.enabled = True
        cfg.ftp_host = "ftp.sms.test"
        cfg.save()
        resp = self.client.get(reverse("cert-create"))
        self.assertContains(resp, "notify_sms")


class SmsDispatchTests(TestCase):
    def test_dispatch_sends_sms_and_records_delivery(self):
        from apps.alerts.models import Alert, AlertDelivery
        from apps.alerts.services import _dispatch
        from apps.certificates.models import Certificate

        team = Team.objects.create(name="G", notify_platform=False, notify_email=False)
        cfg = SmsGatewayConfig.load()
        cfg.enabled = True
        cfg.ftp_host = "ftp.sms.test"
        cfg.default_number = "8090000000"
        cfg.save()
        cert = Certificate.objects.create(team=team, domain="x.test", port=443, notify_sms=True)
        alert = Alert.objects.create(certificate=cert, status="OPEN", message="vence")

        with mock.patch("apps.alerts.sms.send_sms", return_value=(True, "ok")) as m:
            _dispatch(cert, alert, "vence pronto")

        m.assert_called_once()
        self.assertTrue(
            AlertDelivery.objects.filter(alert=alert, channel=NotificationChannel.SMS).exists()
        )
