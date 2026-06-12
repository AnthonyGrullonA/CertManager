"""Backend de plantillas: obligatorios/clean, usable, permisos y render."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.enums import MembershipRole as R
from apps.mailtemplates.models import EmailTemplate
from apps.mailtemplates.permissions import can_edit_template
from apps.mailtemplates.render import render_email, substitute
from apps.mailtemplates.variables import mandatory_fields
from apps.teams.models import Membership, Team

U = get_user_model()

CERT_DATA_BLOCKS = [
    {"type": "data", "field": "dominio"},
    {"type": "data", "field": "estado"},
    {"type": "data", "field": "dias_restantes"},
    {"type": "data", "field": "vence_el"},
]


class MandatoryTests(TestCase):
    def test_mandatory_sets(self):
        self.assertEqual(
            mandatory_fields("CERT"), {"dominio", "estado", "dias_restantes", "vence_el"}
        )
        self.assertEqual(
            mandatory_fields("REPORT"),
            {"nombre_reporte", "total", "resumen_kpis", "alcance", "generado_el"},
        )

    def test_clean_rejects_missing_mandatory(self):
        tpl = EmailTemplate(name="x", kind="CERT", subject="{{dominio}}", blocks=[])
        with self.assertRaises(ValidationError):
            tpl.full_clean(exclude=["created_by", "team"])

    def test_clean_passes_with_mandatory(self):
        tpl = EmailTemplate(name="x", kind="CERT", subject="{{dominio}}", blocks=CERT_DATA_BLOCKS)
        # No debe lanzar por 'blocks' (puede faltar otro campo no relacionado).
        try:
            tpl.full_clean(exclude=["created_by", "team"])
        except ValidationError as exc:
            self.assertNotIn("blocks", exc.message_dict)


class UsableAndDefaultTests(TestCase):
    def setUp(self):
        # Aísla de las plantillas sembradas (migración 0002) para contar exacto.
        EmailTemplate.objects.all().delete()

    def test_usable_filters_active_and_kind(self):
        EmailTemplate.objects.create(name="a", kind="CERT", subject="s", blocks=CERT_DATA_BLOCKS)
        EmailTemplate.objects.create(
            name="b", kind="CERT", subject="s", blocks=CERT_DATA_BLOCKS, is_active=False
        )
        self.assertEqual(EmailTemplate.objects.usable(kind="CERT").count(), 1)
        self.assertEqual(EmailTemplate.objects.usable(kind="REPORT").count(), 0)

    def test_single_default_per_kind(self):
        a = EmailTemplate.objects.create(
            name="a", kind="CERT", subject="s", blocks=CERT_DATA_BLOCKS, is_default=True
        )
        b = EmailTemplate.objects.create(
            name="b", kind="CERT", subject="s", blocks=CERT_DATA_BLOCKS, is_default=True
        )
        a.refresh_from_db()
        self.assertFalse(a.is_default)
        self.assertTrue(b.is_default)


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="G")
        cls.owner = U.objects.create_user(email="o@x.io", password="x", is_owner=True)
        cls.admin = U.objects.create_user(email="a@x.io", password="x")
        cls.viewer = U.objects.create_user(email="v@x.io", password="x")
        cls.creator = U.objects.create_user(email="c@x.io", password="x")
        Membership.objects.create(user=cls.admin, team=cls.team, role=R.ADMIN)
        Membership.objects.create(user=cls.viewer, team=cls.team, role=R.VIEWER)
        Membership.objects.create(user=cls.creator, team=cls.team, role=R.VIEWER)
        cls.tpl = EmailTemplate.objects.create(
            name="t", kind="CERT", subject="s", blocks=CERT_DATA_BLOCKS, created_by=cls.creator
        )

    def test_owner_and_admin_can_edit(self):
        self.assertTrue(can_edit_template(self.owner, self.tpl))
        self.assertTrue(can_edit_template(self.admin, self.tpl))

    def test_creator_can_edit_even_if_viewer(self):
        self.assertTrue(can_edit_template(self.creator, self.tpl))

    def test_other_viewer_cannot_edit(self):
        self.assertFalse(can_edit_template(self.viewer, self.tpl))


class RenderTests(TestCase):
    def test_substitute(self):
        self.assertEqual(substitute("Hola {{dominio}}", {"dominio": "a.io"}), "Hola a.io")
        self.assertEqual(substitute("x {{nope}}", {}), "x ")

    def test_render_none_returns_none(self):
        self.assertIsNone(render_email(None, {"dominio": "a.io"}))

    def test_render_subject_and_blocks(self):
        tpl = EmailTemplate.objects.create(
            name="t", kind="CERT", subject="{{dominio}} — {{estado}}",
            blocks=[{"type": "text", "props": {"text": "Vence en {{dias_restantes}} días"}},
                    *CERT_DATA_BLOCKS],
        )
        ctx = {"dominio": "a.io", "estado": "Vigente", "dias_restantes": "10", "vence_el": "2026-12-01"}
        out = render_email(tpl, ctx)
        self.assertEqual(out.subject, "a.io — Vigente")
        self.assertIn("Vence en 10 días", out.text)
        self.assertIn("<", out.html)
        self.assertIn("a.io", out.html)
