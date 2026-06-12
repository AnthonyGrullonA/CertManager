"""Settings de desarrollo local: SQLite, DEBUG activado."""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# SQLite por defecto en local.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

# Correo a consola en desarrollo.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
