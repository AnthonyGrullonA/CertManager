"""Tests del Dashboard Forge UI (PASO 6).

Patrón de aislamiento de urls (sin tocar config/urls.py ni apps/web/urls.py):
ROOT_URLCONF = apps.web.test_urls_dashboard, que combina las urls globales con
las propias de esta pantalla. Names: dashboard-forge, dashboard-check-all.

Definition of Done verificada aquí:
- conteo de cada barra == filas del drill (mismos filtros days_gte/days_lt,
  ≤7d incluye vencidos);
- KPI Crítico/Vencido abre status__in=CRITICO,VENCIDO;
- "Chequear todo" responde con toast de conteo real + HX-Trigger que refresca KPIs;
- validity_percent presente en la barra de la DataTable de atención;
- caracterización intacta: labels Total/Vigentes/Por vencer/Vencidos presentes.
"""
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.certificates.models import Certificate
from apps.core.enums import CertificateStatus
from apps.teams.models import Team

User = get_user_model()

ROOT = "apps.web.test_urls_dashboard"


def _make_certs(team):
    now = timezone.now()
    specs = [
        # (domain, status, days_left)
        ("vigente.example.do", CertificateStatus.VIGENTE, 200),
        ("porvencer.example.do", CertificateStatus.POR_VENCER, 20),
        ("critico.example.do", CertificateStatus.CRITICO, 5),
        ("vencido.example.do", CertificateStatus.VENCIDO, -3),
        ("error.example.do", CertificateStatus.ERROR, None),
        ("sinchequear.example.do", CertificateStatus.SIN_CHEQUEAR, None),
        # Extras para poblar varias ventanas.
        ("w15.example.do", CertificateStatus.POR_VENCER, 12),
        ("w30.example.do", CertificateStatus.POR_VENCER, 25),
        ("w60.example.do", CertificateStatus.VIGENTE, 45),
        ("w90.example.do", CertificateStatus.VIGENTE, 80),
    ]
    for domain, status, days in specs:
        Certificate.objects.create(
            domain=domain,
            team=team,
            status=status,
            days_left=days,
            valid_from=now - timedelta(days=100) if days is not None else None,
            valid_to=(now + timedelta(days=days)) if days is not None else None,
        )


