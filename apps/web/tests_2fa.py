"""Tests de 2FA (TOTP) — enrolamiento en Perfil y verificación en login (D)."""
import pyotp
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import TwoFactorDevice, user_has_2fa

User = get_user_model()
HX = {"HTTP_HX_REQUEST": "true"}


class EnrollmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@cf.test", password="secret123")
        self.client.force_login(self.user)

    def test_setup_creates_secret_and_shows_qr(self):
        resp = self.client.get(reverse("two-factor-setup"), **HX)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data:image/png;base64,")  # QR embebido
        device = TwoFactorDevice.objects.get(user=self.user)
        self.assertFalse(device.enabled)
        self.assertTrue(device.secret)

    def test_confirm_with_valid_code_activates(self):
        self.client.get(reverse("two-factor-setup"), **HX)
        device = TwoFactorDevice.objects.get(user=self.user)
        code = pyotp.TOTP(device.secret).now()
        resp = self.client.post(reverse("two-factor-confirm"), {"code": code}, **HX)
        self.assertEqual(resp.status_code, 200)
        device.refresh_from_db()
        self.assertTrue(device.enabled)
        self.assertTrue(user_has_2fa(self.user))

    def test_confirm_with_invalid_code_does_not_activate(self):
        self.client.get(reverse("two-factor-setup"), **HX)
        resp = self.client.post(reverse("two-factor-confirm"), {"code": "000000"}, **HX)
        self.assertEqual(resp.status_code, 422)
        self.assertFalse(TwoFactorDevice.objects.get(user=self.user).enabled)

    def test_disable_with_valid_code_removes_device(self):
        device = TwoFactorDevice.objects.create(user=self.user, secret=pyotp.random_base32())
        from django.utils import timezone
        device.confirmed_at = timezone.now()
        device.save()
        code = pyotp.TOTP(device.secret).now()
        resp = self.client.post(reverse("two-factor-disable"), {"code": code}, **HX)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(TwoFactorDevice.objects.filter(user=self.user).exists())


class LoginFlowTests(TestCase):
    def _enrolled_user(self):
        user = User.objects.create_user(email="2fa@cf.test", password="secret123")
        from django.utils import timezone
        TwoFactorDevice.objects.create(
            user=user, secret=pyotp.random_base32(), confirmed_at=timezone.now()
        )
        return user

    def test_login_with_2fa_redirects_to_verify_without_session(self):
        self._enrolled_user()
        resp = self.client.post(reverse("login"), {"username": "2fa@cf.test", "password": "secret123"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("two-factor-verify"), resp.url)
        # Aún NO autenticado.
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_verify_with_correct_code_logs_in(self):
        user = self._enrolled_user()
        self.client.post(reverse("login"), {"username": "2fa@cf.test", "password": "secret123"})
        code = pyotp.TOTP(user.totp_device.secret).now()
        resp = self.client.post(reverse("two-factor-verify"), {"code": code})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(str(self.client.session.get("_auth_user_id")), str(user.pk))

    def test_verify_with_wrong_code_does_not_log_in(self):
        self._enrolled_user()
        self.client.post(reverse("login"), {"username": "2fa@cf.test", "password": "secret123"})
        resp = self.client.post(reverse("two-factor-verify"), {"code": "000000"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_verify_without_pending_redirects_login(self):
        resp = self.client.get(reverse("two-factor-verify"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.url)

    def test_user_without_2fa_logs_in_normally(self):
        User.objects.create_user(email="plain@cf.test", password="secret123")
        resp = self.client.post(reverse("login"), {"username": "plain@cf.test", "password": "secret123"})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn(reverse("two-factor-verify"), resp.url)
        self.assertIsNotNone(self.client.session.get("_auth_user_id"))
