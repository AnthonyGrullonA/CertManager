"""Tests de la matriz de capacidades por rol (apps/teams/permissions.py)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.enums import MembershipRole as R
from apps.teams import permissions as P
from apps.teams.models import Membership, Team

U = get_user_model()


class CapabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t = Team.objects.create(name="G1")
        cls.other = Team.objects.create(name="G2")
        cls.viewer = U.objects.create_user(email="v@x.io", password="x")
        cls.contrib = U.objects.create_user(email="c@x.io", password="x")
        cls.admin = U.objects.create_user(email="a@x.io", password="x")
        cls.owner = U.objects.create_user(email="o@x.io", password="x", is_owner=True)
        cls.outsider = U.objects.create_user(email="out@x.io", password="x")
        Membership.objects.create(user=cls.viewer, team=cls.t, role=R.VIEWER)
        Membership.objects.create(user=cls.contrib, team=cls.t, role=R.CONTRIBUTOR)
        Membership.objects.create(user=cls.admin, team=cls.t, role=R.ADMIN)

    def test_role_in(self):
        self.assertEqual(P.role_in(self.viewer, self.t), R.VIEWER)
        self.assertIsNone(P.role_in(self.outsider, self.t))

    def test_can_view(self):
        for u in (self.viewer, self.contrib, self.admin, self.owner):
            self.assertTrue(P.can_view(u, self.t))
        self.assertFalse(P.can_view(self.outsider, self.t))

    def test_can_edit_certs(self):
        self.assertFalse(P.can_edit_certs(self.viewer, self.t))
        self.assertTrue(P.can_edit_certs(self.contrib, self.t))
        self.assertTrue(P.can_edit_certs(self.admin, self.t))
        self.assertTrue(P.can_edit_certs(self.owner, self.t))
        self.assertFalse(P.can_edit_certs(self.outsider, self.t))

    def test_is_team_admin(self):
        self.assertFalse(P.is_team_admin(self.viewer, self.t))
        self.assertFalse(P.is_team_admin(self.contrib, self.t))
        self.assertTrue(P.is_team_admin(self.admin, self.t))
        self.assertTrue(P.is_team_admin(self.owner, self.t))

    def test_is_admin_anywhere(self):
        self.assertTrue(P.is_admin_anywhere(self.admin))
        self.assertTrue(P.is_admin_anywhere(self.owner))
        self.assertFalse(P.is_admin_anywhere(self.viewer))
        self.assertFalse(P.is_admin_anywhere(self.contrib))

    def test_owner_crosses_groups(self):
        # Owner puede en un grupo donde no es miembro.
        self.assertTrue(P.can_edit_certs(self.owner, self.other))
        self.assertTrue(P.is_team_admin(self.owner, self.other))
