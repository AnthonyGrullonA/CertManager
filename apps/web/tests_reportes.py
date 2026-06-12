"""Tests de la pantalla Reportes (PASO 13).

Usa ``apps.web.test_urls_reportes`` como ROOT_URLCONF para resolver tanto las
urls globales (dashboard, certificate-list…) como las de Reportes sin tocar
``config/urls.py`` (cableado real en el PASO 14).

Cubre: preview en vivo refleja filtros, EmptyState es-DO, export respeta filtros
(PDF/Excel/CSV y multi-formato ZIP), CRUD de reportes programados con formato(s)
y hora, y scoping por usuario.
"""
import io
import zipfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.certificates.models import Certificate, CertificateRecipient
from apps.core.enums import CertificateStatus, ReportFrequency, ReportTemplate
from apps.reports.models import ScheduledReport
from apps.reports.services import ReportFilters, build_report, export_pdf
from apps.teams.models import Membership, Team
from apps.core.enums import MembershipRole

User = get_user_model()

URLCONF = "apps.web.test_urls_reportes"


@override_settings(ROOT_URLCONF=URLCONF)
class ReportListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.team = Team.objects.create(name="Infraestructura")
        cls.team2 = Team.objects.create(name="Comercial")
        now = timezone.now()
        cls.vigente = Certificate.objects.create(
            domain="vigente.example.do", team=cls.team,
            status=CertificateStatus.VIGENTE, days_left=120,
            valid_to=now + timedelta(days=120), issuer="DigiCert Inc",
        )
        cls.por_vencer = Certificate.objects.create(
            domain="porvencer.example.do", team=cls.team,
            status=CertificateStatus.POR_VENCER, days_left=20,
            valid_to=now + timedelta(days=20), issuer="Let's Encrypt",
        )
        cls.vencido = Certificate.objects.create(
            domain="vencido.example.do", team=cls.team2,
            status=CertificateStatus.VENCIDO, days_left=-3,
            valid_to=now - timedelta(days=3), issuer="DigiCert Inc",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_list_returns_200(self):
        resp = self.client.get(reverse("report-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "reportes/list.html")
        self.assertContains(resp, "<html")
        self.assertContains(resp, "Constructor")
        self.assertContains(resp, "data-report-builder-modal")

    def test_builder_is_modal_not_sticky_side_panel(self):
        resp = self.client.get(reverse("report-list"))
        self.assertContains(resp, "data-report-builder-open")
        self.assertContains(resp, 'class="forge-modal rep-builder-modal"')
        self.assertNotContains(resp, "rep-grid")

    def test_list_requires_authentication(self):
        self.client.logout()
        resp = self.client.get(reverse("report-list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_htmx_returns_preview_partial(self):
        resp = self.client.get(reverse("report-list"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "reportes/_preview.html")
        self.assertNotContains(resp, "<html")

    def test_preview_reflects_status_filter_live(self):
        resp = self.client.get(
            reverse("report-preview"), {"statuses": "POR_VENCER"}
        )
        self.assertEqual(resp.status_code, 200)
        result = resp.context["result"]
        domains = {c.domain for c in result.certificates}
        self.assertEqual(domains, {"porvencer.example.do"})
        self.assertContains(resp, "porvencer.example.do")
        self.assertNotContains(resp, "vigente.example.do")

    def test_preview_reflects_team_filter_live(self):
        resp = self.client.get(
            reverse("report-preview"), {"teams": str(self.team2.id), "date_range": "all"}
        )
        domains = {c.domain for c in resp.context["result"].certificates}
        self.assertEqual(domains, {"vencido.example.do"})

    def test_preview_reflects_issuer_filter(self):
        resp = self.client.get(
            reverse("report-preview"), {"issuer": "Let's Encrypt", "date_range": "all"}
        )
        domains = {c.domain for c in resp.context["result"].certificates}
        self.assertEqual(domains, {"porvencer.example.do"})

    def test_preview_expiry_window_includes_expired(self):
        resp = self.client.get(
            reverse("report-preview"), {"expiry_window": "30", "date_range": "all"}
        )
        domains = {c.domain for c in resp.context["result"].certificates}
        # POR_VENCER (20) y VENCIDO (-3) caen en <=30; VIGENTE (120) no.
        self.assertEqual(domains, {"porvencer.example.do", "vencido.example.do"})

    def test_template_expiring_preset(self):
        resp = self.client.get(
            reverse("report-preview"),
            {"template": "EXPIRING", "date_range": "all"},
        )
        domains = {c.domain for c in resp.context["result"].certificates}
        self.assertEqual(domains, {"porvencer.example.do"})

    def test_empty_state_es_do(self):
        resp = self.client.get(
            reverse("report-preview"),
            {"issuer": "no-existe-emisor-xyz", "date_range": "all"},
        )
        self.assertEqual(resp.context["result"].total, 0)
        self.assertContains(resp, "Sin coincidencias")
        self.assertNotContains(resp, "vigente.example.do")

    def test_preview_table_is_paginated(self):
        """La DataTable de detalle se envuelve para ForgeDataTable."""
        resp = self.client.get(reverse("report-preview"), {"date_range": "all"})
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, 'data-page-size="8"')

    def test_preview_renders_kpi_strip(self):
        resp = self.client.get(reverse("report-preview"), {"date_range": "all"})
        self.assertContains(resp, "rep-kpis")
        self.assertContains(resp, "Por vencer")


@override_settings(ROOT_URLCONF=URLCONF)
class ReportExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.team = Team.objects.create(name="Infraestructura")
        now = timezone.now()
        Certificate.objects.create(
            domain="vigente.example.do", team=cls.team,
            status=CertificateStatus.VIGENTE, days_left=120,
            valid_to=now + timedelta(days=120),
        )
        Certificate.objects.create(
            domain="porvencer.example.do", team=cls.team,
            status=CertificateStatus.POR_VENCER, days_left=20,
            valid_to=now + timedelta(days=20),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_export_csv(self):
        resp = self.client.get(reverse("report-export"), {"format": "CSV"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        body = resp.content.decode("utf-8")
        self.assertIn("vigente.example.do", body)
        self.assertIn("Dominio", body)

    def test_export_pdf(self):
        resp = self.client.get(reverse("report-export"), {"format": "PDF"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_export_pdf_uses_certforge_template(self):
        result = build_report(
            self.user,
            ReportFilters(date_range="all"),
            scope_label="Todos los grupos",
        )
        pdf = export_pdf(result)
        self.assertIn(b"CertManager", pdf)
        self.assertIn(b"monitoreo de certificados", pdf)
        self.assertIn(b"Salida de CertManager", pdf)

    def test_export_excel(self):
        resp = self.client.get(reverse("report-export"), {"format": "EXCEL"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        # xlsx es un zip (PK..).
        self.assertTrue(resp.content.startswith(b"PK"))

    def test_export_multiformat_zip(self):
        resp = self.client.get(
            reverse("report-export"),
            {"formats": ["PDF", "EXCEL", "CSV"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = sorted(n.split(".")[-1] for n in zf.namelist())
        self.assertEqual(names, ["csv", "pdf", "xlsx"])

    def test_export_respects_filter(self):
        resp = self.client.get(
            reverse("report-export"),
            {"format": "CSV", "statuses": "POR_VENCER"},
        )
        body = resp.content.decode("utf-8")
        self.assertIn("porvencer.example.do", body)
        self.assertNotIn("vigente.example.do", body)


@override_settings(ROOT_URLCONF=URLCONF)
class ScheduledReportCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.team = Team.objects.create(name="Infraestructura")

    def setUp(self):
        self.client.force_login(self.user)

    def test_create_modal_renders(self):
        resp = self.client.get(reverse("report-create"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Programar reporte")
        self.assertContains(resp, "Hora de envío")
        self.assertContains(resp, "Formato(s)")

    def test_create_scheduled_report(self):
        resp = self.client.post(
            reverse("report-create"),
            {
                "name": "Resumen semanal",
                "template": ReportTemplate.EXPIRING,
                "frequency": ReportFrequency.WEEKLY,
                "send_time": "08:00",
                "team": str(self.team.id),
                "formats": ["PDF", "EXCEL"],
                "recipients_text": "admin@certforge.do, ops@certforge.do",
                "is_active": "on",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        report = ScheduledReport.objects.get(name="Resumen semanal")
        self.assertEqual(report.formats, ["PDF", "EXCEL"])
        self.assertEqual(str(report.send_time)[:5], "08:00")
        self.assertEqual(report.recipients, ["admin@certforge.do", "ops@certforge.do"])
        self.assertEqual(report.created_by, self.user)
        self.assertContains(resp, "Resumen semanal")

    def test_create_invalid_requires_format(self):
        resp = self.client.post(
            reverse("report-create"),
            {
                "name": "Sin formato",
                "template": ReportTemplate.INVENTORY,
                "frequency": ReportFrequency.DAILY,
                "send_time": "07:00",
                "recipients_text": "x@y.do",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ScheduledReport.objects.filter(name="Sin formato").exists())
        # Vuelve a renderizar el modal con el error.
        self.assertContains(resp, "Programar reporte")

    def test_edit_scheduled_report(self):
        report = ScheduledReport.objects.create(
            name="Inventario mensual", template=ReportTemplate.INVENTORY,
            frequency=ReportFrequency.MONTHLY, formats=["CSV"], created_by=self.user,
        )
        resp = self.client.post(
            reverse("report-edit", args=[report.pk]),
            {
                "name": "Inventario mensual v2",
                "template": ReportTemplate.INVENTORY,
                "frequency": ReportFrequency.MONTHLY,
                "send_time": "09:30",
                "formats": ["EXCEL"],
                "recipients_text": "owner@certforge.io",
                "is_active": "on",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.name, "Inventario mensual v2")
        self.assertEqual(report.formats, ["EXCEL"])

    def test_scheduled_list_is_paginated(self):
        """La lista de programados se renderiza como DataTable."""
        ScheduledReport.objects.create(
            name="Programado X", template=ReportTemplate.INVENTORY,
            frequency=ReportFrequency.WEEKLY, formats=["PDF"], created_by=self.user,
        )
        resp = self.client.get(reverse("report-list"))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, "Programado X")

    def test_delete_scheduled_report(self):
        report = ScheduledReport.objects.create(
            name="Vencidos diario", template=ReportTemplate.EXPIRED,
            frequency=ReportFrequency.DAILY, formats=["CSV"], created_by=self.user,
        )
        resp = self.client.post(reverse("report-delete", args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ScheduledReport.objects.filter(pk=report.pk).exists())


@override_settings(ROOT_URLCONF=URLCONF)
class ScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.member = User.objects.create_user(
            email="member@certforge.test", password="x"
        )
        cls.team_a = Team.objects.create(name="Grupo A")
        cls.team_b = Team.objects.create(name="Grupo B")
        Membership.objects.create(user=cls.member, team=cls.team_a, role=MembershipRole.CONTRIBUTOR)
        now = timezone.now()
        cls.cert_a = Certificate.objects.create(
            domain="a.example.do", team=cls.team_a,
            status=CertificateStatus.VIGENTE, days_left=100,
            valid_to=now + timedelta(days=100),
        )
        cls.cert_b = Certificate.objects.create(
            domain="b.example.do", team=cls.team_b,
            status=CertificateStatus.VIGENTE, days_left=100,
            valid_to=now + timedelta(days=100),
        )

    def test_member_only_sees_own_team_certs_in_preview(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("report-preview"), {"date_range": "all"})
        domains = {c.domain for c in resp.context["result"].certificates}
        self.assertEqual(domains, {"a.example.do"})

    def test_member_export_excludes_other_teams(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("report-export"), {"format": "CSV", "date_range": "all"})
        body = resp.content.decode("utf-8")
        self.assertIn("a.example.do", body)
        self.assertNotIn("b.example.do", body)

    def test_member_cannot_edit_other_users_global_report(self):
        report = ScheduledReport.objects.create(
            name="Global del owner", template=ReportTemplate.INVENTORY,
            frequency=ReportFrequency.DAILY, formats=["CSV"], created_by=self.owner,
        )
        self.client.force_login(self.member)
        resp = self.client.get(reverse("report-edit", args=[report.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 404)


@override_settings(ROOT_URLCONF=URLCONF)
class ReportSortableFidelityTests(TestCase):
    """Pase de fidelidad: orden nativo en la DataTable de detalle del preview y en la
    de reportes programados (sin búsqueda; Reportes ya tiene constructor)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.team = Team.objects.create(name="Infraestructura")
        now = timezone.now()
        Certificate.objects.create(
            domain="uno.example.do", team=cls.team,
            status=CertificateStatus.VIGENTE, days_left=90,
            valid_to=now + timedelta(days=90),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_preview_detail_table_is_sortable(self):
        resp = self.client.get(reverse("report-preview"), {"date_range": "all"})
        self.assertContains(resp, "data-forge-sortable")

    def test_scheduled_table_is_sortable_with_actions_excluded(self):
        ScheduledReport.objects.create(
            name="Programado Z", template=ReportTemplate.INVENTORY,
            frequency=ReportFrequency.WEEKLY, formats=["PDF"], created_by=self.user,
        )
        resp = self.client.get(reverse("report-list"))
        self.assertContains(resp, "data-forge-sortable")
        # La columna de acciones (sin encabezado) no debe ordenar.
        self.assertContains(resp, "data-no-sort")

    def test_reportes_does_not_add_client_search(self):
        """No se duplica búsqueda: Reportes usa su constructor server-side."""
        resp = self.client.get(reverse("report-list"))
        self.assertNotContains(resp, "data-forge-search")
