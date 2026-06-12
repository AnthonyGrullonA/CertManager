"""Serializers DRF de CertForge (fase 1: lectura + acciones núcleo)."""
from rest_framework import serializers

from apps.alerts.models import Alert
from apps.certificates.models import Certificate, CertificateCheck, CertificateRecipient
from apps.core.enums import MembershipRole
from apps.teams.models import Team

from .permissions import WRITE_CERT_ROLES, user_team_ids


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = [
            "id", "name", "slug", "description",
            "default_threshold_days", "default_critical_days",
            "notify_platform", "notify_email", "notify_webhook",
        ]


class RecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateRecipient
        fields = ["id", "email", "user"]


class CertificateSerializer(serializers.ModelSerializer):
    recipients = RecipientSerializer(many=True, read_only=True)
    effective_threshold = serializers.IntegerField(read_only=True)
    effective_critical = serializers.IntegerField(read_only=True)

    def validate_team(self, team):
        """Rechaza crear/editar un certificado en un grupo donde no puede editar.

        Owner puede usar cualquier grupo; el resto, solo grupos donde es
        Colaborador o Admin (crear/editar certificados es escritura del grupo).
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None:
            return team
        if getattr(user, "is_owner", False):
            return team
        editable_team_ids = user_team_ids(user, roles=WRITE_CERT_ROLES)
        if team.id not in editable_team_ids:
            raise serializers.ValidationError(
                "No tienes permiso para asignar el certificado a este grupo "
                "(requiere ser Colaborador o Admin)."
            )
        return team

    class Meta:
        model = Certificate
        fields = [
            "id", "domain", "port", "team", "is_active",
            "alert_threshold_days", "critical_threshold_days",
            "effective_threshold", "effective_critical",
            "notify_platform", "notify_email", "notify_webhook",
            "tags", "notes",
            "status", "days_left", "valid_from", "valid_to",
            "issuer", "subject", "last_checked_at", "next_check_at", "last_error",
            "recipients",
        ]
        read_only_fields = [
            "status", "days_left", "valid_from", "valid_to",
            "issuer", "subject", "last_checked_at", "next_check_at", "last_error",
        ]


class CertificateCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateCheck
        fields = [
            "id", "checked_at", "status", "days_left",
            "valid_from", "valid_to", "issuer", "subject",
            "serial", "fingerprint_sha256", "signature_algorithm", "key_size",
            "san", "chain", "error_message", "latency_ms",
        ]


class AlertSerializer(serializers.ModelSerializer):
    certificate_domain = serializers.CharField(source="certificate.domain", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id", "certificate", "certificate_domain",
            "severity", "status", "message",
            "resolved_at", "snoozed_until", "created_at",
        ]
