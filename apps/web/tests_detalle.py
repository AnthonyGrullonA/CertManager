"""Tests de la pantalla CertDetalle (Forge UI · PASO 8).

Usan el ROOT_URLCONF de prueba ``apps.web.test_urls_detalle`` para resolver las
urls globales + las del PASO 7 (cert-test/cert-create) + las propias del detalle
(cert-detail, cert-detail-tab, cert-notify, cert-edit).

Cubren la DoD:
- tabs con deep-link (?tab=) y panel HTMX por pestaña;
- estado vacío por pestaña cuando no hay last_check;
- pestaña Alertas con histórico completo (incl. dismissed/archivadas);
- ningún dato inventado (solo el último CertificateCheck real);
- Notificar funciona (RBAC Miembro, throttle, registro de AlertDelivery).
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alerts.models import Alert, AlertDelivery, AlertUserState
from apps.certificates.models import Certificate, CertificateCheck, CertificateRecipient
from apps.core.enums import (
    AlertSeverity,
    AlertStatus,
    CertificateStatus,
    DeliveryStatus,
    MembershipRole,
)
from apps.core.models import OrganizationSettings
from apps.teams.models import Membership, Team

User = get_user_model()

URLCONF = "apps.web.test_urls_detalle"


def _make_check(cert, **kw):
    defaults = dict(
        checked_at=timezone.now(),
        status=CertificateStatus.VIGENTE,
        days_left=90,
        valid_from=timezone.now() - timedelta(days=10),
        valid_to=timezone.now() + timedelta(days=90),
        issuer="CN=Let's Encrypt",
        subject="CN=api.ejemplo.com",
        serial="0A:3F:91:E2",
        fingerprint_sha256="9F:2A:C1:08:5E",
        signature_algorithm="sha256WithRSAEncryption",
        key_size=2048,
        san=["api.ejemplo.com", "www.api.ejemplo.com"],
        chain=["Root · ISRG Root X1", "Intermedio · R3", "Hoja · api.ejemplo.com"],
        latency_ms=142,
    )
    defaults.update(kw)
    return CertificateCheck.objects.create(certificate=cert, **defaults)


@override_settings(ROOT_URLCONF=URLCONF)
class DetailPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.member = User.objects.create_user("member@certforge.test", "x")
        self.outsider = User.objects.create_user("out@certforge.test", "x")
        self.team_a = Team.objects.create(name="Plataforma")
        self.team_b = Team.objects.create(name="Finanzas")
        Membership.objects.create(user=self.member, team=self.team_a, role=MembershipRole.CONTRIBUTOR)
        self.cert = Certificate.objects.create(
            domain="api.ejemplo.com", port=443, team=self.team_a,
            status=CertificateStatus.VIGENTE, days_left=90,
            issuer="CN=Let's Encrypt",
        )
        self.cert_b = Certificate.objects.create(
            domain="banco.ejemplo.com", port=443, team=self.team_b
        )

    # --- acceso / RBAC -----------------------------------------------------
    def test_requires_authentication(self):
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 302)

    def test_owner_sees_detail(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "api.ejemplo.com")
        self.assertContains(resp, "Volver a certificados")

    def test_member_sees_own_team_cert(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)

    def test_member_cannot_see_foreign_cert(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("cert-detail", args=[self.cert_b.id]))
        self.assertEqual(resp.status_code, 404)

    # --- hero --------------------------------------------------------------
    def test_hero_shows_days_left(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]))
        self.assertContains(resp, "días restantes")

    def test_hero_negative_days_vencido(self):
        self.cert.days_left = -3
        self.cert.status = CertificateStatus.VENCIDO
        self.cert.save()
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]))
        self.assertContains(resp, "días vencido")

    # --- tabs deep-link ----------------------------------------------------
    def test_default_tab_is_resumen(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]))
        self.assertContains(resp, "Identidad")

    def test_deep_link_tecnico_tab(self):
        check = _make_check(self.cert)
        self.cert.last_check = check
        self.cert.save(update_fields=["last_check"])
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]), {"tab": "tecnico"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Detalles técnicos")
        self.assertContains(resp, "sha256WithRSAEncryption")

    def test_invalid_tab_falls_back_to_resumen(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-detail", args=[self.cert.id]), {"tab": "bogus"})
        self.assertContains(resp, "Identidad")

    def test_tab_endpoint_returns_only_panel(self):
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse("cert-detail-tab", args=[self.cert.id, "tecnico"]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Detalles técnicos")
        self.assertNotContains(resp, "<html")


@override_settings(ROOT_URLCONF=URLCONF)
class EmptyStateTests(TestCase):
    """Cada pestaña muestra su propio estado vacío cuando no hay last_check."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.team = Team.objects.create(name="Plataforma")
        self.cert = Certificate.objects.create(
            domain="nuevo.ejemplo.com", port=443, team=self.team,
            status=CertificateStatus.SIN_CHEQUEAR,
        )
        self.client.force_login(self.owner)

    def _panel(self, tab):
        return self.client.get(reverse("cert-detail-tab", args=[self.cert.id, tab]))

    def test_resumen_empty(self):
        resp = self._panel("resumen")
        self.assertContains(resp, "no se ha chequeado todavía")

    def test_tecnico_empty(self):
        resp = self._panel("tecnico")
        self.assertContains(resp, "no se ha chequeado todavía")

    def test_cadena_empty(self):
        resp = self._panel("cadena")
        self.assertContains(resp, "Sin cadena de confianza")
        self.assertContains(resp, "Sin SAN")

    def test_historial_empty(self):
        resp = self._panel("historial")
        self.assertContains(resp, "Sin historial")

    def test_alertas_empty(self):
        resp = self._panel("alertas")
        self.assertContains(resp, "Sin alertas")