@override_settings(ROOT_URLCONF=ROOT)
class DashboardForgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.team = Team.objects.create(name="Infraestructura")
        _make_certs(cls.team)

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("dashboard-forge")

    # --- básicos ---------------------------------------------------------
    def test_dashboard_returns_200(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard/dashboard.html")

    def test_requires_authentication(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_caracterizacion_labels_present(self):
        """No romper las aserciones de caracterización del dashboard."""
        resp = self.client.get(self.url)
        for label in ["Total", "Vigentes", "Por vencer", "Vencidos"]:
            self.assertContains(resp, label)

    def test_kpi_context_values(self):
        resp = self.client.get(self.url)
        k = resp.context["kpis"]
        self.assertEqual(k["total"], 10)
        self.assertEqual(k["vigente"], 3)
        self.assertEqual(k["critico"], 1)
        self.assertEqual(k["vencido"], 1)
        self.assertEqual(k["error"], 1)
        self.assertEqual(k["sin_chequear"], 1)
        self.assertEqual(k["critico_vencido"], 2)
        self.assertEqual(k["error_sin_chequear"], 2)

    # --- DRILL: KPI Crítico/Vencido abre status__in correcto -------------
    def test_kpi_critico_vencido_drill_status_in(self):
        resp = self.client.get(self.url)
        card = next(c for c in resp.context["kpi_cards"] if c["label"] == "Crítico / Vencido")
        qs = parse_qs(urlparse(card["href"]).query)
        self.assertEqual(set(qs["status"]), {"CRITICO", "VENCIDO"})

    def test_kpi_error_sin_chequear_drill_status_in(self):
        resp = self.client.get(self.url)
        card = next(c for c in resp.context["kpi_cards"] if c["label"] == "Error / sin chequear")
        qs = parse_qs(urlparse(card["href"]).query)
        self.assertEqual(set(qs["status"]), {"ERROR", "SIN_CHEQUEAR"})

    def test_kpi_drill_points_to_certificate_list(self):
        resp = self.client.get(self.url)
        card = next(c for c in resp.context["kpi_cards"] if c["label"] == "Vigentes")
        self.assertTrue(card["href"].startswith(reverse("certificate-list")))
        self.assertEqual(parse_qs(urlparse(card["href"]).query)["status"], ["VIGENTE"])

    # --- DRILL: conteo de cada barra == filas del drill -----------------
    def test_bar_count_equals_drill_rows(self):
        resp = self.client.get(self.url)
        certs = Certificate.objects.for_user(self.user)
        for w in resp.context["expiry_windows"]:
            qs = parse_qs(urlparse(w["href"]).query)
            q = Q(days_left__lt=int(qs["days_lt"][0]))
            if "days_gte" in qs:
                q &= Q(days_left__gte=int(qs["days_gte"][0]))
            drill_rows = certs.filter(q).count()
            self.assertEqual(
                w["value"], drill_rows,
                f"Barra {w['label']}: conteo {w['value']} != filas drill {drill_rows}",
            )

    def test_first_window_includes_expired(self):
        """≤7d incluye vencidos (days_left < 0) y no tiene cota inferior."""
        resp = self.client.get(self.url)
        first = resp.context["expiry_windows"][0]
        self.assertEqual(first["label"], "≤7d")
        self.assertIsNone(first["window_min"])
        qs = parse_qs(urlparse(first["href"]).query)
        self.assertNotIn("days_gte", qs)
        self.assertEqual(qs["days_lt"], ["7"])
        # critico (5d) + vencido (-3d) caen en ≤7d.
        self.assertEqual(first["value"], 2)

    def test_windows_non_overlapping_partition(self):
        """Las ventanas particionan días<90 sin solape (suma de conteos)."""
        resp = self.client.get(self.url)
        certs = Certificate.objects.for_user(self.user)
        total_in_windows = sum(w["value"] for w in resp.context["expiry_windows"])
        expected = certs.filter(days_left__lt=90).count()
        self.assertEqual(total_in_windows, expected)

    # --- validity_percent en la barra de la tabla ------------------------
    def test_attention_table_has_validity_bar(self):
        resp = self.client.get(self.url)
        # La barra de validez renderiza role="progressbar" con aria-valuenow.
        self.assertContains(resp, "forge-validity")
        self.assertContains(resp, 'role="progressbar"')

    def test_attention_lists_urgent_certs(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "critico.example.do")
        self.assertContains(resp, "vencido.example.do")
        self.assertNotContains(resp, "w90.example.do")

    def test_attention_table_is_sortable(self):
        # PASE DE FIDELIDAD: la tabla "Requieren atención" habilita orden por
        # columna nativo (data-forge-sortable sobre data-forge-table).
        resp = self.client.get(self.url)
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, "data-forge-sortable")

    # --- donut por estado ------------------------------------------------
    def test_status_distribution_has_all_states(self):
        resp = self.client.get(self.url)
        keys = {s["key"] for s in resp.context["status_distribution"]}
        self.assertEqual(keys, {s.value for s in CertificateStatus})
        for seg in resp.context["status_distribution"]:
            qs = parse_qs(urlparse(seg["href"]).query)
            self.assertEqual(qs["status"], [seg["key"]])

    def test_donut_color_distinguishes_critico_from_vencido(self):
        """Cada segmento expone un color CSS y CRITICO != VENCIDO (ambos rojos,
        pero el vencido más oscuro) para que el donut no los confunda."""
        resp = self.client.get(self.url)
        by_key = {s["key"]: s for s in resp.context["status_distribution"]}
        for seg in by_key.values():
            self.assertTrue(seg["color"])  # toda fila trae color
        self.assertNotEqual(by_key["CRITICO"]["color"], by_key["VENCIDO"]["color"])
        self.assertEqual(by_key["VENCIDO"]["color"], "var(--status-exp-fg)")

    # --- tendencia real (sin datos inventados) ---------------------------
    def test_trend_is_real_and_empty_without_history(self):
        """La tendencia se calcula del historial: 8 semanas y, sin chequeos
        registrados, series en cero (has_data=False) en vez de datos fijos."""
        resp = self.client.get(self.url)
        trend = resp.context["trend"]
        self.assertEqual(len(trend["labels"]), 8)
        self.assertEqual(len(trend["por_vencer"]), 8)
        self.assertEqual(len(trend["vencidos"]), 8)
        # _make_certs no crea CertificateCheck -> sin historial.
        self.assertFalse(trend["has_data"])
        self.assertEqual(sum(trend["por_vencer"]) + sum(trend["vencidos"]), 0)

    def test_trend_counts_history(self):
        """Con chequeos en el historial, la semana corriente refleja el conteo."""
        from apps.certificates.models import Certificate, CertificateCheck

        now = timezone.now()
        cert = Certificate.objects.filter(domain="porvencer.example.do").first()
        CertificateCheck.objects.create(
            certificate=cert, checked_at=now - timedelta(days=1),
            status=CertificateStatus.POR_VENCER, days_left=20,
        )
        resp = self.client.get(self.url)
        trend = resp.context["trend"]
        self.assertTrue(trend["has_data"])
        # La última ventana (semana corriente) contiene el chequeo recién creado.
        self.assertEqual(trend["por_vencer"][-1], 1)


@override_settings(ROOT_URLCONF=ROOT)
class CheckAllTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.team_a = Team.objects.create(name="Alpha")
        cls.team_b = Team.objects.create(name="Beta")
        now = timezone.now()
        for i in range(3):
            Certificate.objects.create(
                domain=f"a{i}.example.do", team=cls.team_a,
                status=CertificateStatus.VIGENTE, days_left=100,
                valid_from=now, valid_to=now + timedelta(days=100),
            )
        for i in range(2):
            Certificate.objects.create(
                domain=f"b{i}.example.do", team=cls.team_b,
                status=CertificateStatus.VIGENTE, days_left=100,
                valid_from=now, valid_to=now + timedelta(days=100),
            )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("dashboard-check-all")

    def test_check_all_requires_post(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_check_all_dispatches_background_with_scope_ids(self):
        """"Chequear todo" lanza el chequeo en segundo plano con los ids del
        ámbito y confirma de inmediato (no bloquea con run_check real)."""
        with mock.patch("apps.web.views_dashboard._dispatch_check_all") as disp:
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        disp.assert_called_once()
        ids = list(disp.call_args.args[0])
        self.assertEqual(len(ids), 5)  # 3 Alpha + 2 Beta
        self.assertContains(resp, "Chequeo en curso para 5 certificados")
        self.assertContains(resp, "forge-toast")

    def test_check_all_emits_hx_trigger(self):
        with mock.patch("apps.web.views_dashboard._dispatch_check_all"):
            resp = self.client.post(self.url)
        self.assertEqual(resp["HX-Trigger"], "cf:check-all-started")

    def test_check_all_respects_scope(self):
        with mock.patch("apps.web.views_dashboard._dispatch_check_all") as disp:
            resp = self.client.post(self.url, {"team": str(self.team_b.id)})
        self.assertEqual(len(list(disp.call_args.args[0])), 2)
        self.assertContains(resp, "Chequeo en curso para 2 certificados")

    def test_check_all_singular_message(self):
        Certificate.objects.exclude(team=self.team_b).delete()
        Certificate.objects.filter(team=self.team_b).exclude(
            domain="b0.example.do"
        ).delete()
        with mock.patch("apps.web.views_dashboard._dispatch_check_all") as disp:
            resp = self.client.post(self.url, {"team": str(self.team_b.id)})
        self.assertEqual(len(list(disp.call_args.args[0])), 1)
        self.assertContains(resp, "Chequeo en curso para 1 certificado")

    def test_check_all_empty_scope_does_not_dispatch(self):
        Certificate.objects.all().delete()
        with mock.patch("apps.web.views_dashboard._dispatch_check_all") as disp:
            resp = self.client.post(self.url)
        disp.assert_not_called()
        self.assertContains(resp, "No hay certificados")

    # --- worker (chequeo real, síncrono y testeable) ---------------------
    def test_worker_runs_real_checks(self):
        from apps.web.views_dashboard import _check_all_worker

        ids = list(Certificate.objects.values_list("id", flat=True))
        with mock.patch("apps.monitoring.runner.run_check") as run:
            ok = _check_all_worker(ids)
        self.assertEqual(run.call_count, 5)
        self.assertEqual(ok, 5)

    def test_worker_isolates_failures(self):
        """Un run_check que revienta no cuenta como verificado, pero no aborta."""
        from apps.web.views_dashboard import _check_all_worker

        ids = list(Certificate.objects.values_list("id", flat=True))
        with mock.patch("apps.monitoring.runner.run_check") as run:
            run.side_effect = [None, RuntimeError("boom"), None, None, None]
            ok = _check_all_worker(ids)
        self.assertEqual(run.call_count, 5)
        self.assertEqual(ok, 4)

    def test_check_all_requires_authentication(self):
        self.client.logout()
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 302)


@override_settings(ROOT_URLCONF=ROOT)
class DashboardScopeTests(TestCase):
    """El dashboard recorta KPIs/tabla al scope activo (querystring team)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@certforge.test", password="x", is_owner=True
        )
        cls.team_a = Team.objects.create(name="Alpha")
        cls.team_b = Team.objects.create(name="Beta")
        now = timezone.now()
        Certificate.objects.create(
            domain="alpha.example.do", team=cls.team_a,
            status=CertificateStatus.VIGENTE, days_left=100,
            valid_from=now, valid_to=now + timedelta(days=100),
        )
        Certificate.objects.create(
            domain="beta.example.do", team=cls.team_b,
            status=CertificateStatus.VIGENTE, days_left=100,
            valid_from=now, valid_to=now + timedelta(days=100),
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("dashboard-forge")

    def test_scope_all_counts_everything(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["kpis"]["total"], 2)

    def test_scope_team_narrows_counts(self):
        resp = self.client.get(self.url, {"team": str(self.team_a.id)})
        self.assertEqual(resp.context["kpis"]["total"], 1)
        self.assertEqual(resp.context["kpis"]["vigente"], 1)
        # El ámbito Beta no aporta a los conteos del ámbito Alpha.
        resp_b = self.client.get(self.url, {"team": str(self.team_b.id)})
        self.assertEqual(resp_b.context["kpis"]["total"], 1)

    def test_scope_propagated_to_drill_hrefs(self):
        resp = self.client.get(self.url, {"team": str(self.team_a.id)})
        card = next(c for c in resp.context["kpi_cards"] if c["label"] == "Vigentes")
        qs = parse_qs(urlparse(card["href"]).query)
        self.assertEqual(qs["team"], [str(self.team_a.id)])
