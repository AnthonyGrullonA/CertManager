"""Tests del avatar por defecto: ningún usuario queda sin avatar.

Cubre el diseño 2026-06-12-avatar-default-design.md:
- ``default_avatar_choice(email)`` es determinista y cae en ``1..AVATAR_COUNT``.
- La señal de creación de usuario asigna ese avatar (nunca 0).
- ``AvatarChoiceForm`` rechaza 0 (el estado "sin avatar" ya no es elegible).
- La migración de backfill puebla los registros existentes en 0.
"""
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.forms_profile import AvatarChoiceForm
from apps.accounts.models import UserPreferences, default_avatar_choice
from apps.web.templatetags.forge_avatars import AVATAR_COUNT

User = get_user_model()


class DefaultAvatarChoiceTests(TestCase):
    def test_returns_index_in_valid_range(self):
        for email in ("a@x.io", "maria@claro.com.do", "z" * 60 + "@y.com", ""):
            choice = default_avatar_choice(email)
            self.assertGreaterEqual(choice, 1, email)
            self.assertLessEqual(choice, AVATAR_COUNT, email)

    def test_is_deterministic(self):
        self.assertEqual(
            default_avatar_choice("maria@claro.com.do"),
            default_avatar_choice("maria@claro.com.do"),
        )

    def test_distributes_across_catalog(self):
        emails = [f"user{i}@claro.com.do" for i in range(40)]
        choices = {default_avatar_choice(e) for e in emails}
        self.assertGreater(len(choices), 5)


class SignalAssignsAvatarTests(TestCase):
    def test_new_user_gets_default_avatar(self):
        user = User.objects.create_user(email="nuevo@claro.com.do", password="x")
        prefs = UserPreferences.objects.get(user=user)
        self.assertEqual(prefs.avatar_choice, default_avatar_choice(user.email))
        self.assertGreaterEqual(prefs.avatar_choice, 1)


class ProfileSectionTemplateTests(TestCase):
    def test_no_remove_avatar_button(self):
        from django.template.loader import render_to_string

        user = User.objects.create_user(email="ana@claro.com.do", password="x")
        html = render_to_string(
            "perfil/_section_avatar.html",
            {"prefs": user.preferences, "display_name": "Ana"},
        )
        self.assertNotIn('"avatar_choice": "0"', html)


class AvatarChoiceFormTests(TestCase):
    def test_rejects_zero(self):
        form = AvatarChoiceForm(data={"avatar_choice": 0})
        self.assertFalse(form.is_valid())

    def test_rejects_out_of_range(self):
        form = AvatarChoiceForm(data={"avatar_choice": AVATAR_COUNT + 1})
        self.assertFalse(form.is_valid())

    def test_accepts_bounds(self):
        for value in (1, AVATAR_COUNT):
            form = AvatarChoiceForm(data={"avatar_choice": value})
            self.assertTrue(form.is_valid(), form.errors)


class BackfillMigrationTests(TestCase):
    def test_backfill_assigns_avatar_to_zero_rows(self):
        user = User.objects.create_user(email="legacy@claro.com.do", password="x")
        UserPreferences.objects.filter(user=user).update(avatar_choice=0)

        import importlib

        migration = importlib.import_module(
            "apps.accounts.migrations.0010_avatar_choice_backfill"
        )
        migration.forward(django_apps, schema_editor=None)  # forward no lo usa

        prefs = UserPreferences.objects.get(user=user)
        self.assertEqual(prefs.avatar_choice, default_avatar_choice(user.email))
