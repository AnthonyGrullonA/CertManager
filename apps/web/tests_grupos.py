"""Tests de la pantalla Grupos (team-list / team-create).

Usan el ROOT_URLCONF de prueba `apps.web.test_urls_grupos` para resolver tanto
las urls globales (dashboard, logout, certificate-list…) como las propias.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team

User = get_user_model()

URLCONF = "apps.web.test_urls_grupos"


@override_settings(ROOT_URLCONF=URLCONF)
class TeamListTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.member = User.objects.create_user("member@certforge.test", "x")

    def test_requires_authentication(self):
        resp = self.client.get(reverse("team-list"))
        self.assertEqual(resp.status_code, 302)

    def test_empty_state_es_do_copy(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Aún no hay grupos")
        self.assertContains(resp, 'id="grupos-empty"')

    def test_owner_sees_all_groups(self):
        Team.objects.create(name="Plataforma")
        Team.objects.create(name="Finanzas")
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-list"))
        self.assertContains(resp, "Plataforma")
        self.assertContains(resp, "Finanzas")
        self.assertNotContains(resp, "Aún no hay grupos")

    def test_non_owner_sees_only_own_groups(self):
        own = Team.objects.create(name="MiGrupo")
        Team.objects.create(name="OtroGrupo")
        Membership.objects.create(user=self.member, team=own, role=MembershipRole.CONTRIBUTOR)
        self.client.force_login(self.member)
        resp = self.client.get(reverse("team-list"))
        self.assertContains(resp, "MiGrupo")
        self.assertNotContains(resp, "OtroGrupo")

    def test_non_owner_has_no_create_button(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("team-list"))
        # El boton dispara hx-get a team-create; ausente para no-Owner.
        self.assertNotContains(resp, reverse("team-create"))

    def test_pagination_wrapper_present_with_groups(self):
        # Con grupos: la tabla va envuelta en [data-forge-table] con el
        # page size que ForgeDataTable usa en cliente.
        Team.objects.create(name="Plataforma")
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-list"))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, "forge-table-scroll")
        self.assertContains(resp, 'data-page-size="8"')

    def test_no_pager_when_empty(self):
        # Sin grupos: el estado vacío se muestra; ForgeDataTable se inicializa sobre
        # una tabla vacía cuando haya filas.
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-list"))
        self.assertContains(resp, 'id="grupos-empty"')
        self.assertContains(resp, "data-forge-table")

    def test_table_is_sortable_with_no_sort_columns(self):
        # Orden nativo: wrapper con data-forge-sortable y data-no-sort en las
        # columnas no ordenables (Salud, Admin(s) y acciones).
        Team.objects.create(name="Plataforma")
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-list"))
        self.assertContains(resp, "data-forge-sortable")
        # Tres columnas no ordenables: Salud, Admin(s), acciones.
        self.assertEqual(resp.content.decode().count("data-no-sort"), 3)

    def test_native_search_present_with_groups(self):
        # ForgeDataTable genera el buscador en cliente.
        Team.objects.create(name="Plataforma")
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-list"))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, 'data-page-size="8"')

    def test_no_native_search_when_empty(self):
        # Sin grupos no hay buscador (no tiene filas que filtrar).
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-list"))
        self.assertNotContains(resp, "data-forge-search")


@override_settings(ROOT_URLCONF=URLCONF)
class TeamCreateTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.admin_user = User.objects.create_user("admin@certforge.test", "x")
        self.member = User.objects.create_user("member@certforge.test", "x")

    def test_owner_gets_modal(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("team-create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Nuevo grupo")
        self.assertContains(resp, "Frecuencia")  # default_check_interval

    def test_non_owner_cannot_open_modal(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("team-create"))
        self.assertEqual(resp.status_code, 403)

    def test_create_via_modal_returns_200_and_new_row(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("team-create"),
            {
                "name": "Plataforma",
                "description": "Equipo de plataforma",
                "default_threshold_days": 30,
                "default_check_interval": 6,
                "admin": self.admin_user.id,
                "default_email": "plataforma@certforge.test",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # Fila nueva (OOB) presente.
        self.assertContains(resp, "Plataforma")
        self.assertContains(resp, 'id="team-rows"')
        self.assertContains(resp, 'hx-swap-oob="beforeend"')
        # Grupo persistido con sus defaults.
        team = Team.objects.get(name="Plataforma")
        self.assertEqual(team.default_check_interval, 6)
        self.assertEqual(team.default_threshold_days, 30)
        self.assertEqual(team.default_recipients, ["plataforma@certforge.test"])
        self.assertEqual(team.created_by, self.owner)
        # Admin asignado como Membership ADMIN.
        m = Membership.objects.get(team=team, user=self.admin_user)
        self.assertEqual(m.role, MembershipRole.ADMIN)

    def test_create_without_admin_is_allowed(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("team-create"),
            {
                "name": "SinAdmin",
                "default_threshold_days": 45,
                "default_check_interval": 24,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Team.objects.filter(name="SinAdmin").exists())
        self.assertFalse(Membership.objects.filter(team__name="SinAdmin").exists())

    def test_non_owner_cannot_create(self):
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse("team-create"),
            {"name": "Hack", "default_threshold_days": 45, "default_check_interval": 24},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Team.objects.filter(name="Hack").exists())

    def test_invalid_form_returns_422_and_no_team(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("team-create"),
            {"name": "", "default_threshold_days": 45, "default_check_interval": 24},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(Team.objects.count(), 0)
        self.assertContains(resp, "Nuevo grupo", status_code=422)
