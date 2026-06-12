"""Probe the API scoping findings empirically."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.alerts.models import Alert
from apps.certificates.models import Certificate
from apps.core.enums import AlertSeverity, AlertStatus, MembershipRole as R
from apps.teams.models import Membership, Team

from api.permissions import scope_certificates, IsScopedAlertViewer
from api.views import AlertViewSet

U = get_user_model()


class ApiScopingProbe(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.A = Team.objects.create(name="A")
        cls.B = Team.objects.create(name="B")
        cls.cert = Certificate.objects.create(team=cls.A, domain="x.example.com", port=443)
        cls.cert.groups.add(cls.B)
        cls.alert = Alert.objects.create(
            certificate=cls.cert, severity=AlertSeverity.POR_VENCER,
            status=AlertStatus.OPEN, message="m",
        )
        # contributor in B only (additional group)
        cls.user_b = U.objects.create_user(email="b@x.io", password="x")
        Membership.objects.create(user=cls.user_b, team=cls.B, role=R.CONTRIBUTOR)

    def test_scope_certificates_via_group(self):
        qs = scope_certificates(Certificate.objects.all(), self.user_b)
        visible = qs.filter(pk=self.cert.pk).exists()
        print("API scope_certificates sees cert via group:", visible)

    def test_alert_queryset_via_group(self):
        v = AlertViewSet()
        # emulate get_queryset filter for non-owner
        from api.permissions import user_team_ids
        qs = Alert.objects.filter(certificate__team_id__in=user_team_ids(self.user_b))
        print("API AlertViewSet sees alert via group:", qs.filter(pk=self.alert.pk).exists())

    def test_alert_object_permission_via_group(self):
        class Req:
            method = "GET"
            user = self.user_b
        class V:
            action = "read"
        perm = IsScopedAlertViewer()
        allowed = perm.has_object_permission(Req(), V(), self.alert)
        print("API IsScopedAlertViewer allows read via group:", allowed)
