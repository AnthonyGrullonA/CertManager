"""Settings de producción: MySQL 8 y seguridad endurecida."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# SECRET_KEY obligatorio en producción: SIN default (falla el arranque si falta,
# en vez de heredar el placeholder "change-me-in-prod" de base.py).
SECRET_KEY = env("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# MySQL 8 (estándar corporativo) con los valores POR SEPARADO (no DATABASE_URL).
# Obligatorios: DB_NAME, DB_USER, DB_PASSWORD, DB_HOST. DB_PORT por defecto 3306.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT", default="3306"),
        # utf8mb4 (Unicode completo) + modo estricto.
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# --- Estáticos (WhiteNoise + manifest) ------------------------------------
# ManifestStaticFilesStorage (con hash de contenido) SOLO en prod. WhiteNoise
# añade compresión. Requiere que collectstatic resuelva todos los assets
# referenciados (iconos inline + fuentes con rutas relativas evitan roturas).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Subclase tolerante (config/storages.py): hashea + comprime, pero no
        # aborta si un asset de vendor referencia un archivo ausente (p.ej. el
        # sourcemap chart.umd.js.map que no se distribuye). Mitiga el riesgo
        # "Manifest rompe el arranque si falta un asset" del plan.
        "BACKEND": "config.storages.ForgivingManifestStaticFilesStorage",
    },
}

# --- Seguridad ------------------------------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

# Correo en producción: SMTP real SOLO si hay host configurado por entorno; si no,
# degrada a consola para no crashear en envíos cuando no se configuró SMTP.
# (Las alertas/reportes usan además el SMTP de OrganizationSettings vía
#  apps.core.mail.smtp_connection, independiente de este backend por defecto.)
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if env("EMAIL_HOST", default="")
    else "django.core.mail.backends.console.EmailBackend"
)
