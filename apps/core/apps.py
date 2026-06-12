from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Núcleo"

    def ready(self):
        # Registra los PRAGMAs de endurecimiento de SQLite (no-op en MySQL).
        from . import db_signals  # noqa: F401

        # Conecta las señales de auditoría (OWASP A09) a los modelos sensibles.
        from . import audit_signals

        audit_signals.connect()
