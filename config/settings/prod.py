"""Settings de producción: MySQL 8 y seguridad endurecida."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# SECRET_KEY obligatorio en producción: SIN default (falla el arranque si falta,
# en vez de heredar el placeholder "change-me-in-prod" de base.py).
SECRET_KEY = env("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# MySQL obligatorio vía DATABASE_URL (p.ej. mysql://user:pass@db:3306/certforge).
# Estándar corporativo: MySQL 8 en contenedor. django-environ deriva el ENGINE
# del esquema de la URL.
DATABASES = {"default": env.db("DATABASE_URL")}

# Opciones específicas de MySQL: utf8mb4 (Unicode completo) y modo estricto.
if "mysql" in DATABASES["default"].get("ENGINE", ""):
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].update({
        "charset": "utf8mb4",
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
    })

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
