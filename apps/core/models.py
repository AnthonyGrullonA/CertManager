"""Modelos base y configuración global de la organización."""
import hashlib
import secrets

from django.conf import settings
from django.db import models

from .enums import ApiKeyScope


class TimeStampedModel(models.Model):
    """Base abstracta con marcas de tiempo de creación/actualización."""

    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        abstract = True


class OrganizationSettings(TimeStampedModel):
    """Configuración global (singleton). Acceso vía OrganizationSettings.load()."""

    org_name = models.CharField("Nombre de la organización", max_length=120, default="CertManager")
    timezone = models.CharField("Zona horaria", max_length=64, default="America/Santo_Domingo")
    default_language = models.CharField("Idioma", max_length=10, default="es-do")

    # SMTP (sustituye credenciales hardcodeadas del legacy). El password se
    # almacena aquí pero nunca se expone en claro en la UI.
    smtp_host = models.CharField("SMTP host", max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField("SMTP puerto", default=587)
    smtp_user = models.CharField("SMTP usuario", max_length=255, blank=True)
    smtp_password = models.CharField("SMTP password", max_length=255, blank=True)
    smtp_from = models.EmailField("Remitente", blank=True)
    smtp_use_tls = models.BooleanField("Usar TLS", default=True)
    email_copy_enabled = models.BooleanField("Enviar copia global", default=False)
    email_copy_address = models.EmailField(
        "Correo de copia global",
        blank=True,
        default="",
    )

    # Monitoreo
    check_interval_hours = models.PositiveIntegerField("Intervalo de chequeo (horas)", default=24)
    connect_timeout = models.PositiveIntegerField("Timeout de conexión (s)", default=10)
    retries = models.PositiveIntegerField("Reintentos", default=1)
    # Ventana horaria preferida para ejecutar los chequeos (cron). Null = sin restricción.
    preferred_check_window_start = models.TimeField("Ventana de chequeo (inicio)", null=True, blank=True)
    preferred_check_window_end = models.TimeField("Ventana de chequeo (fin)", null=True, blank=True)

    # Organización / marca
    account_domain = models.CharField("Dominio de la cuenta", max_length=253, blank=True)
    logo = models.ImageField("Logo", upload_to="org/", null=True, blank=True)

    # Seguridad
    password_min_length = models.PositiveIntegerField("Longitud mínima de contraseña", default=8)
    require_2fa = models.BooleanField("Exigir 2FA", default=False)  # placeholder/diferido
    session_timeout = models.PositiveIntegerField("Timeout de sesión (min)", default=0)
    # Expiración de contraseñas (OWASP A07). Apagado por defecto: cuando se activa,
    # los usuarios con contraseña local más vieja que `password_expiry_days` deben
    # cambiarla antes de seguir usando la app (lo fuerza PasswordExpiryMiddleware).
    password_expiry_enabled = models.BooleanField("Expirar contraseñas", default=False)
    password_expiry_days = models.PositiveIntegerField("Vigencia de contraseña (días)", default=90)
    sso_enabled = models.BooleanField("SSO habilitado", default=False)
    ldap_enabled = models.BooleanField("LDAP habilitado", default=False)

    class Meta:
        verbose_name = "Configuración de la organización"
        verbose_name_plural = "Configuración de la organización"

    def __str__(self):
        return self.org_name

    def save(self, *args, **kwargs):
        # Forzar un único registro (pk=1).
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ApiKey(TimeStampedModel):
    """Clave de API para autenticar consumidores externos de la API REST.

    Solo se almacena el **hash** de la clave (nunca el secreto en claro): la clave
    completa se muestra UNA sola vez al crearla. El prefijo visible indica el
    ámbito: ``cf_live_`` (acceso total) o ``cf_ro_`` (solo lectura).
    """

    name = models.CharField("Nombre", max_length=120)
    scope = models.CharField("Ámbito", max_length=10, choices=ApiKeyScope.choices, default=ApiKeyScope.READ_ONLY)
    prefix = models.CharField("Prefijo", max_length=12, editable=False)
    # Identificador público corto (para mostrar/buscar sin exponer el secreto).
    key_id = models.CharField("ID público", max_length=24, unique=True, editable=False)
    hashed_key = models.CharField("Hash de la clave", max_length=64, editable=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    is_active = models.BooleanField("Activa", default=True)
    last_used_at = models.DateTimeField("Último uso", null=True, blank=True)

    class Meta:
        verbose_name = "Clave de API"
        verbose_name_plural = "Claves de API"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.key_id}…)"

    @staticmethod
    def _hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def generate(cls, *, name, scope, user):
        """Crea una clave y devuelve (instancia, clave_en_claro). Mostrar la clave una vez."""
        prefix = "cf_live" if scope == ApiKeyScope.FULL else "cf_ro"
        secret = secrets.token_urlsafe(32)
        raw = f"{prefix}_{secret}"
        obj = cls.objects.create(
            name=name,
            scope=scope,
            prefix=prefix,
            key_id=raw[: 16],
            hashed_key=cls._hash(raw),
            created_by=user,
        )
        return obj, raw

    @classmethod
    def lookup(cls, raw: str):
        """Devuelve la ApiKey activa que corresponde a la clave en claro, o None."""
        if not raw:
            return None
        return cls.objects.filter(hashed_key=cls._hash(raw), is_active=True).first()

    @property
    def is_read_only(self):
        return self.scope == ApiKeyScope.READ_ONLY


