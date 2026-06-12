"""
Settings base de CertForge, comunes a todos los entornos.

Los valores sensibles y dependientes del entorno se leen de variables de entorno
(via django-environ). Nunca se hardcodean secretos aquí.
"""
import importlib.util
from pathlib import Path

import environ

# certforge/config/settings/base.py -> BASE_DIR = certforge/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

# Lee .env si existe (en local). En contenedor las vars vienen del entorno.
env_file = BASE_DIR / ".env"
if env_file.exists():
    env.read_env(str(env_file))

# NOTA: base.py NUNCA es el settings activo de un despliegue (es solo herencia).
# prod.py exige DJANGO_SECRET_KEY sin default (fail-loud) y standalone.py la
# autogenera/persiste. Este default débil solo aplica a ejecución directa de base.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="change-me-in-prod")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
OBSFORGE_ENABLED = env.bool("OBSFORGE_ENABLED", default=True)
# Modo mantenimiento: si True, MaintenanceMiddleware devuelve 503 'maintenance'
# para todo el tráfico (excepto /health, /admin y superusuarios).
MAINTENANCE_MODE = env.bool("MAINTENANCE_MODE", default=False)

# --- Aplicaciones ---------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "django_filters",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.teams",
    "apps.certificates",
    "apps.monitoring",
    "apps.alerts",
    "apps.reports",
    "apps.mailtemplates",
    "apps.web",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise sirve estáticos comprimidos directamente desde la app; va justo
    # tras SecurityMiddleware (recomendación oficial), antes que el resto.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Log estructurado por request (status + latencia + reference_id, web y /api/).
    # Tras Auth para leer request.user; envuelve al resto para medir la latencia.
    "apps.core.middleware.RequestLogMiddleware",
    # Restringe el admin de Django al superusuario real (los Owner/Admin de la app
    # van al dashboard). Tras Auth para disponer de request.user.
    "apps.core.middleware.AdminAccessMiddleware",
    # Modo mantenimiento opcional (503 'maintenance' si MAINTENANCE_MODE). Tras
    # Auth porque exime al superusuario; exime /health y /admin.
    "apps.core.middleware.MaintenanceMiddleware",
    # Aplica el idioma preferido del usuario (selector de Perfil). Tras Auth.
    "apps.accounts.middleware.UserLocaleMiddleware",
    # Expone request a la auditoría (quién hace qué). Tras Auth.
    "apps.core.middleware.AuditContextMiddleware",
    # Exige enrolar 2FA si la organización lo requiere. Tras Auth.
    "apps.core.middleware.Require2FAMiddleware",
    # Fuerza el cambio de contraseña vencida si la organización lo exige. Tras Auth.
    "apps.core.middleware.PasswordExpiryMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # CSP en modo Report-Only en esta fase: no bloquea htmx ni los handlers
    # inline del chrome; solo reporta violaciones. Endurecer en hardening (paso 15).
    "csp.middleware.CSPMiddleware",
]

# obsforge es OPCIONAL: solo se inserta el middleware si el flag está activo Y el
# paquete está instalado. Sin el import guard, un clon sin obsforge (vive en un
# índice privado) crasheaba al cargar MIDDLEWARE, antes del fail-open del bootstrap.
# Con el guard: prod (que sí trae obsforge) funciona igual; un instalable mínimo
# degrada en silencio al logging estándar de Django.
_rid_index = 1
if OBSFORGE_ENABLED and importlib.util.find_spec("obsforge"):
    MIDDLEWARE.insert(
        1,
        "obsforge.integrations.django.middleware.DjangoObservabilityMiddleware",
    )
    _rid_index = 2
