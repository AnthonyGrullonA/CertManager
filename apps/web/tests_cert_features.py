"""Activar/pausar monitoreo (toggle is_active) y validación de dominio duplicado
entre grupos (con info para reactivar el existente)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.certificates.forms import CertificateForm
from apps.certificates.models import Certificate
from apps.core.enums import MembershipRole as R
from apps.teams.models import Membership, Team

U = get_user_model()


class ToggleMonitoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="G")
        cls.contrib = U.objects.create_user(email="c@x.io", password="pw")
        cls.viewer = U.objects.create_user(email="v@x.io", password="pw")
        Membership.objects.create(user=cls.contrib, team=cls.team, role=R.CONTRIBUTOR)
        Membership.objects.create(user=cls.viewer, team=cls.team, role=R.VIEWER)
        cls.cert = Certificate.objects.create(team=cls.team, domain="a.example.com", port=443, is_active=True)

    def test_contributor_can_pause_and_resume(self):
        self.client.force_login(self.contrib)
        r1 = self.client.post(reverse("cert-toggle-active", args=[self.cert.pk]))
        self.assertEqual(r1.status_code, 200)
        self.cert.refresh_from_db()
        self.assertFalse(self.cert.is_active)
        self.client.post(reverse("cert-toggle-active", args=[self.cert.pk]))
        self.cert.refresh_from_db()
        self.assertTrue(self.cert.is_active)

    def test_viewer_cannot_toggle(self):
        self.client.force_login(self.viewer)
        r = self.client.post(reverse("cert-toggle-active", args=[self.cert.pk]))
        self.assertEqual(r.status_code, 403)
        self.cert.refresh_from_db()
        self.assertTrue(self.cert.is_active)


class DuplicateDomainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.A = Team.objects.create(name="Infra")
        cls.B = Team.objects.create(name="Apps")
        cls.user = U.objects.create_user(email="u@x.io", password="pw")
        Membership.objects.create(user=cls.user, team=cls.A, role=R.CONTRIBUTOR)
        Membership.objects.create(user=cls.user, team=cls.B, role=R.CONTRIBUTOR)
        cls.existing = Certificate.objects.create(team=cls.A, domain="dup.example.com", port=443)

    def _form(self, **over):
        data = {"domain": "dup.example.com", "port": 443, "team": self.B.id, "alert_threshold_days": 30}
        data.update(over)
        return CertificateForm(data, user=self.user)

    def test_cross_group_duplicate_blocked_with_groups(self):
        form = self._form()
        self.assertFalse(form.is_valid())
        self.assertIn("domain", form.errors)
        self.assertTrue(any("ya está agregado" in e for e in form.errors["domain"]))
        self.assertTrue(any("Infra" in e for e in form.errors["domain"]))
        self.assertEqual(len(form.duplicate_info), 1)
        self.assertEqual(form.duplicate_info[0]["id"], self.existing.pk)

    def test_different_domain_ok(self):
        form = self._form(domain="nuevo.example.com")
        self.assertTrue(form.is_valid(), form.errors)

    def test_different_port_not_duplicate(self):
        form = self._form(port=8443)
        self.assertTrue(form.is_valid(), form.errors)

    def test_duplicate_info_flags_inactive(self):
        self.existing.is_active = False
        self.existing.save(update_fields=["is_active"])
        form = self._form()
        self.assertFalse(form.is_valid())
        self.assertFalse(form.duplicate_info[0]["is_active"])
        self.assertTrue(form.duplicate_info[0]["editable"])
