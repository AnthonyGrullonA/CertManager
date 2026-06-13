"""Identidad sin duplicados en cards y filas.

Cuando el usuario no tiene nombre, ``get_full_name|default:email`` producía
"correo · correo" en el select de agregar miembro y línea-nombre + línea-correo
idénticas en las filas. Regla: sin nombre, el correo se muestra UNA sola vez.
"""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team

User = get_user_model()


@override_settings(ROOT_URLCONF="apps.web.test_urls_grupos")
class MembersCardIdentityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "owner@certforge.test", "x", is_owner=True
        )
        self.team = Team.objects.create(name="Plataforma")
        self.client.force_login(self.owner)

    def test_add_member_option_does_not_duplicate_email(self):
        User.objects.create_user("sinnombre@certforge.test", "x")
        resp = self.client.get(reverse("team-detail", args=[self.team.pk]))
        self.assertNotContains(
            resp, "sinnombre@certforge.test · sinnombre@certforge.test"
        )
        self.assertContains(resp, "sinnombre@certforge.test")

    def test_add_member_option_keeps_name_dot_email(self):
        User.objects.create_user(
            "maria@certforge.test", "x", first_name="María", last_name="Reyes"
        )
        resp = self.client.get(reverse("team-detail", args=[self.team.pk]))
        self.assertContains(resp, "María Reyes · maria@certforge.test")

    def test_member_row_does_not_duplicate_email(self):
        nameless = User.objects.create_user("plano@certforge.test", "x")
        Membership.objects.create(
            user=nameless, team=self.team, role=MembershipRole.VIEWER
        )
        html = self.client.get(
            reverse("team-detail", args=[self.team.pk])
        ).content.decode()
        # Sin nombre: NO debe existir el enlace con el correo seguido de la
        # línea mono con el mismo correo.
        self.assertNotRegex(
            html, r">plano@certforge\.test</a>\s*<div[^>]*>plano@certforge\.test<"
        )

    def test_member_row_with_name_keeps_both_lines(self):
        named = User.objects.create_user(
            "test@certforge.test", "x", first_name="Test", last_name="Test"
        )
        Membership.objects.create(
            user=named, team=self.team, role=MembershipRole.VIEWER
        )
        html = self.client.get(
            reverse("team-detail", args=[self.team.pk])
        ).content.decode()
        self.assertRegex(
            html, r">Test Test</a>\s*<div[^>]*>test@certforge\.test<"
        )


class UsuariosRowIdentityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "owner@certforge.test", "x", is_owner=True
        )
        self.client.force_login(self.owner)

    def test_nameless_row_shows_email_once(self):
        User.objects.create_user("solo@certforge.test", "x")
        resp = self.client.get(reverse("user-list"))
        self.assertNotContains(
            resp, 'forge-userline__mail">solo@certforge.test'
        )
        self.assertContains(resp, "solo@certforge.test")

    def test_named_row_keeps_mail_line(self):
        User.objects.create_user(
            "ana@certforge.test", "x", first_name="Ana", last_name="Mota"
        )
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, 'forge-userline__mail">ana@certforge.test')
