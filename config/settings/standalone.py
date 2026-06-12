"""Perfil 'standalone' — plug-and-play en un solo contenedor/proceso.

Pensado para "git clone / un comando / funciona" SIN servicios externos:
- BD SQLite (endurecida con WAL, ver apps/core/db_signals) en un volumen por
  defecto; MySQL/Postgres siguen siendo opcionales vía DATABASE_URL.
- SECRET_KEY: del entorno o, si falta, autogenerada y persistida UNA vez en el
  volumen (no se regenera entre arranques → no invalida sesiones).
- ALLOWED_HOSTS permisivo por defecto (intranet); ajustable por entorno.
- Scheduler en-proceso ON por defecto (RUN_SCHEDULER=True): sin cron externo.
- Estáticos servidos por WhiteNoise (manifest + compresión).

NO reemplaza a prod.py (perfil corporativo: MySQL + SECRET_KEY/ALLOWED_HOSTS
estrictos + TLS/HSTS). Este perfil es un opt-in explícito
(DJANGO_SETTINGS_MODULE=config.settings.standalone).
"""
import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = env.bool("DEBUG", default=False)

# --- Datos persistentes (sqlite + media + secret). Volumen recomendado: /data ---
DATA_DIR = Path(env("CERTFORGE_DATA_DIR", default=str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- SECRET_KEY: del entorno o autogenerada y persistida una sola vez -------
# Creación ATÓMICA con O_CREAT|O_EXCL: si varios procesos arrancan a la vez sobre
# el mismo volumen, solo uno crea el archivo (modo 0600); el resto lo relee.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
if not SECRET_KEY:
    _key_file = DATA_DIR / "secret_key"
    try:
        _fd = os.open(str(_key_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            SECRET_KEY = get_random_secret_key()
            os.write(_fd, SECRET_KEY.encode())
        finally:
            os.close(_fd)
    except FileExistsError:
        SECRET_KEY = _key_file.read_text().strip()

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- Base de datos: SQLite por defecto; MySQL/Postgres opcional ------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{DATA_DIR / 'certforge.sqlite3'}",
    )
}
if "mysql" in DATABASES["default"].get("ENGINE", ""):
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].update({
        "charset": "utf8mb4",
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
    })

MEDIA_ROOT = DATA_DIR / "media"

# --- Estáticos: WhiteNoise manifest + compresión (igual que prod) ----------
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "config.storages.ForgivingManifestStaticFilesStorage"},
}

# --- Scheduler en-proceso ON por defecto (single-container, sin cron) ------
RUN_SCHEDULER = env.bool("RUN_SCHEDULER", default=True)

# --- Correo: SMTP real solo si hay host por entorno; si no, consola --------
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if env("EMAIL_HOST", default="")
    else "django.core.mail.backends.console.EmailBackend"
)

# --- Seguridad: por defecto pensado para intranet HTTP --------------------
# Si lo ponés detrás de TLS, activá estos por entorno (1/True).
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
