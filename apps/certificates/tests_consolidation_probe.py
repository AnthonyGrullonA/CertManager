"""Probe tests to confirm/refute the consolidation findings empirically."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.certificates.forms import CertificateForm
from apps.certificates.models import Certificate
from apps.core.enums import MembershipRole as R
from apps.teams.models import Membership, Team

U = get_user_model()


class EditDataLossProbe(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.A = Team.objects.create(name="A")  # owner group
        cls.B = Team.objects.create(name="B")  # additional, user is contributor
        cls.C = Team.objects.create(name="C")  # additional, user has NO access
        cls.cert = Certificate.objects.create(team=cls.A, domain="x.example.com", port=443)
        cls.cert.groups.add(cls.B, cls.C)

        # User U: VIEWER in A, CONTRIBUTOR in B, no access to C
        cls.user = U.objects.create_user(email="u@x.io", password="x")
        Membership.objects.create(user=cls.user, team=cls.A, role=R.VIEWER)
        Membership.objects.create(user=cls.user, team=cls.B, role=R.CONTRIBUTOR)

    def test_edit_drops_group_C(self):
        """Simulate the contributor-in-B editing the cert and submitting groups=[B]."""
        before = set(self.cert.groups.values_list("id", flat=True))
        self.assertEqual(before, {self.B.id, self.C.id})

        form = CertificateForm(
            {
                "domain": "x.example.com",
                "port": 443,
                "team": self.A.id,
                "alert_threshold_days": 30,
                "groups": [self.B.id],  # form only offers B; C not in queryset
            },
            instance=self.cert,
            user=self.user,
        )
        # team A: user is VIEWER => can_edit_certs(A) is False => form invalid?
        valid = form.is_valid()
        print("FORM VALID:", valid, "ERRORS:", dict(form.errors))
        if valid:
            form.save()
            self.cert.refresh_from_db()
            after = set(self.cert.groups.values_list("id", flat=True))
            print("GROUPS AFTER:", after)

    def test_edit_owned_by_B_contributor(self):
        """Cert OWNED by B (so user can edit via team), shared with C the user can't see."""
        cert = Certificate.objects.create(team=self.B, domain="y.example.com", port=443)
        cert.groups.add(self.C)
        form = CertificateForm(
            {
                "domain": "y.example.com",
                "port": 443,
                "team": self.B.id,
                "alert_threshold_days": 30,
                "groups": [],  # user re-submits without C (C not visible)
            },
            instance=cert,
            user=self.user,
        )
        valid = form.is_valid()
        print("FORM2 VALID:", valid, "ERRORS:", dict(form.errors))
        if valid:
            form.save()
            cert.refresh_from_db()
            after = set(cert.groups.values_list("id", flat=True))
            print("GROUPS2 AFTER (expected {C} if no data loss):", after, "C.id=", self.C.id)
