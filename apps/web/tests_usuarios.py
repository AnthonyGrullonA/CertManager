"""Tests de la pantalla Usuarios (PASO 10, solo Owner).

Usan ROOT_URLCONF de prueba (test_urls_usuarios) para resolver tanto las urls
globales como las de Usuarios sin tocar las urls compartidas.

DoD cubierto:
- no-Owner: acceso directo -> 403 (item ya oculto en sidebar por is_owner).
- estado vacío sin resultados.
- crear -> 200 y crea usuario.
- mini-matriz RBAC: Owner ok, Admin/Miembro 403.
- anti mass-assignment de is_owner desde el form de invitación.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team
from apps.accounts.models import get_or_create_preferences

User = get_user_model()

PWD = "usuarios-2026"
TEST_URLCONF = "apps.web.test_urls_usuarios"


@override_settings(ROOT_URLCONF=TEST_URLCONF)
class UserListAccessTests(TestCase):
    """RBAC de acceso: solo Owner; Admin/Miembro y anónimo bloqueados."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Plataforma")
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password=PWD, is_owner=True
        )
        cls.admin = User.objects.create_user(
            email="admin@certforge.test", password=PWD
        )
        cls.member = User.objects.create_user(
            email="member@certforge.test", password=PWD
        )
        Membership.objects.create(
            user=cls.admin, team=cls.team, role=MembershipRole.CONTRIBUTOR
        )
        Membership.objects.create(
            user=cls.member, team=cls.team, role=MembershipRole.CONTRIBUTOR
        )

    def test_owner_can_access_list(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("user-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "usuarios/list.html")

    def test_admin_gets_403(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("user-list"))
        self.assertEqual(resp.status_code, 403)

    def test_member_gets_403(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("user-list"))
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("user-list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_invite_endpoint_owner_only(self):
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("user-invite")).status_code, 403
        )
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(reverse("user-invite")).status_code, 200
        )


