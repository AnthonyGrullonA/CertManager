"""ViewSets DRF de CertForge."""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone

from apps.alerts.models import Alert, AlertUserState
from apps.certificates.models import Certificate
from apps.core.enums import AlertStatus
from apps.monitoring.runner import run_check
from apps.teams.models import Team

from .permissions import (
    ApiKeyScopePermission,
    IsOwnerOrTeamMember,
    IsScopedAlertViewer,
    scope_certificates,
    user_team_ids,
)
from .serializers import (
    AlertSerializer,
    CertificateCheckSerializer,
    CertificateSerializer,
    TeamSerializer,
)


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    permission_classes = [IsOwnerOrTeamMember, ApiKeyScopePermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Team.objects.none()
        user = self.request.user
        if user.is_owner:
            return Team.objects.all()
        return Team.objects.filter(id__in=user_team_ids(user))

    def perform_create(self, serializer):
        # Crear un grupo es una acción global: solo el Owner.
        if not self.request.user.is_owner:
            raise PermissionDenied("Solo el Owner puede crear grupos.")
        serializer.save(created_by=self.request.user)


class CertificateViewSet(viewsets.ModelViewSet):
    serializer_class = CertificateSerializer
    permission_classes = [IsOwnerOrTeamMember, ApiKeyScopePermission]
    filterset_fields = ["status", "team", "is_active"]
    search_fields = ["domain", "issuer", "subject"]
    ordering_fields = ["days_left", "valid_to", "domain"]
    ordering = ["days_left"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Certificate.objects.none()
        return scope_certificates(
            Certificate.objects.select_related("team").prefetch_related("recipients"),
            self.request.user,
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_throttles(self):
        # "Probar ahora" abre conexiones de red: rate-limit con scope 'cert_test'
        # (anti-SSRF/DoS, decisión congelada del plan).
        if getattr(self, "action", None) == "test":
            self.throttle_scope = "cert_test"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Probar ahora: ejecuta un chequeo inmediato y devuelve el resultado."""
        certificate = self.get_object()
        check, result = run_check(certificate, notify=False)
        return Response({
            "ok": result.ok,
            "status": result.status,
            "days_left": result.days_left,
            "issuer": result.issuer,
            "valid_to": result.valid_to,
            "error_message": result.error_message,
            "check": CertificateCheckSerializer(check).data,
        })

    @action(detail=True, methods=["get"])
    def checks(self, request, pk=None):
        """Historial de chequeos del certificado."""
        certificate = self.get_object()
        qs = certificate.checks.all()[:200]
        return Response(CertificateCheckSerializer(qs, many=True).data)


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AlertSerializer
    permission_classes = [IsScopedAlertViewer, ApiKeyScopePermission]
    filterset_fields = ["severity", "status"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Alert.objects.none()
        user = self.request.user
        qs = Alert.objects.select_related("certificate")
        if user.is_owner:
            return qs
        return qs.filter(certificate__team_id__in=user_team_ids(user))

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        """Marca la alerta como leída por el usuario actual (estado personal)."""
        alert = self.get_object()
        state, _ = AlertUserState.objects.get_or_create(alert=alert, user=request.user)
        if state.read_at is None:
            state.read_at = timezone.now()
            state.save(update_fields=["read_at", "updated_at"])
        return Response({"status": "ok"})

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        """Limpia la alerta del panel del usuario (no borra el registro)."""
        alert = self.get_object()
        state, _ = AlertUserState.objects.get_or_create(alert=alert, user=request.user)
        if state.dismissed_at is None:
            state.dismissed_at = timezone.now()
            state.save(update_fields=["dismissed_at", "updated_at"])
        return Response({"status": "ok"})

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Resuelve la alerta (recurso compartido: solo Admin/Owner)."""
        alert = self.get_object()
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=["status", "resolved_at", "updated_at"])
        return Response({"status": "ok"})

    @action(detail=True, methods=["post"])
    def snooze(self, request, pk=None):
        """Pospone la alerta (recurso compartido: solo Admin/Owner)."""
        alert = self.get_object()
        alert.status = AlertStatus.SNOOZED
        alert.save(update_fields=["status", "updated_at"])
        return Response({"status": "ok"})
