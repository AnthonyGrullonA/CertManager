"""Modelos del dominio de certificados: Certificate, Recipient e historial Check."""
from django.conf import settings
from django.db import models

from apps.core.enums import CertificateStatus
from apps.core.models import TimeStampedModel
from apps.teams.models import Team


class CertificateQuerySet(models.QuerySet):
    def for_user(self, user):
        """Certificados visibles para el usuario (Owner: todos; resto: grupo dueño
        O grupos adicionales). ``distinct`` evita duplicados por el JOIN del M2M."""
        if getattr(user, "is_owner", False):
            return self
        team_ids = list(user.memberships.values_list("team_id", flat=True))
        return self.filter(
            models.Q(team_id__in=team_ids) | models.Q(groups__in=team_ids)
        ).distinct()


class Certificate(TimeStampedModel):
    """Un host:puerto a monitorear, perteneciente a un grupo.

    Los campos `last_*`/`status`/`days_left` están denormalizados desde el
    último CertificateCheck para listar sin joins. La fuente de verdad del
    historial es CertificateCheck.
    """

    # --- Identidad ---
    domain = models.CharField("Dominio / host", max_length=253)
    port = models.PositiveIntegerField("Puerto", default=443)
    # Ubicación física/lógica del servicio (p.ej. "Servidor", "netscaler"). Texto
    # libre; el importador la deriva del dominio pero se puede editar.
    location = models.CharField("Ubicación", max_length=120, blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="certificates")
    # Grupos ADICIONALES de gestión/visualización (además del dueño `team`). M2M
    # aditivo: no cambia la unicidad (team, domain, port) ni el dueño.
    groups = models.ManyToManyField(
        Team, blank=True, related_name="shared_certificates",
        verbose_name="Grupos adicionales",
    )
    is_active = models.BooleanField("Activo", default=True)
    # Silenciar alertas temporalmente (snooze): hasta esta fecha no se notifica.
    snoozed_until = models.DateTimeField("Silenciado hasta", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certificates_created",
    )

    # --- Configuración de alerta (null => hereda del grupo) ---
    alert_threshold_days = models.PositiveIntegerField("Umbral de alerta (días)", null=True, blank=True)
    critical_threshold_days = models.PositiveIntegerField("Umbral crítico (días)", null=True, blank=True)
    notify_platform = models.BooleanField("Alertar en plataforma", null=True, blank=True)
    notify_email = models.BooleanField("Alertar por correo", null=True, blank=True)
    notify_webhook = models.BooleanField("Alertar por webhook", null=True, blank=True)
    notify_sms = models.BooleanField("Alertar por SMS", null=True, blank=True)

    # Plantilla de correo (kind=CERT) para las notificaciones de este cert. Si es
    # null, se usa la plantilla predeterminada del tipo o el texto plano actual.
    email_template = models.ForeignKey(
        "mailtemplates.EmailTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    tags = models.JSONField("Etiquetas", default=list, blank=True)
    notes = models.TextField("Notas", blank=True)

    # --- Denormalizado del último chequeo ---
    status = models.CharField(
        "Estado",
        max_length=15,
        choices=CertificateStatus.choices,
        default=CertificateStatus.SIN_CHEQUEAR,
    )
    days_left = models.IntegerField("Días restantes", null=True, blank=True)
    valid_from = models.DateTimeField("Válido desde", null=True, blank=True)
    valid_to = models.DateTimeField("Válido hasta", null=True, blank=True)
    issuer = models.CharField("Emisor", max_length=255, blank=True)
    subject = models.CharField("Sujeto", max_length=255, blank=True)
    last_checked_at = models.DateTimeField("Último chequeo", null=True, blank=True)
    next_check_at = models.DateTimeField("Próximo chequeo", null=True, blank=True)
    last_error = models.TextField("Último error", blank=True)
    last_check = models.ForeignKey(
        "CertificateCheck",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = CertificateQuerySet.as_manager()

    class Meta:
        verbose_name = "Certificado"
        verbose_name_plural = "Certificados"
        ordering = ["domain"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "domain", "port"],
                name="unique_team_domain_port",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["valid_to"]),
        ]

    def __str__(self):
        return f"{self.domain}:{self.port}"

    # --- Resolución de herencia grupo -> certificado ---
    @property
    def effective_threshold(self):
        if self.alert_threshold_days is not None:
            return self.alert_threshold_days
        return self.team.default_threshold_days

    @property
    def effective_critical(self):
        if self.critical_threshold_days is not None:
            return self.critical_threshold_days
        return self.team.default_critical_days

    @property
    def is_snoozed(self) -> bool:
        """True si las alertas están silenciadas (snooze vigente)."""
        from django.utils import timezone

        return bool(self.snoozed_until and self.snoozed_until > timezone.now())

    @property
    def effective_channels(self):
        """Devuelve dict con los canales efectivos (cert override o default del grupo)."""
        def resolve(cert_val, team_val):
            return team_val if cert_val is None else cert_val

        return {
            "platform": resolve(self.notify_platform, self.team.notify_platform),
            "email": resolve(self.notify_email, self.team.notify_email),
            "webhook": resolve(self.notify_webhook, self.team.notify_webhook),
            "sms": resolve(self.notify_sms, self.team.notify_sms),
        }

    @property
    def validity_percent(self):
        """Porcentaje (0..100) del periodo de validez ya consumido respecto a ahora.

        100 = recién emitido (queda todo el periodo); 0 = vencido o sin periodo
        consumido restante. Sin fechas válidas devuelve None. Se hace clamp a
        [0, 100] para tolerar relojes desfasados o fechas inconsistentes.
        """
        from django.utils import timezone

        if not self.valid_from or not self.valid_to:
            return None
        total = (self.valid_to - self.valid_from).total_seconds()
        if total <= 0:
            return 0
        remaining = (self.valid_to - timezone.now()).total_seconds()
        pct = (remaining / total) * 100
        return int(max(0, min(100, round(pct))))

    @property
    def all_recipients(self):
        """Correos a notificar: los del certificado o, si no hay, los del grupo."""
        emails = list(self.recipients.values_list("email", flat=True))
        return emails or list(self.team.default_recipients or [])