@override_settings(ROOT_URLCONF=URLCONF)
class RealDataTests(TestCase):
    """Solo datos reales del último CertificateCheck (nada inventado)."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.team = Team.objects.create(name="Plataforma")
        self.cert = Certificate.objects.create(domain="api.ejemplo.com", port=443, team=self.team)
        self.client.force_login(self.owner)

    def test_tecnico_only_real_fields_no_sha1(self):
        # last_check sin SHA-1 ni versión: el detalle NO los inventa (el kit sí).
        check = _make_check(self.cert, fingerprint_sha256="9F:2A:C1:08:5E")
        self.cert.last_check = check
        self.cert.save(update_fields=["last_check"])
        resp = self.client.get(reverse("cert-detail-tab", args=[self.cert.id, "tecnico"]))
        self.assertContains(resp, "SHA-256")
        self.assertContains(resp, "9F:2A:C1:08:5E")
        # No emite filas SHA-1 ni "Versión" (el mock del kit) porque no hay dato.
        self.assertNotContains(resp, "SHA-1")
        self.assertNotContains(resp, "Versión")

    def test_cadena_uses_real_chain_and_san(self):
        check = _make_check(self.cert, chain=["Root X1", "R3", "Hoja"], san=["a.com", "b.com"])
        self.cert.last_check = check
        self.cert.save(update_fields=["last_check"])
        resp = self.client.get(reverse("cert-detail-tab", args=[self.cert.id, "cadena"]))
        self.assertContains(resp, "Root X1")
        self.assertContains(resp, "a.com")
        self.assertContains(resp, "b.com")

    def test_historial_lists_real_checks(self):
        _make_check(self.cert, days_left=30, checked_at=timezone.now() - timedelta(days=2))
        _make_check(self.cert, days_left=29, checked_at=timezone.now() - timedelta(days=1))
        last = _make_check(self.cert, days_left=28)
        self.cert.last_check = last
        self.cert.save(update_fields=["last_check"])
        resp = self.client.get(reverse("cert-detail-tab", args=[self.cert.id, "historial"]))
        # Tres chequeos reales => mini-tendencia (polyline) presente.
        self.assertContains(resp, "polyline")
        self.assertContains(resp, "días")

    def test_historial_is_sortable_searchable_table(self):
        # La DataTable de Historial usa ForgeDataTable vía el adapter global.
        _make_check(self.cert, days_left=30, checked_at=timezone.now() - timedelta(days=1))
        last = _make_check(self.cert, days_left=28)
        self.cert.last_check = last
        self.cert.save(update_fields=["last_check"])
        resp = self.client.get(reverse("cert-detail-tab", args=[self.cert.id, "historial"]))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, "data-forge-sortable")
        self.assertContains(resp, 'data-page-size="8"')
        self.assertContains(resp, "cf-data-source")


@override_settings(ROOT_URLCONF=URLCONF)
class AlertHistoryTests(TestCase):
    """La pestaña Alertas muestra el histórico completo incl. dismissed."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.team = Team.objects.create(name="Plataforma")
        self.cert = Certificate.objects.create(domain="api.ejemplo.com", port=443, team=self.team)
        self.client.force_login(self.owner)

    def test_dismissed_alert_still_listed_as_archived(self):
        open_alert = Alert.objects.create(
            certificate=self.cert, severity=AlertSeverity.POR_VENCER,
            status=AlertStatus.OPEN, message="Vence pronto api.ejemplo.com",
        )
        dismissed = Alert.objects.create(
            certificate=self.cert, severity=AlertSeverity.CRITICO,
            status=AlertStatus.OPEN, message="Critico api.ejemplo.com",
        )
        AlertUserState.objects.create(
            alert=dismissed, user=self.owner, dismissed_at=timezone.now()
        )
        resp = self.client.get(reverse("cert-detail-tab", args=[self.cert.id, "alertas"]))
        # Ambas alertas aparecen; la limpiada lleva el tag "Archivada".
        self.assertContains(resp, "Vence pronto api.ejemplo.com")
        self.assertContains(resp, "Critico api.ejemplo.com")
        self.assertContains(resp, "Archivada")

    def test_resolved_alert_listed_as_archived(self):
        Alert.objects.create(
            certificate=self.cert, severity=AlertSeverity.VENCIDO,
            status=AlertStatus.RESOLVED, message="Resuelta api.ejemplo.com",
            resolved_at=timezone.now(),
        )
        resp = self.client.get(reverse("cert-detail-tab", args=[self.cert.id, "alertas"]))
        self.assertContains(resp, "Resuelta api.ejemplo.com")
        self.assertContains(resp, "Archivada")


