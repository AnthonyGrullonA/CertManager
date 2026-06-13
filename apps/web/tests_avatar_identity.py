"""Cada persona se muestra con SU avatar, nunca con el del usuario autenticado.

El componente ``_avatar.html`` tenía un fallback al avatar global del request
(``forge_user_avatar_choice``): cualquier include sin ``avatar_choice`` pintaba
el avatar del usuario logueado sobre otra persona (admins en Grupos,
responsables en el detalle). Ahora:

- el componente NO tiene fallback global (sin ``avatar_choice`` -> iniciales);
- el topbar pasa el avatar del usuario autenticado explícitamente;
- Grupos pasa el avatar real de cada admin;
- los responsables del detalle usan el avatar elegido si el correo es un
  usuario, o el derivado determinista por email si es un correo externo.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import default_avatar_choice, get_or_create_preferences
from apps.certificates.models import Certificate, CertificateRecipient
from apps.core.enums import MembershipRole
from apps.teams.models import Membership, Team
from apps.web.templatetags.forge_avatars import avatar_svg

User = get_user_model()


def _set_avatar(user, choice):
    prefs = get_or_create_preferences(user)
    prefs.avatar_choice = choice
    prefs.save(update_fields=["avatar_choice"])


@override_settings(ROOT_URLCONF="apps.web.test_urls_grupos")
class GruposOverviewAvatarTests(TestCase):
    def setUp(self):
        cache.clear()
        self.viewer = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        _set_avatar(self.viewer, 9)
        self.admin = User.objects.create_user("admin@certforge.test", "x")
        _set_avatar(self.admin, 7)
        team = Team.objects.create(name="Plataforma")
        Membership.objects.create(user=self.admin, team=team, role=MembershipRole.ADMIN)
        self.client.force_login(self.viewer)

    def test_admin_rows_use_each_admins_avatar(self):
        resp = self.client.get(reverse("team-list"))
        html = resp.content.decode()
        # La fila pinta el avatar del admin (xs), no el del usuario autenticado.
        self.assertIn(avatar_svg(7, size="xs"), html)
        self.assertNotIn(avatar_svg(9, size="xs"), html)

    def test_topbar_still_shows_authenticated_user_avatar(self):
        resp = self.client.get(reverse("team-list"))
        self.assertIn(avatar_svg(9, size="sm"), resp.content.decode())


@override_settings(ROOT_URLCONF="apps.web.test_urls_detalle")
class DetalleResponsablesAvatarTests(TestCase):
    def setUp(self):
        cache.clear()
        self.viewer = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        _set_avatar(self.viewer, 9)
        self.team = Team.objects.create(name="Plataforma")
        self.cert = Certificate.objects.create(
            domain="api.ejemplo.com", port=443, team=self.team,
        )
        self.client.force_login(self.viewer)

    def _resumen(self):
        resp = self.client.get(reverse("cert-detail-tab", args=[self.cert.id, "resumen"]))
        return resp.content.decode()

    def test_recipient_user_shows_their_chosen_avatar(self):
        subscriber = User.objects.create_user("sub@certforge.test", "x")
        derived = default_avatar_choice(subscriber.email)
        chosen = derived % 50 + 1  # garantiza un avatar distinto al derivado
        _set_avatar(subscriber, chosen)
        CertificateRecipient.objects.create(
            certificate=self.cert, email=subscriber.email, user=subscriber
        )
        self.assertIn(avatar_svg(chosen, size="sm"), self._resumen())

    def test_external_email_shows_derived_avatar(self):
        CertificateRecipient.objects.create(
            certificate=self.cert, email="externo@claro.com.do"
        )
        derived = default_avatar_choice("externo@claro.com.do")
        # El avatar del viewer NUNCA debe coincidir con el derivado, para que
        # el test no pase por accidente vía el fallback global.
        _set_avatar(self.viewer, derived % 50 + 1)
        html = self._resumen()
        self.assertIn(avatar_svg(derived, size="sm"), html)
        self.assertNotIn(avatar_svg(derived % 50 + 1, size="sm"), html)

    def test_admin_fallback_shows_admins_avatar(self):
        admin = User.objects.create_user("admin@certforge.test", "x")
        _set_avatar(admin, 7)
        Membership.objects.create(user=admin, team=self.team, role=MembershipRole.ADMIN)
        html = self._resumen()
        self.assertIn(avatar_svg(7, size="sm"), html)
        self.assertNotIn(avatar_svg(9, size="sm"), html)