class ApiKeyUsage(models.Model):
    """Registro de uso de una API key (una fila por petición autenticada)."""

    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name="usages")
    at = models.DateTimeField("Fecha", auto_now_add=True)
    method = models.CharField("Método", max_length=8)
    path = models.CharField("Ruta", max_length=255)
    status_code = models.PositiveIntegerField("Código", null=True, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)

    class Meta:
        verbose_name = "Uso de API key"
        verbose_name_plural = "Uso de API keys"
        ordering = ["-at"]
        indexes = [models.Index(fields=["api_key", "-at"])]

    def __str__(self):
        return f"{self.method} {self.path} ({self.status_code})"


class LdapConfiguration(TimeStampedModel):
    """Configuración LDAP corporativa, almacenada en BD (singleton).

    La edita el Owner en Configuración. El backend de autenticación
    (apps.accounts.ldap_backend.DatabaseLDAPBackend) lee de aquí. Solo verifica la
    contraseña de usuarios que YA existen localmente (no crea cuentas).
    """

    enabled = models.BooleanField("LDAP habilitado", default=False)
    server_uri = models.CharField("Servidor (URI)", max_length=255, blank=True,
                                  help_text="ej. ldap://dc.ejemplo.local:389 o ldaps://dc:636")
    use_ssl = models.BooleanField("Usar SSL (ldaps)", default=False)
    start_tls = models.BooleanField("Usar StartTLS", default=False)

    # Cuenta de servicio para buscar el DN del usuario que inicia sesión.
    bind_dn = models.CharField("Bind DN (cuenta de servicio)", max_length=255, blank=True)
    bind_password = models.CharField("Bind password", max_length=255, blank=True)

    user_search_base = models.CharField("Base de búsqueda de usuarios", max_length=255, blank=True,
                                        help_text="ej. OU=Usuarios,DC=claro,DC=com,DC=do")
    user_filter = models.CharField("Filtro de usuario", max_length=255, blank=True,
                                   default="(mail={login})",
                                   help_text="Usa {login} como marcador. ej. (mail={login}) o (sAMAccountName={login})")
    email_attribute = models.CharField("Atributo de correo", max_length=64, default="mail")
    connect_timeout = models.PositiveIntegerField("Timeout (s)", default=8)

    last_test_at = models.DateTimeField("Última prueba", null=True, blank=True)
    last_test_ok = models.BooleanField("Última prueba OK", null=True, blank=True)
    last_test_message = models.CharField("Resultado de la última prueba", max_length=300, blank=True)

    class Meta:
        verbose_name = "Configuración LDAP"
        verbose_name_plural = "Configuración LDAP"

    def __str__(self):
        return f"LDAP {'habilitado' if self.enabled else 'deshabilitado'}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SmsGatewayConfig(TimeStampedModel):
    """Config del gateway SMS por FTP (legacy). Migrado pero desactivado por defecto."""

    enabled = models.BooleanField("SMS habilitado", default=False)
    ftp_host = models.CharField("Host FTP", max_length=255, blank=True)
    ftp_user = models.CharField("Usuario FTP", max_length=128, blank=True)
    ftp_password = models.CharField("Password FTP", max_length=255, blank=True)
    default_number = models.CharField("Número por defecto", max_length=32, blank=True)
    remote_filename = models.CharField("Archivo remoto", max_length=64, default="sms.log")

    class Meta:
        verbose_name = "Gateway SMS (FTP)"
        verbose_name_plural = "Gateway SMS (FTP)"

    def __str__(self):
        return f"SMS {'habilitado' if self.enabled else 'deshabilitado'}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AuditLog(models.Model):
    """Registro inmutable de acciones sobre recursos sensibles (OWASP A09).

    Append-only: no se edita ni se borra desde la app. Guarda actor (FK + email
    denormalizado por si el usuario se elimina), acción, modelo/objeto afectado,
    un diff opcional y la IP de origen.
    """

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGIN_LOCKED = "login_locked"
    LOGOUT = "logout"

    created_at = models.DateTimeField("Cuándo", auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    actor_email = models.CharField("Actor (email)", max_length=254, blank=True)
    action = models.CharField("Acción", max_length=32, db_index=True)
    model = models.CharField("Modelo", max_length=64, blank=True, db_index=True)
    object_id = models.CharField("ID objeto", max_length=64, blank=True)
    object_repr = models.CharField("Objeto", max_length=255, blank=True)
    changes = models.JSONField("Cambios", default=dict, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-created_at"]

    def __str__(self):
        who = self.actor_email or "sistema"
        return f"{who} · {self.action} {self.model} {self.object_repr}".strip()