@override_settings(
    ROOT_URLCONF=URLCONF,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="alertas@certforge.test",
)
class NotifyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.member = User.objects.create_user("member@certforge.test", "x")
        self.outsider = User.objects.create_user("out@certforge.test", "x")
        self.team_a = Team.objects.create(name="Plataforma")
        self.team_b = Team.objects.create(name="Finanzas")
        Membership.objects.create(user=self.member, team=self.team_a, role=MembershipRole.CONTRIBUTOR)
        self.cert = Certificate.objects.create(
            domain="api.ejemplo.com", port=443, team=self.team_a,
            status=CertificateStatus.POR_VENCER, days_left=12,
            notify_platform=True, notify_email=True, notify_webhook=False,
        )
        CertificateRecipient.objects.create(
            certificate=self.cert, email="ops@equipo.com"
        )
        self.cert_b = Certificate.objects.create(domain="banco.ejemplo.com", port=443, team=self.team_b)
        org = OrganizationSettings.load()
        org.email_copy_enabled = True
        org.email_copy_address = "sp_canales_electronicos@claro.com.do"
        org.save()

    def test_notify_sends_email_and_records_delivery(self):
        self.client.force_login(self.owner)
        resp = self.client.post(reverse("cert-notify", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Notificación enviada")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ops@equipo.com", mail.outbox[0].to)
        self.assertIn("sp_canales_electronicos@claro.com.do", mail.outbox[0].bcc)
        # Registro auditable: deliveries de plataforma + correo.
        self.assertTrue(
            AlertDelivery.objects.filter(
                alert__certificate=self.cert, status=DeliveryStatus.SENT
            ).exists()
        )

    def test_member_can_notify_own_team_cert(self):
        """RBAC §3 congelado: un Miembro PUEDE notificar certs de su grupo."""
        self.client.force_login(self.member)
        resp = self.client.post(reverse("cert-notify", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Notificación enviada")

    def test_member_cannot_notify_foreign_cert(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse("cert-notify", args=[self.cert_b.id]))
        self.assertEqual(resp.status_code, 404)

    def test_notify_requires_login(self):
        resp = self.client.post(reverse("cert-notify", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 302)

    def test_email_test_sends_only_to_manual_recipient(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("cert-email-test", args=[self.cert.id]),
            {"email": "qa@certforge.test"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Correo de prueba enviado")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["qa@certforge.test"])
        self.assertNotIn("ops@equipo.com", mail.outbox[0].to)
        self.assertIn("sp_canales_electronicos@claro.com.do", mail.outbox[0].bcc)

    def test_email_test_modal_get(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-email-test", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Probar correo")
        self.assertContains(resp, "Esta prueba no usa los responsables reales")

    def test_notify_throttled_after_max(self):
        self.client.force_login(self.owner)
        # NOTIFY_THROTTLE_MAX = 5 envíos por ventana.
        for _ in range(5):
            self.client.post(reverse("cert-notify", args=[self.cert.id]))
        resp = self.client.post(reverse("cert-notify", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 429)
        self.assertContains(resp, "Demasiadas notificaciones", status_code=429)

    def test_notify_without_recipients_warns(self):
        # Cert sin destinatarios ni admins de grupo => aviso, no error.
        bare = Certificate.objects.create(
            domain="solo.ejemplo.com", port=443, team=self.team_a,
            notify_platform=False, notify_email=True, notify_webhook=False,
        )
        self.client.force_login(self.owner)
        resp = self.client.post(reverse("cert-notify", args=[bare.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sin responsables")


@override_settings(ROOT_URLCONF=URLCONF)
class EditTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.member = User.objects.create_user("member@certforge.test", "x")
        self.team_a = Team.objects.create(name="Plataforma")
        self.team_b = Team.objects.create(name="Finanzas")
        Membership.objects.create(user=self.member, team=self.team_a, role=MembershipRole.CONTRIBUTOR)
        self.cert = Certificate.objects.create(
            domain="api.ejemplo.com", port=443, team=self.team_a, alert_threshold_days=30,
        )

    def test_edit_modal_renders_with_instance(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-edit", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Editar certificado")
        self.assertContains(resp, "api.ejemplo.com")

    def test_edit_saves_changes(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("cert-edit", args=[self.cert.id]),
            {
                "domain": "nuevo.ejemplo.com",
                "port": 443,
                "team": self.team_a.id,
                "alert_threshold_days": 60,
                "notify_platform": "on",
                "notify_email": "on",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Certificado actualizado")
        # Refresca tanto el detalle como el listado (evita estado viejo).
        self.assertIn("cf:cert-updated", resp["HX-Trigger"])
        self.assertIn("cf:certs-changed", resp["HX-Trigger"])
        self.cert.refresh_from_db()
        self.assertEqual(self.cert.domain, "nuevo.ejemplo.com")

    def test_edit_invalid_returns_422(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("cert-edit", args=[self.cert.id]),
            {"domain": "", "port": 443, "team": self.team_a.id},
        )
        self.assertEqual(resp.status_code, 422)

    def test_member_cannot_edit_foreign_cert(self):
        foreign = Certificate.objects.create(domain="x.ejemplo.com", port=443, team=self.team_b)
        self.client.force_login(self.member)
        resp = self.client.get(reverse("cert-edit", args=[foreign.id]))
        self.assertEqual(resp.status_code, 404)
