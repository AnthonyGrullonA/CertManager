"""Tests del bootstrap de producción (management command data_update_certs_app)."""
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.certificates.models import Certificate
from apps.core.enums import MembershipRole
from apps.core.models import OrganizationSettings
from apps.teams.models import Membership, Team

User = get_user_model()

CERT_TXT = """\
ntpsfens.corp.codetel.com.do|itclienteservidornt@claro.com.do|50|443
ntpsfens.corp.codetel.com.do|adm_middleware@claro.com.do|50|443
sgv.claro.com.do|sp_canales_electronicos@claro.com.do|45|443
api.mi.claro.com.do|sp_canales_electronicos@claro.com.do|60|443
api.mi.claro.com.do|itredes@claro.com.do|60|443
claroump.claro.com.do|sp_ordenes-aprov@claro.com.do|45|443
osbprod2.corp.codetel.com.do|adm_middleware@claro.com.do|45|443
finanzas-a.claro.com.do|sp_adm-finanzas@claro.com.do|45|443
finanzas-b.claro.com.do|sp_adm_finanzas@claro.com.do|45|443
linea-mala-sin-campos
"""


class BootstrapCommandTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        self.tmp.write(CERT_TXT)
        self.tmp.close()
        self.source = self.tmp.name

    def tearDown(self):
        Path(self.source).unlink(missing_ok=True)

    def _run(self, **env):
        with mock.patch.dict("os.environ", env, clear=False):
            call_command("data_update_certs_app", source=self.source, verbosity=0)

    def test_creates_owner_as_app_owner_not_django_admin(self):
        self._run(CF_OWNER_PASSWORD="Ninguna123@")
        u = User.objects.get(email="jairol_grullon@claro.com.do")
        self.assertTrue(u.is_owner)
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)
        self.assertTrue(u.check_password("Ninguna123@"))

    def test_seeds_production_config_defaults(self):
        self._run(CF_OWNER_PASSWORD="x")
        org = OrganizationSettings.load()
        self.assertEqual(org.check_interval_hours, 24)
        self.assertEqual(org.connect_timeout, 10)
        self.assertEqual(org.retries, 1)

    def test_seeds_smtp_from_env(self):
        self._run(CF_OWNER_PASSWORD="x", CF_SMTP_HOST="smtp.claro.com.do", CF_SMTP_FROM="c@claro.com.do")
        org = OrganizationSettings.load()
        self.assertEqual(org.smtp_host, "smtp.claro.com.do")
        self.assertEqual(org.smtp_from, "c@claro.com.do")

    def test_location_mapping(self):
        self._run(CF_OWNER_PASSWORD="x")
        loc = lambda d: Certificate.objects.get(domain=d).location
        self.assertEqual(loc("ntpsfens.corp.codetel.com.do"), "Servidor")
        self.assertEqual(loc("sgv.claro.com.do"), "netscaler")
        self.assertEqual(loc("osbprod2.corp.codetel.com.do"), "")  # ni ntp/ntt ni claro.com.do

    def test_all_certs_notify_platform_and_email(self):
        self._run(CF_OWNER_PASSWORD="x")
        for c in Certificate.objects.all():
            self.assertTrue(c.notify_platform, c.domain)
            self.assertTrue(c.notify_email, c.domain)

    def test_support_groups_and_owner_membership(self):
        self._run(CF_OWNER_PASSWORD="x")
        owner = User.objects.get(email="jairol_grullon@claro.com.do")
        # Grupos sp_* creados.
        self.assertTrue(Team.objects.filter(name="sp_canales_electronicos").exists())
        # Nombre normalizado: sp_ordenes-aprov -> sp_ordenes_aprov.
        self.assertTrue(Team.objects.filter(name="sp_ordenes_aprov").exists())
        # El Owner es ADMIN SOLO de su grupo.
        memberships = list(Membership.objects.filter(user=owner))
        self.assertEqual(len(memberships), 1)
        self.assertEqual(memberships[0].team.name, "sp_canales_electronicos")
        self.assertEqual(memberships[0].role, MembershipRole.ADMIN)

    def test_cert_assigned_to_its_sp_groups(self):
        self._run(CF_OWNER_PASSWORD="x")
        sgv = Certificate.objects.get(domain="sgv.claro.com.do")
        self.assertEqual([g.name for g in sgv.groups.all()], ["sp_canales_electronicos"])
        # Cert sin correo sp_* -> sin grupos adicionales.
        ntp = Certificate.objects.get(domain="ntpsfens.corp.codetel.com.do")
        self.assertEqual(list(ntp.groups.all()), [])

    def test_recipients_include_all_emails(self):
        self._run(CF_OWNER_PASSWORD="x")
        api = Certificate.objects.get(domain="api.mi.claro.com.do")
        emails = set(api.recipients.values_list("email", flat=True))
        self.assertEqual(emails, {"sp_canales_electronicos@claro.com.do", "itredes@claro.com.do"})

    def test_group_names_normalized(self):
        # sp_adm-finanzas y sp_adm_finanzas son el mismo grupo (- == _).
        self._run(CF_OWNER_PASSWORD="x")
        self.assertEqual(Team.objects.filter(name="sp_adm_finanzas").count(), 1)
        self.assertFalse(Team.objects.filter(name="sp_adm-finanzas").exists())
        a = Certificate.objects.get(domain="finanzas-a.claro.com.do")
        b = Certificate.objects.get(domain="finanzas-b.claro.com.do")
        self.assertEqual([g.name for g in a.groups.all()], ["sp_adm_finanzas"])
        self.assertEqual([g.name for g in b.groups.all()], ["sp_adm_finanzas"])

    def test_idempotent(self):
        self._run(CF_OWNER_PASSWORD="x")
        n1 = Certificate.objects.count()
        t1 = Team.objects.count()
        self._run(CF_OWNER_PASSWORD="x")
        self.assertEqual(Certificate.objects.count(), n1)
        self.assertEqual(Team.objects.count(), t1)
