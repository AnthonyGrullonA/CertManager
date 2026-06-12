"""Backfill: asigna avatar a todo usuario que quedó "sin avatar" (choice=0).

El estado 0 (iniciales) se eliminó: todo usuario tiene un avatar SVG asignado,
determinista por email (ver ``default_avatar_choice``). Reversa: no-op (no hay
forma de saber quién estaba en 0, y volver a 0 reintroduciría el bug visual).
"""
from django.db import migrations

from apps.accounts.models import default_avatar_choice


def forward(apps, schema_editor):
    UserPreferences = apps.get_model("accounts", "UserPreferences")
    for prefs in UserPreferences.objects.filter(avatar_choice=0).select_related("user"):
        prefs.avatar_choice = default_avatar_choice(prefs.user.email)
        prefs.save(update_fields=["avatar_choice"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_user_password_changed_at"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
