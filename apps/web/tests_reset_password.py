"""Reset de contraseña con temporal (solo Owner) — spec 2026-06-12.

- El Owner genera una contraseña temporal para otro usuario; se muestra UNA vez
  (elemento ``#temp-password``) y opcionalmente se envía por correo (sin BCC).
- El usuario queda con ``must_change_password``: el middleware lo manda al
  Perfil hasta que fije su propia contraseña.
- Guardas: a sí mismo y usuarios LDAP -> 400; no-Owner -> 403.
"""
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.passwords import generate_temp_password

User = get_user_model()

AMBIGUOUS = set("l1IO0")


def _extract_temp(html):
    m = re.search(r'id="temp-password"[^>]*>([^<]+)<', html)
    return m.group(1).strip() if m else None


class GenerateTempPasswordTests(TestCase):
    def test_length_and_alphabet(self):
        pwd = generate_temp_password()
        self.assertGreaterEqual(len(pwd), 14)
        self.assertFalse(set(pwd) & AMBIGUOUS, pwd)

    def test_passes_django_validators(self):
        validate_password(generate_temp_password())  # no debe lanzar

    def test_not_repeated(self):
        self.assertNotEqual(generate_temp_password(), generate_temp_password())


class ResetPasswordViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "owner@certforge.test", "x", is_owner=True
        )
        self.member = User.objects.create_user("member@certforge.test", "x")
        self.url = reverse("user-reset-password", args=[self.member.pk])
        self.client.force_login(self.owner)

    def test_get_returns_confirm_modal(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "member@certforge.test")
        self.assertContains(resp, "send_email")

    def test_post_sets_temp_password_and_flag(self):
        resp = self.client.post(self.url, {})
        self.assertEqual(resp.status_code, 200)
        temp = _extract_temp(resp.content.decode())
        self.assertTrue(temp, "el partial debe mostrar la temporal en #temp-password")
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(temp))
        self.assertTrue(self.member.must_change_password)
        self.assertEqual(len(mail.outbox), 0)  # sin checkbox no envía correo

    def test_post_with_send_email_mails_user_without_bcc(self):
        resp = self.client.post(self.url, {"send_email": "1"})
        self.assertEqual(resp.status_code, 200)
        temp = _extract_temp(resp.content.decode())
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["member@certforge.test"])
        self.assertEqual(msg.bcc, [])
        self.assertIn(temp, msg.body)

    def test_cannot_reset_self(self):
        url = reverse("user-reset-password", args=[self.owner.pk])
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, 400)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.must_change_password)

    def test_cannot_reset_ldap_user(self):
        ldap_user = User.objects.create_user("ldap@certforge.test")
        ldap_user.set_unusable_password()
        ldap_user.save()
        resp = self.client.post(
            reverse("user-reset-password", args=[ldap_user.pk]), {}
        )
        self.assertEqual(resp.status_code, 400)

    def test_non_owner_gets_403(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)

    def test_detail_page_shows_reset_button(self):
        resp = self.client.get(reverse("user-detail", args=[self.member.pk]))
        self.assertContains(resp, reverse("user-reset-password", args=[self.member.pk]))

    def test_detail_page_hides_button_for_self(self):
        resp = self.client.get(reverse("user-detail", args=[self.owner.pk]))
        self.assertNotContains(
            resp, reverse("user-reset-password", args=[self.owner.pk])
        )


class MustChangePasswordFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("temp@certforge.test", "x")
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        self.client.force_login(self.user)

    def test_any_page_redirects_to_profile(self):
        resp = self.client.get(reverse("certificate-list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("profile"), resp["Location"])
        self.assertIn("password_reset=1", resp["Location"])

    def test_profile_itself_is_exempt_and_shows_banner(self):
        resp = self.client.get(reverse("profile") + "?password_reset=1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "temporal")

    def test_changing_password_clears_flag(self):
        resp = self.client.post(
            reverse("password-change"),
            {
                "old_password": "x",
                "new_password1": "NuevaClave#2026!",
                "new_password2": "NuevaClave#2026!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        # Ya puede navegar sin redirección forzada.
        resp = self.client.get(reverse("certificate-list"))
        self.assertEqual(resp.status_code, 200)
