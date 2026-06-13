"""Tests de fidelidad de UI de la pantalla Usuarios (overhaul espejo Usuarios.jsx).

Usan el urlconf real (config.urls) vía reverse() y el Client directo, sin
test_urls ni ROOT_URLCONF de prueba. Verifican que el markup quedó acorde al
diseño del kit (avatar+nombre+correo, chips de rol, punto de estado, menú de
acciones, búsqueda y modal de invitar) y que RBAC/anti mass-assignment siguen
intactos.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team

User = get_user_model()
PWD = "usuarios-ui-2026"


class UsuariosUiFidelityTests(TestCase):
    """El markup de la pantalla refleja el diseño del kit."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Plataforma")
        cls.owner = User.objects.create_user(
            email="owner@certforge.test",
            password=PWD,
            first_name="María",
            last_name="Reyes",
            is_owner=True,
        )
        cls.member = User.objects.create_user(
            email="jose@certforge.test",
            password=PWD,
            first_name="José",
            last_name="Cabrera",
        )
        Membership.objects.create(
            user=cls.member, team=cls.team, role=MembershipRole.CONTRIBUTOR
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_pageheader_present(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "forge-usuarios__title")
        self.assertContains(resp, "Gestiona personas, roles y pertenencia a grupos")

    def test_table_uses_avatar_and_userline(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "forge-userline")
        self.assertContains(resp, "forge-avatar")  # partial _avatar
        self.assertContains(resp, "forge-userline__mail")

    def test_role_chip_uses_forge_tag(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "forge-tag forge-tag--brand")  # Owner
        self.assertContains(resp, "Owner")
        # El chip refleja el rol de grupo real (member es CONTRIBUTOR).
        self.assertContains(resp, "Colaborador")

    def test_status_dot_rendered(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "forge-status-dot")
        self.assertContains(resp, "Activo")

    def test_row_actions_menu_present(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "forge-rowmenu")
        self.assertContains(resp, "Desactivar")
        self.assertContains(resp, "Editar")

    def test_edit_link_wired_to_user_edit(self):
        # BUG fix: el botón Editar abre el modal de edición (no apunta a la
        # propia lista) vía HTMX hacia #modal-root.
        resp = self.client.get(reverse("user-list"))
        edit_url = reverse("user-edit", args=[self.member.pk])
        self.assertContains(resp, 'hx-get="%s"' % edit_url)

    def test_table_is_paginated(self):
        # La tabla está envuelta para ForgeDataTable.
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, 'data-page-size="8"')
        # La fila de estado vacío se marca para que el paginación la ignore.
        empty = self.client.get(reverse("user-list"), {"q": "nadie-zzz"})
        self.assertContains(empty, "data-empty-row")

    def test_search_input_present(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, 'name="q"')
        self.assertContains(resp, "forge-search__input")

    def test_invite_button_targets_modal_root(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, 'hx-target="#modal-root"')
        self.assertContains(resp, "Crear usuario")

    def test_scoped_styles_block_present(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, 'class="cf-data-source"')
        self.assertContains(resp, ".forge-ubtn--primary")

    def test_no_visible_block_comment_leak(self):
        # Guardia contra el bug de {# multilínea #}: el contenido de los bloques
        # {% comment %} no debe filtrarse al HTML renderizado.
        resp = self.client.get(reverse("user-list"))
        self.assertNotContains(resp, "búsqueda en vivo (HTMX) y modal")


class UsuariosUiInviteModalTests(TestCase):
    """El modal de alta usa forge-modal + campos forge-uform del kit."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Marketing")
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password=PWD, is_owner=True
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_modal_markup(self):
        resp = self.client.get(reverse("user-invite"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "forge-modal__panel")
        self.assertContains(resp, "forge-uform")
        self.assertContains(resp, "Crear usuario")
        self.assertContains(resp, "Autenticar por LDAP")

    def test_modal_has_no_global_role_field(self):
        # Anti mass-assignment: el modal jamás ofrece is_owner/is_staff.
        resp = self.client.get(reverse("user-invite"))
        self.assertNotContains(resp, 'name="is_owner"')
        self.assertNotContains(resp, 'name="is_staff"')


class UsuariosUiRbacTests(TestCase):
    """RBAC intacto contra el urlconf real: solo Owner."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password=PWD, is_owner=True
        )
        cls.member = User.objects.create_user(
            email="member@certforge.test", password=PWD
        )

    def test_member_gets_403_on_list(self):
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("user-list")).status_code, 403
        )

    def test_member_gets_403_on_invite(self):
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("user-invite")).status_code, 403
        )

    def test_owner_ok(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(reverse("user-list")).status_code, 200
        )
