"""Probe bulk-op RBAC, health bar, webhooks, responsables findings."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.certificates.models import Certificate
from apps.core.enums import MembershipRole as R
from apps.teams.models import Membership, Team
from apps.teams.permissions import can_edit_certs, can_edit_certificate

U = get_user_model()


class BulkAndHealthProbe(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.A = Team.objects.create(name="A")  # owner group
        cls.B = Team.objects.create(name="B")  # additional group
        cls.cert = Certificate.objects.create(team=cls.A, domain="x.example.com", port=443, status="VIGENTE")
        cls.cert.groups.add(cls.B)
        # contributor in B (additional), NOT a member of A
        cls.contrib_b = U.objects.create_user(email="cb@x.io", password="x")
        Membership.objects.create(user=cls.contrib_b, team=cls.B, role=R.CONTRIBUTOR)

    def test_bulk_gate_uses_owner_team_only(self):
        # what bulk currently checks:
        owner_check = can_edit_certs(self.contrib_b, self.cert.team)
        # what it SHOULD check:
        full_check = can_edit_certificate(self.contrib_b, self.cert)
        print("BULK can_edit_certs(owner team) =", owner_check, "| can_edit_certificate =", full_check)

    def test_health_bar_counts_owner_only(self):
        # team B's health bar uses team.certificates (FK only), not shared_certificates
        owned_by_B = self.B.certificates.count()
        shared_with_B = self.B.shared_certificates.count()
        print("HEALTH B owned (FK):", owned_by_B, "| B shared (M2M):", shared_with_B)


class WebhookProbe(TestCase):
    def test_webhooks_only_owner_team(self):
        from apps.alerts.models import WebhookIntegration
        from apps.alerts.services import _webhooks_for
        A = Team.objects.create(name="A")
        B = Team.objects.create(name="B")
        cert = Certificate.objects.create(team=A, domain="x.example.com", port=443)
        cert.groups.add(B)
        WebhookIntegration.objects.create(team=A, url="https://hook-a.example.com/x", is_active=True)
        WebhookIntegration.objects.create(team=B, url="https://hook-b.example.com/x", is_active=True)
        hooks = list(_webhooks_for(cert).values_list("url", flat=True))
        print("WEBHOOKS dispatched for cert (owner A + additional B):", hooks)
