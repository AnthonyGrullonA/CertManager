"""Usuario custom de CertManager: login por email + rol global Owner."""
import hashlib

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.core.models import TimeStampedModel

from .managers import UserManager


class User(AbstractUser):
    """Usuario con email como identificador y rol global opcional Owner.

    Los roles por grupo (Admin/Miembro) viven en teams.Membership, no aquí.
    """

    username = None  # se reemplaza por email
    email = models.EmailField("Correo", unique=True)

    # Rol global: el Owner ve y gestiona todo (todos los grupos, usuarios, config).
    is_owner = models.BooleanField(
        "Owner global",
        default=False,
        help_text="Acceso total: gestiona grupos, usuarios y certificados de toda la organización.",
    )

    # Sello del último cambio de contraseña: base de la política de expiración
    # (OrganizationSettings.password_expiry_*). Null en usuarios previos a la
    # política -> se cae a date_joined (ver password_age).
    password_changed_at = models.DateTimeField(
        "Contraseña cambiada", null=True, blank=True
    )

    # Activo tras un reset del Owner: la contraseña vigente es temporal y el
    # middleware fuerza a definir una propia antes de seguir usando la app.
    must_change_password = models.BooleanField(
        "Debe cambiar contraseña", default=False
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ["email"]

    def __str__(self):
        full = self.get_full_name()
        return full or self.email

    def set_password(self, raw_password):
        super().set_password(raw_password)
        # Sella el momento del cambio para la política de expiración (OWASP A07).
        # set_password siempre va seguido de save() en los flujos de la app.
        self.password_changed_at = timezone.now()

    def password_age(self):
        """``timedelta`` desde el último cambio de contraseña.

        Si nunca se registró (usuario previo a la política), cae a ``date_joined``.
        Devuelve None si tampoco hay alta (caso degenerado).
        """
        ref = self.password_changed_at or self.date_joined
        if ref is None:
            return None
        return timezone.now() - ref

    def password_expired(self, org=None):
        """True si la organización exige expiración y la contraseña local venció.

        Exime a usuarios sin contraseña local usable (LDAP/SSO): su credencial no
        se gestiona aquí, así que no tiene sentido forzar un cambio local.
        """
        from apps.core.models import OrganizationSettings

        org = org or OrganizationSettings.load()
        if not org.password_expiry_enabled:
            return False
        if not self.has_usable_password():
            return False
        age = self.password_age()
        if age is None:
            return False
        return age.days >= org.password_expiry_days


class UserPreferences(TimeStampedModel):
    """Preferencias personales de un usuario (OneToOne con User).

    `panel_cleared_at` es el sello de "Limpiar todo" del panel de alertas:
    permite ocultar alertas anteriores sin crear N filas de AlertUserState.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    language = models.CharField("Idioma", max_length=10, default="es-do")
    timezone = models.CharField("Zona horaria", max_length=64, default="America/Santo_Domingo")

    # Avatar SVG generado (índice 1..N). Todo usuario nace con uno asignado
    # (determinista por email); 0 solo puede aparecer en datos legados.
    # Evita depender de storage: el SVG se renderiza por índice (1..N).
    avatar_choice = models.PositiveIntegerField("Avatar SVG", default=0)
    panel_cleared_at = models.DateTimeField("Panel limpiado", null=True, blank=True)

    class Meta:
        verbose_name = "Preferencias de usuario"
        verbose_name_plural = "Preferencias de usuario"

    def __str__(self):
        return f"Preferencias de {self.user}"


class TwoFactorDevice(TimeStampedModel):
    """Dispositivo TOTP (2FA) de un usuario. Opcional, auto-enrolado en Perfil.

    El secreto Base32 se guarda al iniciar el enrolamiento; el 2FA queda ACTIVO
    solo cuando ``confirmed_at`` se setea (tras validar el primer código del
    autenticador). Desactivar = borrar el dispositivo.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="totp_device",
    )
    secret = models.CharField("Secreto TOTP (Base32)", max_length=64)
    confirmed_at = models.DateTimeField("Confirmado", null=True, blank=True)

    class Meta:
        verbose_name = "Dispositivo 2FA"
        verbose_name_plural = "Dispositivos 2FA"

    def __str__(self):
        return f"2FA de {self.user} ({'activo' if self.enabled else 'pendiente'})"

    @property
    def enabled(self) -> bool:
        return self.confirmed_at is not None


def default_avatar_choice(email: str) -> int:
    """Avatar SVG por defecto: pseudo-aleatorio pero determinista por email.

    Usa SHA-256 (estable entre procesos; ``hash()`` nativo está salteado por
    PYTHONHASHSEED) y mapea al catálogo ``1..AVATAR_COUNT``. Así nadie queda
    "sin avatar" y migraciones/señales dan el mismo resultado en cualquier
    ambiente.
    """
    # Import perezoso: el catálogo vive en la capa web (templatetag).
    from apps.web.templatetags.forge_avatars import AVATAR_COUNT

    digest = hashlib.sha256((email or "").strip().lower().encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % AVATAR_COUNT + 1


def get_or_create_preferences(user):
    """Helper para obtener (o crear) las preferencias de un usuario."""
    prefs, _ = UserPreferences.objects.get_or_create(
        user=user, defaults={"avatar_choice": default_avatar_choice(user.email)}
    )
    return prefs


def user_has_2fa(user) -> bool:
    """¿El usuario tiene 2FA activo (dispositivo confirmado)?"""
    device = getattr(user, "totp_device", None)
    return bool(device and device.enabled)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_preferences(sender, instance, created, **kwargs):
    """Crea las preferencias por defecto al crear un usuario."""
    if created:
        UserPreferences.objects.get_or_create(
            user=instance,
            defaults={"avatar_choice": default_avatar_choice(instance.email)},
        )
