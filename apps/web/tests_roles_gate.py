"""Gating por rol nuevo: Viewer (solo ve) vs Contributor (crea/edita certs)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.certificates.models import Certificate
from apps.core.enums import MembershipRole as R
from apps.mailtemplates.models import EmailTemplate
from apps.teams.models import Membership, Team

U = get_user_model()


class CertRoleGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="G")
        cls.viewer = U.objects.create_user(email="v@x.io", password="pw")
        cls.contrib = U.objects.create_user(email="c@x.io", password="pw")
        Membership.objects.create(user=cls.viewer, team=cls.team, role=R.VIEWER)
        Membership.objects.create(user=cls.contrib, team=cls.team, role=R.CONTRIBUTOR)
        cls.cert = Certificate.objects.create(team=cls.team, domain="a.example.com", port=443)

    def _create_payload(self):
        return {"domain": "new.example.com", "port": 443, "team": self.team.id,
                "alert_threshold_days": 30}

    def test_viewer_list_hides_create(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse("certificate-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Nuevo certificado")

    def test_contributor_list_shows_create(self):
        self.client.force_login(self.contrib)
        resp = self.client.get(reverse("certificate-list"))
        self.assertContains(resp, "Nuevo certificado")

    def test_viewer_cannot_open_create_modal(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("cert-create")).status_code, 403)

    def test_viewer_cannot_post_create(self):
        self.client.force_login(self.viewer)
        resp = self.client.post(reverse("cert-create"), self._create_payload())
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Certificate.objects.filter(domain="new.example.com").exists())

    def test_contributor_can_create(self):
        self.client.force_login(self.contrib)
        resp = self.client.post(reverse("cert-create"), self._create_payload())
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(Certificate.objects.filter(domain="new.example.com").exists())

    def test_viewer_cannot_bulk_delete(self):
        self.client.force_login(self.viewer)
        resp = self.client.post(
            reverse("cert-bulk"),
            {"action": "delete", "ids": [self.cert.id], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Certificate.objects.filter(pk=self.cert.pk).exists())

    def test_viewer_cannot_edit(self):
        self.client.force_login(self.viewer)
        self.assertEqual(
            self.client.get(reverse("cert-edit", args=[self.cert.pk])).status_code, 403
        )

    def test_contributor_can_open_edit(self):
        self.client.force_login(self.contrib)
        self.assertEqual(
            self.client.get(reverse("cert-edit", args=[self.cert.pk])).status_code, 200
        )

    def test_edit_preserves_email_template(self):
        # Regresión: editar el cert NO debe borrar la plantilla de correo asignada.
        tpl = EmailTemplate.objects.create(
            name="t", kind="CERT", subject="s",
            blocks=[{"type": "data", "field": f} for f in ("dominio", "estado", "dias_restantes", "vence_el")],
        )
        self.cert.email_template = tpl
        self.cert.save(update_fields=["email_template"])
        self.client.force_login(self.contrib)
        resp = self.client.post(
            reverse("cert-edit", args=[self.cert.pk]),
            {"domain": self.cert.domain, "port": 443, "team": self.team.id,
             "alert_threshold_days": 30, "email_template": tpl.id},
        )
        self.assertEqual(resp.status_code, 200)
        self.cert.refresh_from_db()
        self.assertEqual(self.cert.email_template_id, tpl.id)
