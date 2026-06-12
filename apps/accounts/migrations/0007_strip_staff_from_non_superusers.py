"""Invariante de acceso al admin: solo el superusuario real es is_staff.

Los Owner/Admin de la aplicación gestionan todo desde la UI propia; no deben
tener acceso al admin de Django. Este data-migration quita ``is_staff`` a
cualquier usuario que NO sea superusuario (nunca toca a los superusuarios, para
no dejar a nadie fuera del admin por error).
"""
from django.db import migrations


def strip_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=False, is_staff=True).update(is_staff=False)


def noop(apps, schema_editor):
    # Irreversible de forma segura: no volvemos a otorgar is_staff a nadie.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_remove_userpreferences_table_density"),
    ]

    operations = [
        migrations.RunPython(strip_staff, noop),
    ]
