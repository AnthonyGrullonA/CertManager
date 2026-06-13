"""El rol mostrado en las cards/filas de Usuarios refleja los roles reales.

Bug: el chip "rol global" leía ``is_staff``, que esta app nunca asigna
(migración 0007 lo limpia; los forms lo excluyen por anti-escalada), así que
todo no-Owner salía "Miembro". El chip deriva del rol de membresía más alto:
Owner > Colaborador > Visualizador > Miembro (sin grupos).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team

User = get_user_model()


class GroupRolePropertyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u@certforge.test", "x")
        self.team_a = Team.objects.create(name="A")
        self.team_b = Team.objects.create(name="B")

    def test_none_without_memberships(self):
        self.assertIsNone(self.user.group_role)

    def test_contributor_beats_viewer(self):
        Membership.objects.create(
            user=self.user, team=self.team_a, role=MembershipRole.CONTRIBUTOR
        )
        Membership.objects.create(
            user=self.user, team=self.team_b, role=MembershipRole.VIEWER
        )
        self.assertEqual(self.user.group_role, MembershipRole.CONTRIBUTOR)


class RoleChipInUsuariosTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "owner@certforge.test", "x", is_owner=True
        )
        self.team = Team.objects.create(name="Plataforma")
        self.client.force_login(self.owner)

    def _row_html(self):
        return self.client.get(reverse("user-list")).content.decode()

    def test_contributor_shows_colaborador(self):
        user = User.objects.create_user("colab@certforge.test", "x")
        Membership.objects.create(
            user=user, team=self.team, role=MembershipRole.CONTRIBUTOR
        )
        self.assertIn("Colaborador", self._row_html())

    def test_viewer_shows_visualizador(self):
        user = User.objects.create_user("viewer@certforge.test", "x")
        Membership.objects.create(
            user=user, team=self.team, role=MembershipRole.VIEWER
        )
        self.assertIn("Visualizador", self._row_html())

    def test_no_groups_shows_miembro(self):
        User.objects.create_user("solo@certforge.test", "x")
        self.assertIn("Miembro", self._row_html())

    def test_detail_card_shows_group_role(self):
        user = User.objects.create_user("colab2@certforge.test", "x")
        Membership.objects.create(
            user=user, team=self.team, role=MembershipRole.CONTRIBUTOR
        )
        resp = self.client.get(reverse("user-detail", args=[user.pk]))
        self.assertContains(resp, "Colaborador")