# RequestIDMiddleware va JUSTO DESPUÉS de obsforge: así reusa el correlation_id ya
# bindeado (el id del card de error == el de los logs). Si obsforge no está, igual
# fija un reference_id (header entrante o uuid).
MIDDLEWARE.insert(_rid_index, "apps.core.middleware.RequestIDMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Chrome global de Forge UI: ámbito (scope), panel de
                # notificaciones, datos de usuario y monitoreo (paso 3).
                "apps.web.context_processors.forge_globals",
                "apps.web.context_processors.asset_version",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Base de datos --------------------------------------------------------
# Por defecto SQLite (cero-config). prod.py exige MySQL vía DATABASE_URL;
# el perfil standalone usa SQLite (WAL) en un volumen para "un solo contenedor".
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

# --- Autenticación --------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Backends de autenticación, en orden:
#  1) ModelBackend — usuario local de Django (correo + contraseña local).
#  2) DatabaseLDAPBackend — LDAP corporativo configurado EN LA BASE DE DATOS
#     (modelo core.LdapConfiguration, editable por el Owner en Configuración).
#     Solo autentica usuarios que YA existen localmente (pre-creados por el Owner);
#     no crea cuentas automáticamente. Un único formulario/botón de login: Django
#     prueba los backends en orden (local primero, LDAP después).
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "apps.accounts.ldap_backend.DatabaseLDAPBackend",
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# --- Bloqueo de login por fuerza bruta (OWASP A07) ------------------------
# Tras LOGIN_LOCKOUT_MAX fallos por (IP, correo) dentro de la ventana, se
# bloquea ese par durante LOGIN_LOCKOUT_DURATION segundos. Basado en caché:
# en producción usar un backend compartido (Redis/Memcached) para que aplique
# entre workers de gunicorn.
LOGIN_LOCKOUT_MAX = env.int("LOGIN_LOCKOUT_MAX", default=5)
LOGIN_LOCKOUT_WINDOW = env.int("LOGIN_LOCKOUT_WINDOW", default=300)
LOGIN_LOCKOUT_DURATION = env.int("LOGIN_LOCKOUT_DURATION", default=900)

# --- Internacionalización -------------------------------------------------
LANGUAGE_CODE = "es"
TIME_ZONE = env("TIME_ZONE", default="America/Santo_Domingo")
USE_I18N = True
USE_TZ = True

# Idiomas soportados (el selector de Perfil cambia entre estos). El español es
# el idioma base (cadenas fuente); el inglés se traduce vía catálogos en locale/.
LANGUAGES = [("es", "Español"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Estáticos / media ----------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Seguridad (cabeceras comunes a todos los entornos) -------------------
# Producción endurece además SSL/HSTS/cookies-secure en prod.py.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# --- Content Security Policy (django-csp 4.x) -----------------------------
# ENFORCE por defecto (OWASP A02 Security Misconfiguration). Se mantiene
# 'unsafe-inline' porque el chrome usa handlers/estilos inline y HTMX; aun así
# la política restringe orígenes (default-src 'self', sin object/frame externos),
# bloqueando inyección de recursos externos y framing. Para diagnosticar
# violaciones sin bloquear, exporta CSP_REPORT_ONLY=1.
from csp.constants import NONE, SELF, UNSAFE_INLINE  # noqa: E402

_CSP_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF, UNSAFE_INLINE],
        "style-src": [SELF, UNSAFE_INLINE],
        "img-src": [SELF, "data:"],
        "font-src": [SELF],
        "connect-src": [SELF],
        "base-uri": [SELF],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
        "object-src": [NONE],
    },
}
if env.bool("CSP_REPORT_ONLY", default=False):
    CONTENT_SECURITY_POLICY_REPORT_ONLY = _CSP_POLICY
else:
    CONTENT_SECURITY_POLICY = _CSP_POLICY

# --- Django REST Framework ------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # La API REST SOLO se consume con API key (no sesión de navegador): así
        # /api/ nunca devuelve datos sin una clave válida. La web propia NO usa
        # /api/ (tiene sus vistas server-rendered en apps/web).
        "api.authentication.ApiKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        # Las API keys de solo lectura no pueden escribir.
        "api.permissions.ApiKeyScopePermission",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # Rate-limit. 'cert_test' acota "Probar ahora" (anti-SSRF/DoS, ver paso 2).
    "DEFAULT_THROTTLE_RATES": {
        "cert_test": env("THROTTLE_CERT_TEST", default="30/min"),
    },
    # Esquema OpenAPI (drf-spectacular) para la documentación navegable.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# --- Documentación de API (drf-spectacular / OpenAPI 3) -------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "CertManager API",
    "DESCRIPTION": "API REST de CertManager (certificados, grupos, alertas). "
    "Autenticación por API key (Authorization: Api-Key cf_live_… o X-Api-Key).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- Email (SMTP) ---------------------------------------------------------
# Los valores por defecto pueden sobreescribirse desde OrganizationSettings.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="certforge@localhost")

# --- Monitoreo (defaults; configurables en OrganizationSettings) ----------
MONITORING = {
    "DEFAULT_THRESHOLD_DAYS": env.int("MONITORING_THRESHOLD_DAYS", default=45),
    "DEFAULT_CRITICAL_DAYS": env.int("MONITORING_CRITICAL_DAYS", default=15),
    "CONNECT_TIMEOUT": env.int("MONITORING_TIMEOUT", default=10),
    "CHECK_INTERVAL_HOURS": env.int("MONITORING_INTERVAL_HOURS", default=24),
    # Renegociación legacy: DESACTIVADA por defecto (endurecimiento anti-SSRF /
    # decisión congelada del plan). Solo se habilita explícitamente por entorno.
    "ALLOW_LEGACY_RENEGOTIATION": env.bool("MONITORING_LEGACY_RENEG", default=False),
}

