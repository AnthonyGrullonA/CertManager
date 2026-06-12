"""Certificados multi-grupo (aditivo): visibilidad por dueño O grupos adicionales,
sin duplicados, y gestión desde cualquier grupo del cert."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.certificates.models import Certificate
from apps.core.enums import MembershipRole as R
from apps.teams.models import Membership, Team
from apps.teams.permissions import can_edit_certificate

U = get_user_model()


class MultiGroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.A = Team.objects.create(name="A")
        cls.B = Team.objects.create(name="B")
        cls.C = Team.objects.create(name="C")
        cls.cert = Certificate.objects.create(team=cls.A, domain="x.example.com", port=443)
        cls.cert.groups.add(cls.B)

        cls.owner_member = U.objects.create_user(email="oa@x.io", password="x")  # viewer en A
        cls.extra_member = U.objects.create_user(email="eb@x.io", password="x")  # viewer en B
        cls.outsider = U.objects.create_user(email="oc@x.io", password="x")      # solo C
        cls.both = U.objects.create_user(email="ab@x.io", password="x")          # A y B
        cls.contrib_b = U.objects.create_user(email="cb@x.io", password="x")     # contributor en B
        Membership.objects.create(user=cls.owner_member, team=cls.A, role=R.VIEWER)
        Membership.objects.create(user=cls.extra_member, team=cls.B, role=R.VIEWER)
        Membership.objects.create(user=cls.outsider, team=cls.C, role=R.VIEWER)
        Membership.objects.create(user=cls.both, team=cls.A, role=R.VIEWER)
        Membership.objects.create(user=cls.both, team=cls.B, role=R.VIEWER)
        Membership.objects.create(user=cls.contrib_b, team=cls.B, role=R.CONTRIBUTOR)

    def _visible(self, user):
        return Certificate.objects.for_user(user).filter(pk=self.cert.pk).exists()

    def test_visible_to_owner_group_member(self):
        self.assertTrue(self._visible(self.owner_member))

    def test_visible_to_additional_group_member(self):
        self.assertTrue(self._visible(self.extra_member))

    def test_not_visible_to_outsider(self):
        self.assertFalse(self._visible(self.outsider))

    def test_no_duplicates_for_member_of_both(self):
        qs = Certificate.objects.for_user(self.both).filter(pk=self.cert.pk)
        self.assertEqual(qs.count(), 1)

    def test_viewer_in_additional_group_cannot_edit(self):
        self.assertFalse(can_edit_certificate(self.extra_member, self.cert))

    def test_contributor_in_additional_group_can_edit(self):
        self.assertTrue(can_edit_certificate(self.contrib_b, self.cert))

    def test_unique_constraint_unchanged(self):
        # La unicidad sigue siendo por (team dueño, domain, port).
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Certificate.objects.create(team=self.A, domain="x.example.com", port=443)


class CertFormGroupsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.A = Team.objects.create(name="A")
        cls.B = Team.objects.create(name="B")
        cls.user = U.objects.create_user(email="u@x.io", password="x")
        Membership.objects.create(user=cls.user, team=cls.A, role=R.CONTRIBUTOR)
        Membership.objects.create(user=cls.user, team=cls.B, role=R.CONTRIBUTOR)

    def test_bulk_add_group(self):
        from apps.certificates.models import Certificate
        cert = Certificate.objects.create(team=self.A, domain="z.example.com", port=443)
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("cert-bulk"),
            {"action": "add_group", "team": self.B.id, "ids": [cert.id]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.B.id, list(cert.groups.values_list("id", flat=True)))

    def test_form_saves_additional_groups(self):
        from apps.certificates.forms import CertificateForm
        form = CertificateForm(
            {"domain": "n.example.com", "port": 443, "team": self.A.id,
             "alert_threshold_days": 30, "groups": [self.B.id]},
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        cert = form.save()
        self.assertEqual(cert.team_id, self.A.id)
        self.assertEqual(list(cert.groups.values_list("id", flat=True)), [self.B.id])
