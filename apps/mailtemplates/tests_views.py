"""Vistas del módulo de plantillas: uso global, creación, gating de edición, preview."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.enums import MembershipRole as R
from apps.mailtemplates.models import EmailTemplate
from apps.teams.models import Membership, Team

U = get_user_model()

CERT_BLOCKS = [
    {"type": "data", "field": "dominio"},
    {"type": "data", "field": "estado"},
    {"type": "data", "field": "dias_restantes"},
    {"type": "data", "field": "vence_el"},
]


class MailTemplateViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="G")
        cls.viewer = U.objects.create_user(email="v@x.io", password="pw")
        cls.admin = U.objects.create_user(email="a@x.io", password="pw")
        Membership.objects.create(user=cls.viewer, team=cls.team, role=R.VIEWER)
        Membership.objects.create(user=cls.admin, team=cls.team, role=R.ADMIN)
        cls.tpl = EmailTemplate.objects.create(
            name="t", kind="CERT", subject="s", blocks=CERT_BLOCKS, created_by=cls.admin
        )

    def _payload(self, **over):
        data = {
            "name": "Nueva", "kind": "CERT", "subject": "{{dominio}}",
            "blocks_json": json.dumps(CERT_BLOCKS), "is_active": "on",
        }
        data.update(over)
        return data

    def test_list_visible_to_any_authenticated(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse("mailtemplate-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Plantillas de correo")

    def test_viewer_can_create(self):
        self.client.force_login(self.viewer)
        resp = self.client.post(reverse("mailtemplate-create"), self._payload())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(EmailTemplate.objects.filter(name="Nueva", created_by=self.viewer).exists())

    def test_create_missing_mandatory_rejected(self):
        self.client.force_login(self.viewer)
        resp = self.client.post(
            reverse("mailtemplate-create"),
            self._payload(blocks_json=json.dumps([{"type": "data", "field": "dominio"}])),
        )
        self.assertEqual(resp.status_code, 422)
        self.assertFalse(EmailTemplate.objects.filter(name="Nueva").exists())

    def test_viewer_cannot_edit_others_template(self):
        self.client.force_login(self.viewer)
        self.assertEqual(
            self.client.get(reverse("mailtemplate-edit", args=[self.tpl.pk])).status_code, 403
        )

    def test_admin_can_edit(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("mailtemplate-edit", args=[self.tpl.pk])).status_code, 200
        )

    def test_creator_can_edit_even_if_viewer(self):
        # El creador (admin aquí) edita; probamos también que un viewer-creador puede.
        t2 = EmailTemplate.objects.create(
            name="propia", kind="CERT", subject="s", blocks=CERT_BLOCKS, created_by=self.viewer
        )
        self.client.force_login(self.viewer)
        self.assertEqual(
            self.client.get(reverse("mailtemplate-edit", args=[t2.pk])).status_code, 200
        )

    def test_preview_renders(self):
        self.client.force_login(self.viewer)
        resp = self.client.post(
            reverse("mailtemplate-preview"),
            {"kind": "CERT", "subject": "{{dominio}}", "blocks_json": json.dumps(CERT_BLOCKS)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Vista previa")

    def test_viewer_cannot_delete_others_template(self):
        self.client.force_login(self.viewer)
        resp = self.client.post(reverse("mailtemplate-delete", args=[self.tpl.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(EmailTemplate.objects.filter(pk=self.tpl.pk).exists())

    def test_creator_can_delete_own_template(self):
        own = EmailTemplate.objects.create(
            name="mía", kind="CERT", subject="s", blocks=CERT_BLOCKS, created_by=self.viewer
        )
        self.client.force_login(self.viewer)
        resp = self.client.post(reverse("mailtemplate-delete", args=[own.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(EmailTemplate.objects.filter(pk=own.pk).exists())