@override_settings(ROOT_URLCONF=TEST_URLCONF)
class UserListContentTests(TestCase):
    """Contenido de la tabla: usuarios, búsqueda, estado vacío, parcial HTMX."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Pagos")
        cls.owner = User.objects.create_user(
            email="owner@certforge.test",
            password=PWD,
            first_name="María",
            last_name="Reyes",
            is_owner=True,
        )
        cls.other = User.objects.create_user(
            email="jose@certforge.test",
            password=PWD,
            first_name="José",
            last_name="Cabrera",
        )
        Membership.objects.create(
            user=cls.other, team=cls.team, role=MembershipRole.CONTRIBUTOR
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_list_shows_users(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "owner@certforge.test")
        self.assertContains(resp, "jose@certforge.test")
        self.assertContains(resp, "Pagos")  # grupo del segundo usuario

    def test_owner_tag_rendered(self):
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "Owner")

    def test_search_narrows_results(self):
        # Se usa el parcial HTMX (solo filas) para no chocar con el correo del
        # propio Owner que aparece en el menú de usuario de la topbar.
        resp = self.client.get(
            reverse("user-list"), {"q": "jose"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(resp, "jose@certforge.test")
        self.assertNotContains(resp, "owner@certforge.test")

    def test_empty_state_when_no_results(self):
        resp = self.client.get(reverse("user-list"), {"q": "nadie-zzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sin resultados")

    def test_htmx_returns_rows_partial(self):
        resp = self.client.get(reverse("user-list"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "usuarios/_rows.html")
        self.assertNotContains(resp, "<html")
        self.assertContains(resp, "jose@certforge.test")

    def test_table_is_sortable_with_actions_no_sort(self):
        # Orden nativo (ForgeDataTable): wrapper con data-forge-sortable y la
        # columna de acciones marcada data-no-sort.
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, "data-forge-sortable")
        self.assertContains(resp, "data-no-sort")

    def test_no_duplicate_native_search(self):
        # Usuarios YA tiene su búsqueda server-side (HTMX) en la toolbar; no se
        # añade un segundo buscador client-side para no duplicar la búsqueda.
        resp = self.client.get(reverse("user-list"))
        self.assertContains(resp, 'name="q"')  # búsqueda server-side
        self.assertNotContains(resp, "data-forge-search")  # sin buscador nativo

    def test_each_user_row_uses_own_avatar_choice(self):
        owner_prefs = get_or_create_preferences(self.owner)
        owner_prefs.avatar_choice = 7
        owner_prefs.save(update_fields=["avatar_choice"])
        other_prefs = get_or_create_preferences(self.other)
        other_prefs.avatar_choice = 0
        other_prefs.save(update_fields=["avatar_choice"])

        resp = self.client.get(reverse("user-list"), HTTP_HX_REQUEST="true")
        html = resp.content.decode()
        self.assertEqual(html.count("forge-avatar--media"), 1)
        self.assertIn("jose@certforge.test", html)


@override_settings(ROOT_URLCONF=TEST_URLCONF)
class UserInviteTests(TestCase):
    """Modal de alta y creación de usuario, sin mass-assignment de Owner."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Marketing")
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password=PWD, is_owner=True
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_invite_modal_get_returns_200(self):
        resp = self.client.get(reverse("user-invite"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "usuarios/_invite_modal.html")
        self.assertContains(resp, "Crear usuario")

    def test_invite_creates_user_returns_200(self):
        resp = self.client.post(
            reverse("user-invite"),
            {
                "email": "nuevo@certforge.test",
                "password1": "Nuevo-Usuario-2026!",
                "password2": "Nuevo-Usuario-2026!",
                "groups": [self.team.pk],
                "role": MembershipRole.CONTRIBUTOR,
            },
        )
        self.assertEqual(resp.status_code, 200)
        new = User.objects.get(email="nuevo@certforge.test")
        self.assertTrue(new.check_password("Nuevo-Usuario-2026!"))
        self.assertFalse(new.is_owner)
        self.assertFalse(new.is_staff)
        self.assertTrue(
            Membership.objects.filter(user=new, team=self.team).exists()
        )

    def test_invite_does_not_allow_is_owner_mass_assignment(self):
        # Intento de inyectar is_owner=True por el POST: debe ignorarse.
        resp = self.client.post(
            reverse("user-invite"),
            {
                "email": "intruso@certforge.test",
                "password1": "Intruso-Usuario-2026!",
                "password2": "Intruso-Usuario-2026!",
                "groups": [self.team.pk],
                "role": MembershipRole.CONTRIBUTOR,
                "is_owner": "true",
                "is_staff": "true",
            },
        )
        self.assertEqual(resp.status_code, 200)
        new = User.objects.get(email="intruso@certforge.test")
        self.assertFalse(new.is_owner)
        self.assertFalse(new.is_staff)

    def test_invite_role_assigns_group_role_not_global(self):
        self.client.post(
            reverse("user-invite"),
            {
                "email": "groupcolab@certforge.test",
                "password1": "Colab-Grupo-2026!",
                "password2": "Colab-Grupo-2026!",
                "groups": [self.team.pk],
                "role": MembershipRole.CONTRIBUTOR,
            },
        )
        new = User.objects.get(email="groupcolab@certforge.test")
        m = Membership.objects.get(user=new, team=self.team)
        self.assertEqual(m.role, MembershipRole.CONTRIBUTOR)

    def test_create_ldap_user_has_unusable_password(self):
        resp = self.client.post(
            reverse("user-invite"),
            {
                "email": "ldap@certforge.test",
                "use_ldap": "on",
                "groups": [self.team.pk],
                "role": MembershipRole.CONTRIBUTOR,
            },
        )
        self.assertEqual(resp.status_code, 200)
        new = User.objects.get(email="ldap@certforge.test")
        self.assertFalse(new.has_usable_password())
        self.assertFalse(new.is_owner)

    def test_invite_duplicate_email_rejected(self):
        resp = self.client.post(
            reverse("user-invite"),
            {
                "email": "owner@certforge.test",  # ya existe
                "groups": [self.team.pk],
                "role": MembershipRole.CONTRIBUTOR,
            },
        )
        self.assertEqual(resp.status_code, 200)  # re-render del modal con error
        self.assertContains(resp, "Ya existe un usuario con ese correo.")


@override_settings(ROOT_URLCONF=TEST_URLCONF)
class UserToggleActiveTests(TestCase):
    """Acción de fila activar/desactivar (solo Owner, no auto-desactivación)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password=PWD, is_owner=True
        )
        cls.target = User.objects.create_user(
            email="target@certforge.test", password=PWD
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_toggle_deactivates_then_reactivates(self):
        self.assertTrue(self.target.is_active)
        resp = self.client.post(
            reverse("user-toggle-active", args=[self.target.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertContains(resp, "Activar")  # la fila ahora ofrece reactivar

        self.client.post(reverse("user-toggle-active", args=[self.target.pk]))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_cannot_deactivate_self(self):
        resp = self.client.post(
            reverse("user-toggle-active", args=[self.owner.pk])
        )
        self.assertEqual(resp.status_code, 400)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_toggle_member_gets_403(self):
        member = User.objects.create_user(
            email="m@certforge.test", password=PWD
        )
        self.client.force_login(member)
        resp = self.client.post(
            reverse("user-toggle-active", args=[self.target.pk])
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(ROOT_URLCONF=TEST_URLCONF)
class UserEditTests(TestCase):
    """Edición de usuario en modal (solo Owner, sin escalada a is_owner)."""

    @classmethod
    def setUpTestData(cls):
        cls.team_a = Team.objects.create(name="Plataforma")
        cls.team_b = Team.objects.create(name="Pagos")
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password=PWD, is_owner=True
        )
        cls.target = User.objects.create_user(
            email="target@certforge.test",
            password=PWD,
            first_name="Ana",
            last_name="Luna",
        )
        Membership.objects.create(
            user=cls.target, team=cls.team_a, role=MembershipRole.CONTRIBUTOR
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_edit_modal_get_returns_200(self):
        resp = self.client.get(reverse("user-edit", args=[self.target.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "usuarios/_edit_modal.html")
        self.assertContains(resp, "Editar usuario")
        self.assertContains(resp, "target@certforge.test")

    def test_edit_updates_name_active_and_groups(self):
        resp = self.client.post(
            reverse("user-edit", args=[self.target.pk]),
            {
                "first_name": "Anabel",
                "last_name": "Luna Díaz",
                "is_active": "",  # desactivar
                "groups": [self.team_b.pk],  # cambia de grupo
                "role": MembershipRole.CONTRIBUTOR,
            },
        )
        self.assertEqual(resp.status_code, 200)
        # La fila refrescada vuelve por OOB.
        self.assertContains(resp, 'id="user-row-%d"' % self.target.pk)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "Anabel")
        self.assertEqual(self.target.last_name, "Luna Díaz")
        self.assertFalse(self.target.is_active)
        # Reconciliación de membresías: solo team_b, rol Colaborador.
        teams = set(
            self.target.memberships.values_list("team__name", flat=True)
        )
        self.assertEqual(teams, {"Pagos"})
        m = self.target.memberships.get(team=self.team_b)
        self.assertEqual(m.role, MembershipRole.CONTRIBUTOR)
        # NUNCA se promueve a Owner.
        self.assertFalse(self.target.is_owner)

    def test_edit_non_owner_gets_403(self):
        member = User.objects.create_user(
            email="member2@certforge.test", password=PWD
        )
        self.client.force_login(member)
        get_resp = self.client.get(
            reverse("user-edit", args=[self.target.pk])
        )
        self.assertEqual(get_resp.status_code, 403)
        post_resp = self.client.post(
            reverse("user-edit", args=[self.target.pk]),
            {"first_name": "Hack", "role": MembershipRole.CONTRIBUTOR},
        )
        self.assertEqual(post_resp.status_code, 403)

    def test_edit_cannot_self_promote_to_owner(self):
        # Un Owner edita a otro usuario e intenta inyectar is_owner/is_staff.
        resp = self.client.post(
            reverse("user-edit", args=[self.target.pk]),
            {
                "first_name": "Ana",
                "last_name": "Luna",
                "is_active": "on",
                "groups": [self.team_a.pk],
                "role": MembershipRole.CONTRIBUTOR,
                "is_owner": "true",
                "is_staff": "true",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_owner)
        self.assertFalse(self.target.is_staff)

    def test_owner_cannot_self_deactivate_via_edit(self):
        # Owner se edita a sí mismo intentando desactivarse: se rechaza.
        resp = self.client.post(
            reverse("user-edit", args=[self.owner.pk]),
            {
                "first_name": "Dueño",
                "last_name": "",
                "is_active": "",  # intenta desactivarse
                "role": MembershipRole.CONTRIBUTOR,
            },
        )
        self.assertEqual(resp.status_code, 200)
        # Re-render del modal con error, no éxito.
        self.assertTemplateUsed(resp, "usuarios/_edit_modal.html")
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
