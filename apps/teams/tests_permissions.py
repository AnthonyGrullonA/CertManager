"""Tests de la matriz de capacidades por rol (apps/teams/permissions.py).

El rol Admin de grupo no existe: la gestión es exclusiva del Owner global.
"""
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
        cls.owner = U.objects.create_user(email="o@x.io", password="x", is_owner=True)
        cls.outsider = U.objects.create_user(email="out@x.io", password="x")
        Membership.objects.create(user=cls.viewer, team=cls.t, role=R.VIEWER)
        Membership.objects.create(user=cls.contrib, team=cls.t, role=R.CONTRIBUTOR)

    def test_roles_are_only_viewer_and_contributor(self):
        self.assertEqual(set(R.values), {"VIEWER", "CONTRIBUTOR"})

    def test_role_in(self):
        self.assertEqual(P.role_in(self.viewer, self.t), R.VIEWER)
        self.assertIsNone(P.role_in(self.outsider, self.t))

    def test_can_view(self):
        for u in (self.viewer, self.contrib, self.owner):
            self.assertTrue(P.can_view(u, self.t))
        self.assertFalse(P.can_view(self.outsider, self.t))

    def test_can_edit_certs(self):
        self.assertFalse(P.can_edit_certs(self.viewer, self.t))
        self.assertTrue(P.can_edit_certs(self.contrib, self.t))
        self.assertTrue(P.can_edit_certs(self.owner, self.t))
        self.assertFalse(P.can_edit_certs(self.outsider, self.t))

    def test_owner_crosses_groups(self):
        # Owner puede en un grupo donde no es miembro.
        self.assertTrue(P.can_edit_certs(self.owner, self.other))
