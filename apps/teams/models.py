"""Grupos (Team) y membresías con rol por grupo."""
from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.core.enums import MembershipRole
from apps.core.models import TimeStampedModel


class TeamQuerySet(models.QuerySet):
    def for_user(self, user):
        """Grupos visibles para el usuario (Owner: todos; resto: sus grupos)."""
        if getattr(user, "is_owner", False):
            return self
        team_ids = user.memberships.values_list("team_id", flat=True)
        return self.filter(id__in=team_ids)


class Team(TimeStampedModel):
    """Grupo organizacional. Contiene certificados y miembros.

    Se muestra como "Grupo" en la UI. Mantiene valores por defecto que los
    certificados heredan (umbral, canales, destinatarios).
    """

    name = models.CharField("Nombre", max_length=120, unique=True)
    slug = models.SlugField("Slug", max_length=140, unique=True, blank=True)
    description = models.TextField("Descripción", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teams_created",
    )

    # Defaults heredables por los certificados del grupo.
    default_threshold_days = models.PositiveIntegerField("Umbral por defecto (días)", default=45)
    default_critical_days = models.PositiveIntegerField("Umbral crítico por defecto (días)", default=15)
    default_check_interval = models.PositiveIntegerField(
        "Intervalo de chequeo por defecto (horas)",
        default=24,
    )
    notify_platform = models.BooleanField("Alertar en plataforma", default=True)
    notify_email = models.BooleanField("Alertar por correo", default=True)
    notify_webhook = models.BooleanField("Alertar por webhook", default=False)
    notify_sms = models.BooleanField("Alertar por SMS", default=False)
    default_recipients = models.JSONField("Destinatarios por defecto", default=list, blank=True)

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Membership",
        related_name="teams",
        blank=True,
    )

    objects = TeamQuerySet.as_manager()

    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)


class Membership(TimeStampedModel):
    """Pertenencia de un usuario a un grupo, con su rol en ese grupo."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(
        "Rol",
        max_length=12,
        choices=MembershipRole.choices,
        default=MembershipRole.VIEWER,
    )

    class Meta:
        verbose_name = "Membresía"
        verbose_name_plural = "Membresías"
        constraints = [
            models.UniqueConstraint(fields=["user", "team"], name="unique_user_team"),
        ]

    def __str__(self):
        return f"{self.user} · {self.team} ({self.get_role_display()})"
