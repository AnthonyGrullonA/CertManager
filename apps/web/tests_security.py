"""Tests de la capa de seguridad: lockout de login, exigencia de 2FA y auditoría.

Cubre OWASP A07 (Authentication Failures) y A09 (Logging Failures).
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AuditLog, OrganizationSettings

User = get_user_model()
PWD = "clave-correcta-123"


class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("user@x.test", PWD)

    @override_settings(LOGIN_LOCKOUT_MAX=3, LOGIN_LOCKOUT_DURATION=900)
    def test_lockout_after_max_failures(self):
        url = reverse("login")
        for _ in range(3):
            self.client.post(url, {"username": "user@x.test", "password": "mala"})
        # Aun con la clave CORRECTA, el acceso queda bloqueado.
        resp = self.client.post(url, {"username": "user@x.test", "password": PWD})
        self.assertContains(resp, "bloqueado")
        self.assertFalse(resp.wsgi_request.user.is_authenticated)
        # Se auditó el bloqueo y los fallos.
        self.assertTrue(AuditLog.objects.filter(action="login_locked").exists())
        self.assertTrue(AuditLog.objects.filter(action="login_failed").exists())

    @override_settings(LOGIN_LOCKOUT_MAX=5)
    def test_success_resets_and_audits(self):
        url = reverse("login")
        self.client.post(url, {"username": "user@x.test", "password": "mala"})
        resp = self.client.post(url, {"username": "user@x.test", "password": PWD}, follow=True)
        self.assertTrue(resp.context["user"].is_authenticated)
        self.assertTrue(AuditLog.objects.filter(action="login", actor=self.user).exists())


class Require2FATests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("u2@x.test", PWD)

    def test_redirects_to_setup_when_org_requires_2fa(self):
        org = OrganizationSettings.load()
        org.require_2fa = True
        org.save()
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("two-factor-setup"))

    def test_no_redirect_when_not_required(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)


class PasswordExpiryTests(TestCase):
    """Expiración de contraseñas (OWASP A07). Apagada por defecto; cuando se
    activa, fuerza el cambio de la contraseña vencida antes de seguir."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("pw@x.test", PWD)

    def _enable(self, days=90):
        org = OrganizationSettings.load()
        org.password_expiry_enabled = True
        org.password_expiry_days = days
        org.save()
        return org

    def _age_password(self, days):
        from django.utils import timezone
        from datetime import timedelta
        old = timezone.now() - timedelta(days=days)
        User.objects.filter(pk=self.user.pk).update(password_changed_at=old)

    def test_disabled_by_default(self):
        org = OrganizationSettings.load()
        self.assertFalse(org.password_expiry_enabled)
        self._age_password(999)
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_redirects_when_expired(self):
        self._enable(days=90)
        self._age_password(120)
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(reverse("profile")))
        self.assertIn("password_expired=1", resp["Location"])

    def test_no_redirect_when_recent(self):
        self._enable(days=90)
        self._age_password(10)
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_profile_is_reachable_while_expired(self):
        # No debe haber bucle: el perfil (donde se cambia la clave) está exento.
        self._enable(days=90)
        self._age_password(120)
        self.client.force_login(self.user)
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, 200)

    def test_superuser_exempt(self):
        su = User.objects.create_superuser("root@x.test", PWD)
        self._enable(days=90)
        User.objects.filter(pk=su.pk).update(
            password_changed_at=None, date_joined=self.user.date_joined
        )
        self._age_password(120)  # no aplica a su, pero da contexto
        self.client.force_login(su)
        resp = self.client.get(reverse("dashboard"))
        self.assertNotEqual(resp.status_code, 302)

    def test_ldap_user_without_usable_password_exempt(self):
        self.user.set_unusable_password()
        self.user.save()
        self._enable(days=90)
        self._age_password(999)
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_set_password_stamps_changed_at(self):
        before = self.user.password_changed_at
        self.user.set_password("otra-clave-distinta-456")
        self.user.save()
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.password_changed_at)
        self.assertNotEqual(self.user.password_changed_at, before)


class AuditSignalTests(TestCase):
    def setUp(self):
        from apps.core import audit
        audit.clear_request()

    def test_user_action_is_audited_and_system_is_not(self):
        from apps.core import audit
        from apps.teams.models import Team

        # Sin contexto de petición (sistema): NO se audita.
        Team.objects.create(name="Sistema")
        self.assertFalse(AuditLog.objects.filter(model="team").exists())

        # Con un actor autenticado en el thread-local: SÍ se audita.
        actor = User.objects.create_user("actor@x.test", PWD)

        class _Req:
            user = actor
            META = {"REMOTE_ADDR": "10.1.2.3"}

        audit.set_request(_Req())
        try:
            t = Team.objects.create(name="Humano")
        finally:
            audit.clear_request()

        entry = AuditLog.objects.filter(model="team", object_id=str(t.pk)).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, "create")
        self.assertEqual(entry.actor, actor)
        self.assertEqual(entry.ip, "10.1.2.3")


class ApiDocsTests(TestCase):
    def test_docs_require_login(self):
        from django.urls import reverse
        r = self.client.get(reverse("api-docs"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_docs_ok_when_authenticated(self):
        from django.urls import reverse
        u = User.objects.create_user("d@x.test", PWD)
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse("api-docs")).status_code, 200)
        self.assertEqual(self.client.get(reverse("api-schema")).status_code, 200)
