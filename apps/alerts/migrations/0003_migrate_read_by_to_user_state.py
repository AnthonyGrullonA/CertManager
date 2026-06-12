"""Migración de datos: Alert.read_by (M2M) -> AlertUserState.read_at.

Por cada par (alert, user) en `Alert.read_by` crea un AlertUserState con
`read_at = alert.updated_at` (mejor aproximación disponible del momento de
lectura; `read_by` no guardaba timestamp). `read_by` se deja DEPRECADO pero
presente para conservar reversibilidad.

Reversa: reconstruye `read_by` desde los AlertUserState con `read_at` no nulo y
borra los estados creados, dejando el esquema como antes.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Alert = apps.get_model("alerts", "Alert")
    AlertUserState = apps.get_model("alerts", "AlertUserState")

    for alert in Alert.objects.all():
        read_at = alert.updated_at
        for user in alert.read_by.all():
            state, created = AlertUserState.objects.get_or_create(
                alert=alert,
                user=user,
                defaults={"read_at": read_at},
            )
            if not created and state.read_at is None:
                state.read_at = read_at
                state.save(update_fields=["read_at"])


def backwards(apps, schema_editor):
    Alert = apps.get_model("alerts", "Alert")
    AlertUserState = apps.get_model("alerts", "AlertUserState")

    for state in AlertUserState.objects.exclude(read_at__isnull=True).select_related("alert", "user"):
        state.alert.read_by.add(state.user)

    # Limpia los estados creados por esta migración (todos los que tienen read_at).
    AlertUserState.objects.exclude(read_at__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0002_webhookintegration_rich_format_alertuserstate"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
