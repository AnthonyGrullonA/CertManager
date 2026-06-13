"""Tests de los avatares SVG generativos (templatetag + componente _avatar.html).

Cubre el DoD de la tarea "avatars":
- ``{% avatar_svg index %}`` es determinista, geométrico e inline (sin storage).
- ``components/_avatar.html`` renderiza el SVG cuando ``avatar_choice > 0``,
  e iniciales en su defecto. No se renderizan fotos subidas.
"""
from django.template import Context, Template
from django.test import TestCase

from apps.web.templatetags.forge_avatars import AVATAR_COUNT, avatar_svg


class AvatarSvgTagTests(TestCase):
    def test_renders_inline_svg(self):
        out = avatar_svg(1)
        self.assertIn("<svg", out)
        self.assertIn("viewBox=\"0 0 64 64\"", out)
        # Inline: sin referencias a archivos/storage.
        self.assertNotIn("http", out)
        self.assertNotIn(".png", out)
        self.assertNotIn(".svg\"", out)

    def test_deterministic(self):
        self.assertEqual(avatar_svg(5), avatar_svg(5))

    def test_distinct_indices_differ(self):
        # Distintas formas/paletas -> markup distinto para índices distintos.
        self.assertNotEqual(avatar_svg(1), avatar_svg(2))

    def test_at_least_24_variants(self):
        self.assertGreaterEqual(AVATAR_COUNT, 24)

    def test_zero_or_negative_is_empty(self):
        self.assertEqual(avatar_svg(0), "")
        self.assertEqual(avatar_svg(-3), "")

    def test_invalid_index_is_empty(self):
        self.assertEqual(avatar_svg("abc"), "")
        self.assertEqual(avatar_svg(None), "")

    def test_size_keyword_changes_dimension(self):
        small = avatar_svg(3, size="xs")
        large = avatar_svg(3, size="xl")
        self.assertIn('width="22"', small)
        self.assertIn('width="64"', large)

    def test_size_integer_px(self):
        self.assertIn('width="120"', avatar_svg(3, size=120))


class AvatarComponentTests(TestCase):
    def _render(self, **ctx):
        tpl = Template(
            '{% include "components/_avatar.html" %}'
        )
        return tpl.render(Context(ctx))

    def test_renders_svg_when_choice_positive(self):
        html = self._render(name="María Reyes", email="m@x.io", avatar_choice=4)
        self.assertIn("<svg", html)
        self.assertIn("forge-avatar--media", html)

    def test_no_image_upload_supported(self):
        # No hay subida de fotos: aunque se pase src, NO se renderiza <img>.
        html = self._render(
            name="María", email="m@x.io", src="/media/avatars/face.png", avatar_choice=4
        )
        self.assertNotIn("<img", html)
        self.assertIn("<svg", html)  # cae al avatar SVG elegido

    def test_falls_back_to_initials(self):
        html = self._render(name="María Reyes", email="m@x.io", avatar_choice=0)
        self.assertNotIn("<svg", html)
        self.assertIn("MR", html)

    def test_ignores_global_chrome_choice(self):
        # SIN fallback global: el avatar del usuario autenticado
        # (forge_user_avatar_choice) NO debe pintarse sobre otra persona.
        # El topbar pasa su avatar explícito como avatar_choice.
        html = self._render(
            name="Ana Mota", email="a@x.io", forge_user_avatar_choice=9
        )
        self.assertNotIn("<svg", html)
        self.assertIn("AM", html)
