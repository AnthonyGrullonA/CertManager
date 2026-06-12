"""Roles granulares: MEMBER → CONTRIBUTOR; nuevas choices VIEWER/CONTRIBUTOR/ADMIN."""
from django.db import migrations, models


def member_to_contributor(apps, schema_editor):
    Membership = apps.get_model("teams", "Membership")
    Membership.objects.filter(role="MEMBER").update(role="CONTRIBUTOR")


def back(apps, schema_editor):
    Membership = apps.get_model("teams", "Membership")
    Membership.objects.filter(role="CONTRIBUTOR").update(role="MEMBER")


class Migration(migrations.Migration):

    dependencies = [
        ("teams", "0002_team_default_check_interval"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.CharField(
                choices=[
                    ("VIEWER", "Visualizador"),
                    ("CONTRIBUTOR", "Colaborador"),
                    ("ADMIN", "Admin de grupo"),
                ],
                default="VIEWER",
                max_length=12,
                verbose_name="Rol",
            ),
        ),
        migrations.RunPython(member_to_contributor, back),
    ]