class CertificateRecipient(TimeStampedModel):
    """Destinatario de notificación de un certificado (correo, opcionalmente un usuario)."""

    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name="recipients",
    )
    email = models.EmailField("Correo")
    alert_threshold_days = models.PositiveIntegerField(
        "Umbral legacy (días)",
        null=True,
        blank=True,
        help_text="Umbral original asociado a este correo en certapp_old.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cert_subscriptions",
    )

    class Meta:
        verbose_name = "Destinatario"
        verbose_name_plural = "Destinatarios"
        constraints = [
            models.UniqueConstraint(
                fields=["certificate", "email"],
                name="unique_certificate_email",
            ),
        ]

    def __str__(self):
        return f"{self.email} ({self.certificate})"


class CertificateCheck(TimeStampedModel):
    """Registro histórico de un chequeo. Fuente de verdad de la evolución."""

    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name="checks",
    )
    checked_at = models.DateTimeField("Fecha de chequeo")
    status = models.CharField("Estado", max_length=15, choices=CertificateStatus.choices)
    days_left = models.IntegerField("Días restantes", null=True, blank=True)

    valid_from = models.DateTimeField("Válido desde", null=True, blank=True)
    valid_to = models.DateTimeField("Válido hasta", null=True, blank=True)
    issuer = models.CharField("Emisor", max_length=255, blank=True)
    subject = models.CharField("Sujeto", max_length=255, blank=True)

    # Detalles técnicos
    serial = models.CharField("Número de serie", max_length=128, blank=True)
    fingerprint_sha256 = models.CharField("Fingerprint SHA-256", max_length=95, blank=True)
    signature_algorithm = models.CharField("Algoritmo de firma", max_length=64, blank=True)
    key_size = models.PositiveIntegerField("Tamaño de clave", null=True, blank=True)
    san = models.JSONField("SAN (dominios alternos)", default=list, blank=True)
    chain = models.JSONField("Cadena de confianza", default=list, blank=True)

    error_message = models.TextField("Error", blank=True)
    latency_ms = models.PositiveIntegerField("Latencia (ms)", null=True, blank=True)

    class Meta:
        verbose_name = "Chequeo"
        verbose_name_plural = "Chequeos"
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["certificate", "-checked_at"]),
        ]

    def __str__(self):
        return f"{self.certificate} @ {self.checked_at:%Y-%m-%d %H:%M} ({self.status})"
