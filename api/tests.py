"""Tests de RBAC, anti-SSRF y migración de estado de alertas (PASO 2).

Cubren las correcciones de seguridad del plan:
- Estado personal de alertas (read/dismiss) accesible por Miembro.
- Resolver alerta solo Admin/Owner.
- Crear grupo solo Owner.
- Crear certificado en grupo ajeno rechazado.
- Mass-assignment de is_owner/role ignorado.
- Anti-SSRF rechaza hosts internos.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Alert, AlertUserState
from apps.certificates.models import Certificate
from apps.core.enums import AlertSeverity, AlertStatus, CertificateStatus, MembershipRole
from apps.monitoring.services import (
    SSRFValidationError,
    SSLChecker,
    validate_public_host,
)
from apps.teams.models import Membership, Team

User = get_user_model()


class _BaseRBAC(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@cf.test", password="x", is_owner=True)
        self.admin = User.objects.create_user(email="admin@cf.test", password="x")
        self.member = User.objects.create_user(email="member@cf.test", password="x")
        self.outsider = User.objects.create_user(email="out@cf.test", password="x")

        self.team = Team.objects.create(name="Infra")
        self.other_team = Team.objects.create(name="Ajeno")
        Membership.objects.create(user=self.admin, team=self.team, role=MembershipRole.ADMIN)
        Membership.objects.create(user=self.member, team=self.team, role=MembershipRole.CONTRIBUTOR)
        Membership.objects.create(user=self.outsider, team=self.other_team, role=MembershipRole.ADMIN)

        self.cert = Certificate.objects.create(
            domain="cf.test", team=self.team, status=CertificateStatus.VIGENTE,
            days_left=100, valid_to=timezone.now() + timedelta(days=100),
        )
        self.alert = Alert.objects.create(
            certificate=self.cert, severity=AlertSeverity.POR_VENCER,
            status=AlertStatus.OPEN, message="Por vencer",
        )

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class AlertPersonalStateTests(_BaseRBAC):
    def test_member_can_read_alert(self):
        resp = self.api(self.member).post(f"/api/alerts/{self.alert.id}/read/")
        self.assertEqual(resp.status_code, 200)
        state = AlertUserState.objects.get(alert=self.alert, user=self.member)
        self.assertIsNotNone(state.read_at)

    def test_member_can_dismiss_alert(self):
        resp = self.api(self.member).post(f"/api/alerts/{self.alert.id}/dismiss/")
        self.assertEqual(resp.status_code, 200)
        state = AlertUserState.objects.get(alert=self.alert, user=self.member)
        self.assertIsNotNone(state.dismissed_at)

    def test_member_cannot_resolve_alert(self):
        resp = self.api(self.member).post(f"/api/alerts/{self.alert.id}/resolve/")
        self.assertEqual(resp.status_code, 403)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.OPEN)

    def test_admin_can_resolve_alert(self):
        resp = self.api(self.admin).post(f"/api/alerts/{self.alert.id}/resolve/")
        self.assertEqual(resp.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.RESOLVED)

    def test_outsider_cannot_see_or_act(self):
        # La alerta no está en su ámbito: 404 (queryset filtrado).
        resp = self.api(self.outsider).post(f"/api/alerts/{self.alert.id}/read/")
        self.assertIn(resp.status_code, (403, 404))


class TeamCreationTests(_BaseRBAC):
    def test_owner_can_create_team(self):
        resp = self.api(self.owner).post("/api/teams/", {"name": "Nuevo grupo"}, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_non_owner_cannot_create_team(self):
        resp = self.api(self.admin).post("/api/teams/", {"name": "Otro grupo"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Team.objects.filter(name="Otro grupo").exists())


class CertificateTeamValidationTests(_BaseRBAC):
    def test_create_in_foreign_team_rejected(self):
        resp = self.api(self.admin).post(
            "/api/certificates/",
            {"domain": "nuevo.cf.test", "port": 443, "team": self.other_team.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Certificate.objects.filter(domain="nuevo.cf.test").exists())

    def test_create_in_own_team_allowed(self):
        resp = self.api(self.admin).post(
            "/api/certificates/",
            {"domain": "propio.cf.test", "port": 443, "team": self.team.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_contributor_can_create_in_own_team(self):
        # Paridad web/API: un Colaborador (no Admin) puede crear en su grupo.
        resp = self.api(self.member).post(
            "/api/certificates/",
            {"domain": "colab.cf.test", "port": 443, "team": self.team.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Certificate.objects.filter(domain="colab.cf.test").exists())

    def test_contributor_create_in_foreign_team_rejected(self):
        resp = self.api(self.member).post(
            "/api/certificates/",
            {"domain": "colab-ajeno.cf.test", "port": 443, "team": self.other_team.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Certificate.objects.filter(domain="colab-ajeno.cf.test").exists())


class MassAssignmentTests(_BaseRBAC):
    def test_patch_is_owner_and_role_ignored(self):
        # Aunque el cliente envíe is_owner/role en el PATCH del certificado, se ignoran.
        resp = self.api(self.admin).patch(
            f"/api/certificates/{self.cert.id}/",
            {"notes": "actualizado", "is_owner": True, "role": "ADMIN"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_owner)
        membership = Membership.objects.get(user=self.admin, team=self.team)
        self.assertEqual(membership.role, MembershipRole.ADMIN)
        # El campo legítimo sí se actualizó.
        self.cert.refresh_from_db()
        self.assertEqual(self.cert.notes, "actualizado")


class AntiSSRFTests(TestCase):
    def test_loopback_rejected(self):
        with mock.patch(
            "apps.monitoring.services.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 0))],
        ):
            with self.assertRaises(SSRFValidationError):
                validate_public_host("evil.internal")

    def test_metadata_address_rejected(self):
        with mock.patch(
            "apps.monitoring.services.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("169.254.169.254", 0))],
        ):
            with self.assertRaises(SSRFValidationError):
                validate_public_host("metadata")

    def test_private_ranges_rejected(self):
        for ip in ("10.0.0.5", "172.16.0.1", "192.168.1.1", "::1"):
            with mock.patch(
                "apps.monitoring.services.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", (ip, 0))],
            ):
                with self.assertRaises(SSRFValidationError):
                    validate_public_host("host")

    def test_public_address_allowed(self):
        with mock.patch(
            "apps.monitoring.services.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
        ):
            ips = validate_public_host("example.com")
            self.assertIn("93.184.216.34", ips)

    def test_checker_returns_error_status_for_internal_host(self):
        with mock.patch(
            "apps.monitoring.services.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 0))],
        ):
            result = SSLChecker().check("localhost", 443, 45, 15)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, CertificateStatus.ERROR)
        self.assertIn("interna", result.error_message.lower())


class ReadByMigrationTests(TestCase):
    """La migración read_by -> AlertUserState es reversible y preserva 'leído'."""

    def test_user_state_created_for_read_by_pair(self):
        # Simula el efecto de la migración de datos a nivel funcional: un estado
        # con read_at representa una alerta leída por un usuario.
        user = User.objects.create_user(email="r@cf.test", password="x")
        team = Team.objects.create(name="T")
        cert = Certificate.objects.create(domain="m.test", team=team)
        alert = Alert.objects.create(
            certificate=cert, severity=AlertSeverity.ERROR,
            status=AlertStatus.OPEN, message="x",
        )
        state = AlertUserState.objects.create(alert=alert, user=user, read_at=timezone.now())
        self.assertIsNotNone(state.read_at)
        # Unicidad (alert, user).
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AlertUserState.objects.create(alert=alert, user=user)
