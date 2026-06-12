from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_remove_personal_notification_preferences"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userpreferences",
            name="table_density",
        ),
    ]
