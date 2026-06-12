"""Tests de las vistas de detalle de grupo y de usuario (PASO posterior).

Cubre:
- Detalle de grupo visible para miembros + Owner; 404 para ajenos.
- Gestión de miembros (agregar/rol/quitar) solo Owner o Admin del grupo; 403 si no.
- Detalle de usuario solo-Owner (403 para no-Owner).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team

User = get_user_model()
PWD = "x"


class GroupDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Plataforma")
        cls.other = Team.objects.create(name="Otro")
        cls.owner = User.objects.create_user("owner@x.test", PWD, is_owner=True)
        cls.admin = User.objects.create_user("admin@x.test", PWD)
        cls.viewer = User.objects.create_user("viewer@x.test", PWD)
        cls.outsider = User.objects.create_user("out@x.test", PWD)
        cls.newbie = User.objects.create_user("newbie@x.test", PWD)
        Membership.objects.create(user=cls.admin, team=cls.team, role=MembershipRole.ADMIN)
        Membership.objects.create(user=cls.viewer, team=cls.team, role=MembershipRole.VIEWER)

    def test_member_can_view_detail(self):
        self.client.force_login(self.viewer)
        r = self.client.get(reverse("team-detail", kwargs={"pk": self.team.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Miembros")

    def test_outsider_gets_404(self):
        self.client.force_login(self.outsider)
        r = self.client.get(reverse("team-detail", kwargs={"pk": self.team.pk}))
        self.assertEqual(r.status_code, 404)

    def test_owner_can_view_any_group(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("team-detail", kwargs={"pk": self.other.pk}))
        self.assertEqual(r.status_code, 200)

    def test_admin_can_add_member(self):
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse("team-member-add", kwargs={"pk": self.team.pk}),
            {"user": self.newbie.pk, "role": MembershipRole.CONTRIBUTOR},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            Membership.objects.filter(
                user=self.newbie, team=self.team, role=MembershipRole.CONTRIBUTOR
            ).exists()
        )

    def test_viewer_cannot_manage(self):
        self.client.force_login(self.viewer)
        r = self.client.post(
            reverse("team-member-add", kwargs={"pk": self.team.pk}),
            {"user": self.newbie.pk, "role": MembershipRole.VIEWER},
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(
            Membership.objects.filter(user=self.newbie, team=self.team).exists()
        )

    def test_owner_change_role_and_remove(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("team-member-role", kwargs={"pk": self.team.pk, "user_id": self.viewer.pk}),
            {"role": MembershipRole.ADMIN},
        )
        self.assertEqual(
            Membership.objects.get(user=self.viewer, team=self.team).role,
            MembershipRole.ADMIN,
        )
        self.client.post(
            reverse("team-member-remove", kwargs={"pk": self.team.pk, "user_id": self.viewer.pk})
        )
        self.assertFalse(
            Membership.objects.filter(user=self.viewer, team=self.team).exists()
        )


class GroupEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Plataforma")
        cls.owner = User.objects.create_user("owner@x.test", PWD, is_owner=True)
        cls.admin = User.objects.create_user("admin@x.test", PWD)
        cls.viewer = User.objects.create_user("viewer@x.test", PWD)
        Membership.objects.create(user=cls.admin, team=cls.team, role=MembershipRole.ADMIN)
        Membership.objects.create(user=cls.viewer, team=cls.team, role=MembershipRole.VIEWER)

    def _post(self):
        return {
            "name": "Plataforma X", "description": "nueva",
            "default_threshold_days": "30", "default_check_interval": "12",
            "default_email": "ops@x.test",
        }

    def test_admin_can_edit(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("team-edit", kwargs={"pk": self.team.pk}), self._post())
        self.assertEqual(r.status_code, 200)
        self.assertIn("cf:team-updated", r["HX-Trigger"])
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Plataforma X")
        self.assertEqual(self.team.default_recipients, ["ops@x.test"])

    def test_viewer_cannot_edit(self):
        self.client.force_login(self.viewer)
        r = self.client.post(reverse("team-edit", kwargs={"pk": self.team.pk}), self._post())
        self.assertEqual(r.status_code, 403)


class UserDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("owner@x.test", PWD, is_owner=True)
        cls.member = User.objects.create_user("member@x.test", PWD)

    def test_owner_can_view(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("user-detail", kwargs={"pk": self.member.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Grupos y roles")

    def test_non_owner_forbidden(self):
        self.client.force_login(self.member)
        r = self.client.get(reverse("user-detail", kwargs={"pk": self.owner.pk}))
        self.assertEqual(r.status_code, 403)