# Planificador en-proceso (APScheduler). Si RUN_SCHEDULER=True, el scheduler
# arranca dentro del proceso web (runserver/gunicorn); en cualquier caso se puede
# correr aparte con `python manage.py run_scheduler`. Intervalos configurables.
RUN_SCHEDULER = env.bool("RUN_SCHEDULER", default=False)
SCHEDULER = {
    "CERT_CHECK_HOURS": env.int("SCHEDULER_CERT_HOURS", default=24),
    "REPORTS_MINUTES": env.int("SCHEDULER_REPORTS_MINUTES", default=60),
    # Backup automático de la BD por el scheduler (0 = desactivado).
    "BACKUP_HOURS": env.int("SCHEDULER_BACKUP_HOURS", default=24),
}
# Backups: dónde guardarlos y cuántos conservar.
BACKUP_DIR = env("BACKUP_DIR", default=str(BASE_DIR / "backups"))
BACKUP_KEEP = env.int("BACKUP_KEEP", default=14)
# Re-notificación de alertas: no re-enviar el mismo correo si ya hay una alerta
# abierta del mismo nivel; solo al escalar (por vencer→crítico→vencido) o si han
# pasado N días desde el último envío.
ALERT_RENOTIFY_DAYS = env.int("ALERT_RENOTIFY_DAYS", default=7)

# --- Logging (JSON a stdout + fichero rotado + obsforge) ------------------
# Todos los logs (app, errores, scheduler, SMS y AUDITORÍA) salen en JSON a:
#   · stdout  → lo recoge el cluster en Kubernetes y obsforge (bridge → Loki);
#   · fichero → /var/log/certmanager/{app,audit}.log (LOG_DIR; fallback a
#     BASE_DIR/logs si /var/log no es escribible — pod sin permiso / local).
# No se define ``root`` a propósito: así no se pisa el handler que obsforge
# instala en el root (install_logging_bridge); con propagate=True los registros
# llegan también a obsforge.
from config.logging_utils import resolve_log_dir  # noqa: E402

LOG_DIR = resolve_log_dir(
    env("LOG_DIR", default="/var/log/certmanager"), str(BASE_DIR / "logs")
)

# CRÍTICO para Loki: si obsforge está activo, ÉL es el ÚNICO dueño de stdout
# (su StdoutSink emite el JSON serializado para Loki). Si además pusiéramos NUESTRO
# handler ``console`` en stdout, habría DOS esquemas JSON distintos intercalados en
# stdout y Loki no podría parsearlos. Por eso: con obsforge activo NO añadimos
# console (los registros llegan a obsforge por propagación al root); sin obsforge,
# sí usamos console para que stdout siga saliendo en JSON. Los ficheros /var/log
# usan SIEMPRE nuestro JsonFormatter.
_OBSFORGE_OWNS_STDOUT = bool(OBSFORGE_ENABLED and importlib.util.find_spec("obsforge"))

_LOG_HANDLERS = {
    "console": {"class": "logging.StreamHandler", "formatter": "json"},
}
_stdout = [] if _OBSFORGE_OWNS_STDOUT else ["console"]
_APP_HANDLERS = list(_stdout)
_AUDIT_HANDLERS = list(_stdout)
if LOG_DIR:
    _LOG_HANDLERS["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(Path(LOG_DIR) / "app.log"),
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 10,
        "formatter": "json",
        "encoding": "utf-8",
    }
    _LOG_HANDLERS["audit_file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(Path(LOG_DIR) / "audit.log"),
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 20,
        "formatter": "json",
        "encoding": "utf-8",
    }
    _APP_HANDLERS += ["file"]
    _AUDIT_HANDLERS += ["file", "audit_file"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "config.logging_utils.JsonFormatter"},
    },
    "handlers": _LOG_HANDLERS,
    "loggers": {
        "django": {"handlers": _APP_HANDLERS, "level": env("DJANGO_LOG_LEVEL", default="INFO"), "propagate": True},
        "django.request": {"handlers": _APP_HANDLERS, "level": "WARNING", "propagate": True},
        "django.server": {"handlers": _APP_HANDLERS, "level": "WARNING", "propagate": True},
        "certmanager": {"handlers": _APP_HANDLERS, "level": "INFO", "propagate": True},
        "certmanager.audit": {"handlers": _AUDIT_HANDLERS, "level": "INFO", "propagate": True},
        # gunicorn: enrutar sus logs por el mismo pipeline (propagate al root ->
        # obsforge) en vez de su texto plano por defecto. Requiere arrancar gunicorn
        # con --access-logfile - (ver README) para que el access log pase por aquí.
        "gunicorn.error": {"handlers": _APP_HANDLERS, "level": "INFO", "propagate": True},
        "gunicorn.access": {"handlers": _APP_HANDLERS, "level": "INFO", "propagate": True},
    },
}

from config.observability import configure_obsforge  # noqa: E402

configure_obsforge()
