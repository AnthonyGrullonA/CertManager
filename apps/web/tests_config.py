"""Tests de Configuración (PASO 11) — 5 paneles HTMX, solo Owner, secretos.

Patrón: ``test_urls_config`` + ``@override_settings(ROOT_URLCONF=...)`` para que
el Client resuelva tanto las urls globales como las propias.

Definition of Done cubierto:
- GET de SMTP/Integraciones NO contiene el secreto (assertNotContains).
- POST sin el campo conserva el valor previo.
- no-Owner -> 403 (no redirección).
- 2FA/SSO solo 'Próximamente'.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.alerts.models import WebhookIntegration
from apps.core.enums import WebhookType
from apps.core.models import LdapConfiguration, OrganizationSettings

User = get_user_model()

URLCONF = "apps.web.test_urls_config"


@override_settings(ROOT_URLCONF=URLCONF)
class ConfigAccessTests(TestCase):
    """RBAC: solo Owner; no-Owner recibe 403; anónimo redirige a login."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="pw-owner-2026", is_owner=True
        )
        cls.member = User.objects.create_user(
            email="member@certforge.test", password="pw-member-2026", is_owner=False
        )

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse("settings"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_owner_gets_200(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("settings"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "config/settings.html")

    def test_non_owner_forbidden_on_page(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("settings"))
        self.assertEqual(resp.status_code, 403)

    def test_non_owner_forbidden_on_panel(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("settings-panel", args=["smtp"]))
        self.assertEqual(resp.status_code, 403)

    def test_non_owner_forbidden_on_test_smtp(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse("settings-test-smtp"))
        self.assertEqual(resp.status_code, 403)

    def test_non_owner_forbidden_on_test_webhook(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse("settings-test-webhook"))
        self.assertEqual(resp.status_code, 403)


@override_settings(ROOT_URLCONF=URLCONF)
class ConfigPanelRenderTests(TestCase):
    """Cada panel activo carga 200; Organización no se expone."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="pw-owner-2026", is_owner=True
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_page_lists_monitoring_focused_sections(self):
        resp = self.client.get(reverse("settings"))
        for label in ["Monitoreo", "Correo (SMTP)", "Integraciones", "Seguridad"]:
            self.assertContains(resp, label)
        self.assertNotContains(resp, "Organización")

    def test_each_panel_renders(self):
        for section in ["monitoreo", "smtp", "integraciones", "seguridad"]:
            resp = self.client.get(reverse("settings-panel", args=[section]))
            self.assertEqual(resp.status_code, 200, section)

    def test_small_numeric_fields_use_compact_control(self):
        resp = self.client.get(reverse("settings-panel", args=["monitoreo"]))
        for field in ("check_interval_hours", "retries", "connect_timeout"):
            self.assertContains(resp, f'name="{field}"')
            self.assertContains(resp, "settings-number-input")

        resp = self.client.get(reverse("settings-panel", args=["seguridad"]))
        self.assertContains(resp, 'name="password_min_length"')
        self.assertContains(resp, "settings-select-compact")
        self.assertContains(resp, 'name="session_timeout"')
        self.assertContains(resp, "settings-number-input")

    def test_organization_panel_removed(self):
        resp = self.client.get(reverse("settings-panel", args=["organizacion"]))
        self.assertEqual(resp.status_code, 404)

    def test_unknown_section_404(self):
        resp = self.client.get(reverse("settings-panel", args=["inexistente"]))
        self.assertEqual(resp.status_code, 404)

    def test_security_panel_2fa_links_to_profile_and_real_ldap(self):
        """2FA ya NO es 'Próximamente': se gestiona por usuario (enlace al perfil);
        el placeholder SSO se reemplazó por el panel LDAP real."""
        resp = self.client.get(reverse("settings-panel", args=["seguridad"]))
        self.assertContains(resp, "2FA")
        # 2FA real por usuario: enlace al perfil, sin 'Próximamente'.
        self.assertNotContains(resp, "Próximamente")
        self.assertContains(resp, reverse("profile"))
        # El placeholder SSO ya NO está: se reemplazó por el panel LDAP real.
        self.assertNotContains(resp, "SSO corporativo")
        # El toggle real de LDAP vive en la tarjeta LDAP (LdapConfiguration.enabled),
        # no en Seguridad (el login es transparente, sin botón).
        self.assertContains(resp, 'name="enabled"')
        # Y el panel LDAP real (campos de core.LdapConfiguration) aparece.
        self.assertContains(resp, "LDAP corporativo")
        self.assertContains(resp, "server_uri")


@override_settings(ROOT_URLCONF=URLCONF)
class SmtpSecretTests(TestCase):
    """Secreto SMTP write-only: nunca se devuelve; POST vacío lo conserva."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="pw-owner-2026", is_owner=True
        )

    def setUp(self):
        self.client.force_login(self.owner)
        s = OrganizationSettings.load()
        s.smtp_host = "smtp.certforge.io"
        s.smtp_user = "alerts@certforge.io"
        s.smtp_password = "super-secreto-123"
        s.smtp_from = "CertManager <no-reply@certforge.io>"
        s.save()

    def test_get_does_not_leak_password(self):
        resp = self.client.get(reverse("settings-panel", args=["smtp"]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "super-secreto-123")
        # Muestra el marcador enmascarado.
        self.assertContains(resp, "configurado")

    def test_post_without_password_keeps_previous(self):
        resp = self.client.post(
            reverse("settings-panel", args=["smtp"]),
            {
                "smtp_host": "smtp.nuevo.io",
                "smtp_port": "465",
                "smtp_user": "alerts@certforge.io",
                "smtp_from": "no-reply@certforge.io",
                "smtp_use_tls": "on",
                "smtp_password": "",  # vacío -> conservar
            },
        )
        self.assertEqual(resp.status_code, 200)
        s = OrganizationSettings.load()
        self.assertEqual(s.smtp_password, "super-secreto-123")
        self.assertEqual(s.smtp_host, "smtp.nuevo.io")  # el resto sí cambia

    def test_post_with_password_overwrites(self):
        self.client.post(
            reverse("settings-panel", args=["smtp"]),
            {
                "smtp_host": "smtp.certforge.io",
                "smtp_port": "587",
                "smtp_user": "alerts@certforge.io",
                "smtp_from": "no-reply@certforge.io",
                "smtp_use_tls": "on",
                "smtp_password": "nuevo-secreto-456",
            },
        )
        s = OrganizationSettings.load()
        self.assertEqual(s.smtp_password, "nuevo-secreto-456")


@override_settings(ROOT_URLCONF=URLCONF)
class WebhookSecretTests(TestCase):
    """Secreto webhook write-only: URL nunca se devuelve; POST vacío la conserva."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="pw-owner-2026", is_owner=True
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.slack = WebhookIntegration.objects.create(
            team=None,
            webhook_type=WebhookType.SLACK,
            name="Slack",
            url="https://hooks.slack.com/services/T0/B0/secreto-webhook",
            rich_format=True,
        )

    def test_get_does_not_leak_webhook_url(self):
        resp = self.client.get(reverse("settings-panel", args=["integraciones"]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "secreto-webhook")
        self.assertContains(resp, "configurado")

    def test_post_without_url_keeps_previous(self):
        resp = self.client.post(
            reverse("settings-panel", args=["integraciones"]),
            {"slack_url": "", "teams_url": "", "rich_format": "on"},
        )
        self.assertEqual(resp.status_code, 200)
        self.slack.refresh_from_db()
        self.assertEqual(
            self.slack.url, "https://hooks.slack.com/services/T0/B0/secreto-webhook"
        )
        self.assertTrue(self.slack.rich_format)

    def test_post_with_url_overwrites(self):
        self.client.post(
            reverse("settings-panel", args=["integraciones"]),
            {
                "slack_url": "https://hooks.slack.com/services/NEW/url-cambiada",
                "teams_url": "",
                "rich_format": "",
            },
        )
        self.slack.refresh_from_db()
        self.assertIn("url-cambiada", self.slack.url)
        self.assertFalse(self.slack.rich_format)


@override_settings(ROOT_URLCONF=URLCONF)
class MonitoreoSaveTests(TestCase):
    """Guardado de Monitoreo persiste en el singleton y muestra toast."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="pw-owner-2026", is_owner=True
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_save_updates_settings(self):
        resp = self.client.post(
            reverse("settings-panel", args=["monitoreo"]),
            {
                "check_interval_hours": "12",
                "connect_timeout": "15",
                "retries": "3",
                "preferred_check_window_start": "02:00",
                "preferred_check_window_end": "05:00",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cambios guardados")
        s = OrganizationSettings.load()
        self.assertEqual(s.check_interval_hours, 12)
        self.assertEqual(s.connect_timeout, 15)
        self.assertEqual(s.retries, 3)


@override_settings(ROOT_URLCONF=URLCONF)
class TestEndpointsTests(TestCase):
    """'Probar envío' / 'Probar webhook' devuelven un toast (200)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="pw-owner-2026", is_owner=True
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_test_smtp_warns_without_host(self):
        resp = self.client.post(reverse("settings-test-smtp"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "host")

    def test_test_smtp_ok_with_host(self):
        from unittest import mock

        from django.core import mail as djmail
        from django.core.mail import get_connection

        s = OrganizationSettings.load()
        s.smtp_host = "smtp.certforge.io"
        s.smtp_from = "no-reply@certforge.io"
        s.email_copy_enabled = True
        s.email_copy_address = "copia@certforge.io"
        s.save()
        # Envío real, pero a una conexión en memoria (sin red) para el test.
        locmem = get_connection("django.core.mail.backends.locmem.EmailBackend")
        with mock.patch("apps.core.mail.smtp_connection", return_value=locmem):
            resp = self.client.post(reverse("settings-test-smtp"))
        self.assertContains(resp, "prueba")
        self.assertEqual(len(djmail.outbox), 1)
        self.assertIn("copia@certforge.io", djmail.outbox[0].bcc)

    def test_test_webhook_warns_without_config(self):
        resp = self.client.post(reverse("settings-test-webhook"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "webhook")

    def test_test_webhook_ok_with_config(self):
        from unittest import mock

        WebhookIntegration.objects.create(
            team=None,
            webhook_type=WebhookType.SLACK,
            name="Slack",
            url="https://hooks.slack.com/services/X",
        )
        fake = mock.Mock()
        fake.raise_for_status.return_value = None
        with mock.patch("requests.post", return_value=fake) as post:
            resp = self.client.post(reverse("settings-test-webhook"))
        self.assertContains(resp, "prueba")
        post.assert_called_once()

    def test_test_webhook_blocks_internal_url_ssrf(self):
        """Anti-SSRF: un webhook a una IP interna/metadata no debe contactarse."""
        from unittest import mock

        WebhookIntegration.objects.create(
            team=None,
            webhook_type=WebhookType.GENERIC,
            name="Interno",
            url="http://169.254.169.254/latest/meta-data/",
        )
        with mock.patch("requests.post") as post:
            resp = self.client.post(reverse("settings-test-webhook"))
        self.assertContains(resp, "No se pudo")
        post.assert_not_called()  # bloqueado antes de cualquier petición


# ---------------------------------------------------------------------------
# Panel LDAP corporativo (sobre core.LdapConfiguration) — secreto write-only.
# ---------------------------------------------------------------------------
@override_settings(ROOT_URLCONF=URLCONF)
class LdapPanelTests(TestCase):
    """El sub-panel LDAP de Seguridad: edición Owner, secreto bind_password."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="pw-owner-2026", is_owner=True
        )
        cls.member = User.objects.create_user(
            email="member@certforge.test", password="pw-member-2026", is_owner=False
        )

    def setUp(self):
        self.client.force_login(self.owner)
        cfg = LdapConfiguration.load()
        cfg.server_uri = "ldap://dc.empresa.com:389"
        cfg.bind_dn = "CN=svc,DC=empresa,DC=com"
        cfg.bind_password = "secreto-bind-999"
        cfg.user_search_base = "OU=Usuarios,DC=empresa,DC=com"
        cfg.save()

    def test_seguridad_panel_includes_ldap_card(self):
        resp = self.client.get(reverse("settings-panel", args=["seguridad"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "LDAP corporativo")
        self.assertContains(resp, "Servidor (URI)")
        self.assertContains(resp, "Probar conexión")
        self.assertContains(resp, "{login}")

    def test_get_does_not_leak_bind_password(self):
        resp = self.client.get(reverse("settings-panel", args=["seguridad"]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "secreto-bind-999")
        self.assertContains(resp, "configurado")  # marcador enmascarado

    def test_post_without_password_keeps_previous(self):
        resp = self.client.post(
            reverse("settings-panel", args=["seguridad"]),
            {
                "panel": "ldap",
                "enabled": "on",
                "server_uri": "ldaps://dc.nuevo.com:636",
                "use_ssl": "on",
                "bind_dn": "CN=svc,DC=empresa,DC=com",
                "bind_password": "",  # vacío -> conservar
                "user_search_base": "OU=Usuarios,DC=empresa,DC=com",
                "user_filter": "(mail={login})",
                "email_attribute": "mail",
                "connect_timeout": "8",
            },
        )
        self.assertEqual(resp.status_code, 200)
        cfg = LdapConfiguration.load()
        self.assertEqual(cfg.bind_password, "secreto-bind-999")  # conservado
        self.assertEqual(cfg.server_uri, "ldaps://dc.nuevo.com:636")  # el resto cambia
        self.assertTrue(cfg.enabled)

    def test_post_with_password_overwrites(self):
        self.client.post(
            reverse("settings-panel", args=["seguridad"]),
            {
                "panel": "ldap",
                "server_uri": "ldap://dc.empresa.com:389",
                "bind_dn": "CN=svc,DC=empresa,DC=com",
                "bind_password": "nuevo-bind-000",
                "user_search_base": "OU=Usuarios,DC=empresa,DC=com",
                "user_filter": "(mail={login})",
                "email_attribute": "mail",
                "connect_timeout": "8",
            },
        )
        cfg = LdapConfiguration.load()
        self.assertEqual(cfg.bind_password, "nuevo-bind-000")

    def test_non_owner_forbidden_on_test_ldap(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse("settings-test-ldap"))
        self.assertEqual(resp.status_code, 403)

    def test_test_ldap_returns_toast_and_persists_result(self):
        from unittest import mock

        with mock.patch(
            "apps.accounts.ldap_backend.test_connection",
            return_value=(False, "No se pudo conectar: timeout"),
        ):
            resp = self.client.post(reverse("settings-test-ldap"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "forge-toast")
        self.assertContains(resp, "No se pudo conectar")
        cfg = LdapConfiguration.load()
        self.assertIsNotNone(cfg.last_test_at)
        self.assertFalse(cfg.last_test_ok)
        self.assertIn("timeout", cfg.last_test_message)

    def test_test_ldap_ok_toast(self):
        from unittest import mock

        with mock.patch(
            "apps.accounts.ldap_backend.test_connection",
            return_value=(True, "Conexión y bind de servicio correctos."),
        ):
            resp = self.client.post(reverse("settings-test-ldap"))
        self.assertContains(resp, "correcta")
        cfg = LdapConfiguration.load()
        self.assertTrue(cfg.last_test_ok)


# ---------------------------------------------------------------------------
# Backend de autenticación LDAP (apps.accounts.ldap_backend).
# ---------------------------------------------------------------------------
class LdapBackendTests(TestCase):
    """Reglas del backend: deshabilitado -> None; usuario inexistente -> None."""

    def _backend(self):
        from apps.accounts.ldap_backend import DatabaseLDAPBackend

        return DatabaseLDAPBackend()

    def test_disabled_returns_none(self):
        cfg = LdapConfiguration.load()
        cfg.enabled = False
        cfg.server_uri = "ldap://dc.empresa.com:389"
        cfg.save()
        result = self._backend().authenticate(
            None, username="alguien@empresa.com", password="x"
        )
        self.assertIsNone(result)

    def test_enabled_but_unknown_local_user_returns_none(self):
        cfg = LdapConfiguration.load()
        cfg.enabled = True
        cfg.server_uri = "ldap://dc.empresa.com:389"
        cfg.user_search_base = "OU=Usuarios,DC=empresa,DC=com"
        cfg.save()
        # No existe ningún usuario local con ese correo -> None sin tocar la red.
        result = self._backend().authenticate(
            None, username="fantasma@empresa.com", password="x"
        )
        self.assertIsNone(result)

    def test_missing_credentials_returns_none(self):
        self.assertIsNone(self._backend().authenticate(None, username="", password=""))

    def test_test_connection_without_uri(self):
        from apps.accounts.ldap_backend import test_connection

        cfg = LdapConfiguration.load()
        cfg.server_uri = ""
        cfg.save()
        ok, msg = test_connection(cfg)
        self.assertFalse(ok)
        self.assertIn("servidor", msg.lower())


# ---------------------------------------------------------------------------
# Comando seed_integrations: siembra SMTP / SMS / destinatario por defecto.
# ---------------------------------------------------------------------------
class SeedIntegrationsTests(TestCase):
    """seed_integrations carga la config desde variables de entorno CF_SEED_*
    (sin secretos hardcodeados en el repo) de forma idempotente."""

    SEED_ENV = {
        "CF_SEED_SMTP_HOST": "smtp.proveedor.test",
        "CF_SEED_SMTP_USER": "user-test",
        "CF_SEED_SMTP_PASSWORD": "secreto-test",
        "CF_SEED_SMTP_FROM": "alertas@certforge.test",
        "CF_SEED_EMAIL_COPY_ADDRESS": "copia@certforge.test",
        "CF_SEED_DEFAULT_RECIPIENT": "copia@certforge.test",
        "CF_SEED_SMS_FTP_HOST": "10.0.0.9",
        "CF_SEED_SMS_FTP_USER": "sms-test",
        "CF_SEED_SMS_FTP_PASSWORD": "sms-secreto-test",
        "CF_SEED_SMS_DEFAULT_NUMBER": "8090000000",
    }

    def test_seed_populates_smtp_sms_and_recipient(self):
        import os
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command

        from apps.core.models import SmsGatewayConfig
        from apps.teams.models import Team

        Team.objects.create(name="Sin asignar")

        with mock.patch.dict(os.environ, self.SEED_ENV):
            call_command("seed_integrations", stdout=StringIO())

        org = OrganizationSettings.load()
        self.assertEqual(org.smtp_host, "smtp.proveedor.test")
        self.assertEqual(org.smtp_password, "secreto-test")  # secreto desde entorno
        self.assertEqual(org.smtp_from, "alertas@certforge.test")
        self.assertTrue(org.email_copy_enabled)
        self.assertEqual(org.email_copy_address, "copia@certforge.test")

        sms = SmsGatewayConfig.load()
        self.assertEqual(sms.ftp_host, "10.0.0.9")
        self.assertFalse(sms.enabled)  # queda desactivado

        team = Team.objects.get(name="Sin asignar")
        self.assertIn("copia@certforge.test", team.default_recipients)

    def test_seed_is_idempotent(self):
        import os
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command

        from apps.teams.models import Team

        Team.objects.create(name="Sin asignar")
        with mock.patch.dict(os.environ, self.SEED_ENV):
            call_command("seed_integrations", stdout=StringIO())
            call_command("seed_integrations", stdout=StringIO())  # 2ª vez no rompe

        org = OrganizationSettings.load()
        self.assertEqual(org.smtp_host, "smtp.proveedor.test")

    def test_seed_without_env_is_noop(self):
        """Sin variables CF_SEED_*, no siembra secretos (repo público seguro)."""
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_integrations", stdout=StringIO())
        org = OrganizationSettings.load()
        self.assertEqual(org.smtp_password, "")
        self.assertEqual(org.smtp_host, "")
