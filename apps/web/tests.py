"""Suite de caracterización (PASO 0).

Fija el comportamiento ACTUAL de la capa web ANTES de migrar a Forge UI, para
detectar regresiones en los pasos siguientes. NO valida un diseño objetivo;
documenta lo que hoy responde la aplicación.

Cubre:
- Login (GET /accounts/login/): 200 + referencia a forge.css.
- Raíz protegida (GET /): 302 a /accounts/login/?next=/ sin autenticar.
- Dashboard (GET /) autenticado: 200 + KPIs.
- Listado de certificados (GET /certificates/): 200, filtro ?status, parcial HTMX.

PASO 14 (integración de urls): ``/`` y ``/certificates/`` ahora resuelven a las
vistas canónicas Forge (``views_dashboard.DashboardView`` /
``views_certificates.CertificateListForgeView``). El contexto (``kpis``,
``certificates``) y las etiquetas KPI se mantienen, por lo que esta
caracterización sigue válida; solo se actualizaron los NOMBRES de plantilla del
listado (``certificados/list.html`` y ``certificados/_rows.html``), ya que las
antiguas ``certificates/list.html`` / ``_rows.html`` se eliminaron.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.certificates.models import Certificate
from apps.core.enums import CertificateStatus
from apps.teams.models import Team

User = get_user_model()


class LoginPageTests(TestCase):
    """GET /accounts/login/ caracteriza la página de inicio de sesión."""

    def test_login_page_returns_200(self):
        resp = self.client.get("/accounts/login/")
        self.assertEqual(resp.status_code, 200)

    def test_login_page_references_forge_css(self):
        resp = self.client.get("/accounts/login/")
        self.assertContains(resp, "forge.css")

    def test_login_page_is_html(self):
        resp = self.client.get("/accounts/login/")
        self.assertContains(resp, "<html")


class RootRedirectTests(TestCase):
    """GET / sin autenticar redirige al login con ?next=."""

    def test_root_requires_authentication(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)

    def test_root_redirects_to_login_with_next(self):
        resp = self.client.get("/")
        self.assertRedirects(
            resp,
            "/accounts/login/?next=/",
            fetch_redirect_response=False,
        )


class DashboardTests(TestCase):
    """GET / autenticado renderiza el dashboard con sus KPIs."""

    @classmethod
    def setUpTestData(cls):
        cls.password = "caracterizacion-2026"
        cls.user = User.objects.create_user(
            email="owner@certforge.test",
            password=cls.password,
            is_owner=True,
        )
        cls.team = Team.objects.create(name="Infraestructura")
        now = timezone.now()
        # Un certificado de cada estado relevante para poblar los KPIs.
        Certificate.objects.create(
            domain="vigente.example.do",
            team=cls.team,
            status=CertificateStatus.VIGENTE,
            days_left=120,
            valid_to=now + timedelta(days=120),
        )
        Certificate.objects.create(
            domain="porvencer.example.do",
            team=cls.team,
            status=CertificateStatus.POR_VENCER,
            days_left=20,
            valid_to=now + timedelta(days=20),
        )
        Certificate.objects.create(
            domain="critico.example.do",
            team=cls.team,
            status=CertificateStatus.CRITICO,
            days_left=5,
            valid_to=now + timedelta(days=5),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard_returns_200(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_uses_dashboard_template(self):
        resp = self.client.get("/")
        self.assertTemplateUsed(resp, "dashboard/dashboard.html")

    def test_dashboard_contains_kpi_labels(self):
        resp = self.client.get("/")
        # Etiquetas de las tarjetas KPI tal como se renderizan hoy.
        for label in ["Total", "Vigentes", "Por vencer", "Vencidos"]:
            self.assertContains(resp, label)

    def test_dashboard_kpi_values_present_in_context(self):
        resp = self.client.get("/")
        kpis = resp.context["kpis"]
        self.assertEqual(kpis["total"], 3)
        self.assertEqual(kpis["vigente"], 1)
        self.assertEqual(kpis["por_vencer"], 1)
        self.assertEqual(kpis["critico"], 1)

    def test_dashboard_attention_table_lists_certificates(self):
        resp = self.client.get("/")
        # POR_VENCER y CRITICO requieren atención; VIGENTE no.
        self.assertContains(resp, "porvencer.example.do")
        self.assertContains(resp, "critico.example.do")


class CertificateListTests(TestCase):
    """GET /certificates/ caracteriza listado, filtro por estado y parcial HTMX."""

    @classmethod
    def setUpTestData(cls):
        cls.password = "caracterizacion-2026"
        cls.user = User.objects.create_user(
            email="owner@certforge.test",
            password=cls.password,
            is_owner=True,
        )
        cls.team = Team.objects.create(name="Infraestructura")
        now = timezone.now()
        cls.vigente = Certificate.objects.create(
            domain="vigente.example.do",
            team=cls.team,
            status=CertificateStatus.VIGENTE,
            days_left=120,
            valid_to=now + timedelta(days=120),
        )
        cls.por_vencer = Certificate.objects.create(
            domain="porvencer.example.do",
            team=cls.team,
            status=CertificateStatus.POR_VENCER,
            days_left=20,
            valid_to=now + timedelta(days=20),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_list_returns_200(self):
        resp = self.client.get("/certificates/")
        self.assertEqual(resp.status_code, 200)

    def test_list_uses_full_template(self):
        resp = self.client.get("/certificates/")
        # PASO 14: la lista canónica es la Forge (certificados/list.html); la
        # antigua certificates/list.html se eliminó.
        self.assertTemplateUsed(resp, "certificados/list.html")
        self.assertContains(resp, "<html")

    def test_list_shows_all_certificates_unfiltered(self):
        resp = self.client.get("/certificates/")
        self.assertContains(resp, "vigente.example.do")
        self.assertContains(resp, "porvencer.example.do")

    def test_status_filter_narrows_results(self):
        resp = self.client.get("/certificates/", {"status": "POR_VENCER"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "porvencer.example.do")
        self.assertNotContains(resp, "vigente.example.do")

    def test_status_filter_applied_to_queryset(self):
        resp = self.client.get("/certificates/", {"status": "POR_VENCER"})
        domains = {c.domain for c in resp.context["certificates"]}
        self.assertEqual(domains, {"porvencer.example.do"})

    def test_htmx_request_returns_rows_partial(self):
        resp = self.client.get("/certificates/", HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        # PASO 14: el parcial canónico de filas es certificados/_rows.html.
        self.assertTemplateUsed(resp, "certificados/_rows.html")
        # El parcial no incluye el documento completo.
        self.assertNotContains(resp, "<html")
        self.assertContains(resp, "vigente.example.do")

    def test_htmx_partial_respects_status_filter(self):
        resp = self.client.get(
            "/certificates/",
            {"status": "POR_VENCER"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "<html")
        self.assertContains(resp, "porvencer.example.do")
        self.assertNotContains(resp, "vigente.example.do")

    def test_list_requires_authentication(self):
        self.client.logout()
        resp = self.client.get("/certificates/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])
