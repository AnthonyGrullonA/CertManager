"""Tests de la pantalla Perfil (paso 12).

Patrón: test_urls_perfil + @override_settings para que el Client resuelva las
urls globales y las propias. Cubre el DoD: guardados parciales -> 200 + toast;
avatar SVG sin subida de fotos; Mis grupos con estado vacío; errores -> toast.
"""
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import get_or_create_preferences
from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team

User = get_user_model()

_TMP_MEDIA = tempfile.mkdtemp()


@override_settings(
    ROOT_URLCONF="apps.web.test_urls_perfil",
    MEDIA_ROOT=_TMP_MEDIA,
)
class ProfilePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="maria@certforge.io", password="Sup3r-Secret-99", first_name="María", last_name="Reyes"
        )
        self.client.force_login(self.user)

    def test_profile_page_200(self):
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Datos personales")
        self.assertContains(resp, "Preferencias")
        self.assertNotContains(resp, "Notificaciones propias")
        self.assertContains(resp, "Mis grupos")

    def test_profile_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, 302)

    def test_my_groups_empty_state(self):
        resp = self.client.get(reverse("profile"))
        self.assertContains(resp, "Aún no perteneces a ningún grupo")

    def test_my_groups_lists_role_per_group(self):
        team = Team.objects.create(name="Pagos")
        Membership.objects.create(user=self.user, team=team, role=MembershipRole.ADMIN)
        resp = self.client.get(reverse("profile"))
        self.assertContains(resp, "Pagos")
        self.assertContains(resp, "Admin de grupo")
        self.assertNotContains(resp, "Aún no perteneces")

    def test_identity_card_shows_avatar_name_and_email(self):
        """La tarjeta de identidad (fiel al kit) muestra avatar grande + correo."""
        resp = self.client.get(reverse("profile"))
        self.assertContains(resp, "section-avatar")
        self.assertContains(resp, "forge-avatar")
        self.assertContains(resp, "Elige un avatar")  # picker SVG (sin subir fotos)
        self.assertContains(resp, self.user.email)

    def test_sections_use_kit_form_primitives(self):
        """Las secciones usan las primitivas Forge (PrefRow/Switch), no clases sueltas."""
        resp = self.client.get(reverse("profile"))
        self.assertContains(resp, "perfil-prefrow")
        self.assertContains(resp, "perfil-select")

    def test_password_change_uses_modal_trigger(self):
        resp = self.client.get(reverse("profile"))
        self.assertContains(resp, reverse("password-change"))
        self.assertContains(resp, "Cambiar contraseña")


@override_settings(
    ROOT_URLCONF="apps.web.test_urls_perfil",
    MEDIA_ROOT=_TMP_MEDIA,
)
class ProfileSectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="maria@certforge.io", password="Sup3r-Secret-99"
        )
        self.client.force_login(self.user)

    def test_personal_section_saves_and_toasts(self):
        url = reverse("profile-section", args=["personal"])
        resp = self.client.post(url, {"first_name": "Ana", "last_name": "Pérez", "email": "ana@certforge.io"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "forge-toast")
        self.assertContains(resp, "Cambios guardados")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ana")
        self.assertEqual(self.user.email, "ana@certforge.io")

    def test_personal_section_duplicate_email_errors_with_toast(self):
        User.objects.create_user(email="taken@certforge.io", password="x12345678!A")
        url = reverse("profile-section", args=["personal"])
        resp = self.client.post(url, {"first_name": "X", "last_name": "Y", "email": "taken@certforge.io"})
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, "forge-toast", status_code=422)
        self.assertContains(resp, "Ya existe una cuenta", status_code=422)

    def test_preferences_section_saves(self):
        url = reverse("profile-section", args=["preferences"])
        resp = self.client.post(
            url,
            {"language": "en", "timezone": "UTC"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cambios guardados")
        prefs = get_or_create_preferences(self.user)
        self.assertEqual(prefs.language, "en")
        self.assertEqual(prefs.timezone, "UTC")

    def test_notifications_section_removed(self):
        url = reverse("profile-section", args=["notifications"])
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, 400)

    def test_photo_upload_section_removed(self):
        # No se permite subir fotos: la sección 'avatar' (subida) ya no existe.
        url = reverse("profile-section", args=["avatar"])
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, 400)

    def test_profile_has_no_file_input(self):
        resp = self.client.get(reverse("profile"))
        self.assertNotContains(resp, 'type="file"')
        self.assertNotContains(resp, "Cambiar foto")

    def test_unknown_section_400(self):
        url = reverse("profile-section", args=["bogus"])
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, 400)

    def test_avatar_choice_section_persists(self):
        """Elegir un avatar SVG persiste avatar_choice y refresca el fragmento."""
        url = reverse("profile-section", args=["avatar_choice"])
        resp = self.client.post(url, {"avatar_choice": "7"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cambios guardados")
        prefs = get_or_create_preferences(self.user)
        self.assertEqual(prefs.avatar_choice, 7)
        # El fragmento devuelto re-renderiza el avatar elegido (SVG inline).
        self.assertContains(resp, "section-avatar")
        self.assertContains(resp, "<svg")

    def test_avatar_choice_zero_clears_selection(self):
        prefs = get_or_create_preferences(self.user)
        prefs.avatar_choice = 12
        prefs.save()
        url = reverse("profile-section", args=["avatar_choice"])
        resp = self.client.post(url, {"avatar_choice": "0"})
        self.assertEqual(resp.status_code, 200)
        prefs.refresh_from_db()
        self.assertEqual(prefs.avatar_choice, 0)

    def test_avatar_choice_out_of_range_errors(self):
        url = reverse("profile-section", args=["avatar_choice"])
        resp = self.client.post(url, {"avatar_choice": "99999"})
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, "forge-toast", status_code=422)
        prefs = get_or_create_preferences(self.user)
        self.assertEqual(prefs.avatar_choice, 0)

    def test_profile_page_shows_avatar_picker(self):
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "perfil-avatar-grid")
        self.assertContains(resp, "Elige un avatar")
        self.assertContains(resp, "perfil-avatar-pick")


@override_settings(ROOT_URLCONF="apps.web.test_urls_perfil")
class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="maria@certforge.io", password="Old-Pass-123!")
        self.client.force_login(self.user)

    def test_get_opens_modal(self):
        resp = self.client.get(reverse("password-change"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cambiar contraseña")
        self.assertContains(resp, "forge-modal")

    def test_post_changes_password_and_toasts(self):
        resp = self.client.post(
            reverse("password-change"),
            {
                "old_password": "Old-Pass-123!",
                "new_password1": "Brand-New-456!",
                "new_password2": "Brand-New-456!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Contraseña actualizada")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-New-456!"))

    def test_post_wrong_old_password_errors(self):
        resp = self.client.post(
            reverse("password-change"),
            {
                "old_password": "WRONG",
                "new_password1": "Brand-New-456!",
                "new_password2": "Brand-New-456!",
            },
        )
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, "forge-toast", status_code=422)
