"""El runner usa los parámetros de Monitoreo de OrganizationSettings (timeout/reintentos)."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.certificates.models import Certificate
from apps.core.enums import CertificateStatus
from apps.core.models import OrganizationSettings
from apps.monitoring import runner
from apps.monitoring.services import CheckResult
from apps.teams.models import Team

User = get_user_model()


class RunnerConfigTests(TestCase):
    def setUp(self):
        u = User.objects.create(email="o@x.test", is_owner=True)
        team = Team.objects.create(name="T", created_by=u)
        self.cert = Certificate.objects.create(domain="x.test", port=443, team=team, created_by=u)

    def _fake_checker(self, *, ok, counter=None, captured=None):
        class FakeChecker:
            def __init__(_self, timeout=None, allow_legacy_renegotiation=None):
                if captured is not None:
                    captured["timeout"] = timeout

            def check(_self, *a, **k):
                if counter is not None:
                    counter["n"] += 1
                status = CertificateStatus.VIGENTE if ok else CertificateStatus.ERROR
                return CheckResult(ok=ok, status=status, error_message="" if ok else "fail")
        return FakeChecker

    def test_uses_org_connect_timeout(self):
        org = OrganizationSettings.load()
        org.connect_timeout = 7
        org.save()
        captured = {}
        with mock.patch.object(runner, "SSLChecker", self._fake_checker(ok=True, captured=captured)):
            runner.run_check(self.cert, notify=False)
        self.assertEqual(captured["timeout"], 7)

    def test_retries_on_failure(self):
        org = OrganizationSettings.load()
        org.retries = 3
        org.save()
        counter = {"n": 0}
        with mock.patch.object(runner, "SSLChecker", self._fake_checker(ok=False, counter=counter)):
            runner.run_check(self.cert, notify=False)
        self.assertEqual(counter["n"], 3)  # 3 intentos ante fallo

    def test_no_retry_on_success(self):
        org = OrganizationSettings.load()
        org.retries = 3
        org.save()
        counter = {"n": 0}
        with mock.patch.object(runner, "SSLChecker", self._fake_checker(ok=True, counter=counter)):
            runner.run_check(self.cert, notify=False)
        self.assertEqual(counter["n"], 1)  # éxito al primer intento -> no reintenta
