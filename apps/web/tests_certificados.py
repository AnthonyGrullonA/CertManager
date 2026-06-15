"""Tests de la pantalla Certificados (Forge UI · PASO 7).

Usan el ROOT_URLCONF de prueba ``apps.web.test_urls_certificados`` para resolver
tanto las urls globales (dashboard, logout, certificate-list…) como las propias
(certificate-list-forge, cert-create, cert-bulk, cert-export, cert-test).

Los chequeos reales (``run_check``) se mockean para no abrir red en CI; un test
adicional verifica que el camino de ERROR/timeout del servicio se refleje en el
drawer sin mockear el runner (el servicio anti-SSRF rechaza hosts internos).
"""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.certificates.models import Certificate, CertificateRecipient
from apps.core.enums import CertificateStatus, MembershipRole
from apps.monitoring.services import CheckResult
from apps.teams.models import Membership, Team

User = get_user_model()

URLCONF = "apps.web.test_urls_certificados"


def _ok_result():
    now = timezone.now()
    return CheckResult(
        ok=True,
        status=CertificateStatus.VIGENTE,
        days_left=90,
        valid_from=now - timedelta(days=10),
        valid_to=now + timedelta(days=90),
        issuer="CN=Let's Encrypt",
        latency_ms=42,
    )


@override_settings(ROOT_URLCONF=URLCONF)
class CertListTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.member = User.objects.create_user("member@certforge.test", "x")
        self.team_a = Team.objects.create(name="Plataforma")
        self.team_b = Team.objects.create(name="Finanzas")
        Membership.objects.create(user=self.member, team=self.team_a, role=MembershipRole.CONTRIBUTOR)
        self.cert_a = Certificate.objects.create(domain="api.ejemplo.com", port=443, team=self.team_a)
        self.cert_b = Certificate.objects.create(domain="banco.ejemplo.com", port=443, team=self.team_b)

    def test_requires_authentication(self):
        resp = self.client.get(reverse("certificate-list-forge"))
        self.assertEqual(resp.status_code, 302)

    def test_issuer_cell_truncates_to_single_line(self):
        # Un emisor con DN largo no debe envolver a varias líneas e inflar la
        # fila (rompe el datatable): se trunca a una línea con ellipsis + title.
        import re

        self.cert_a.issuer = (
            "CN=Sectigo Public Server Authentication CA DV R36,"
            "O=Sectigo Limited,C=GB"
        )
        self.cert_a.save(update_fields=["issuer"])
        self.client.force_login(self.owner)
        html = self.client.get(reverse("certificate-list-forge")).content.decode()
        cell = re.search(r'<span[^>]*>CN=Sectigo[^<]*</span>', html).group(0)
        self.assertIn("white-space:nowrap", cell)
        self.assertIn("text-overflow:ellipsis", cell)
        self.assertIn("overflow:hidden", cell)
        self.assertIn("max-width:", cell)
        self.assertIn("title=", cell)

    def test_owner_sees_all(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "api.ejemplo.com")
        self.assertContains(resp, "banco.ejemplo.com")
        self.assertContains(resp, "Certificados")

    def test_member_sees_only_own_team(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("certificate-list-forge"))
        self.assertContains(resp, "api.ejemplo.com")
        self.assertNotContains(resp, "banco.ejemplo.com")

    def test_filter_by_domain(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"), {"q": "banco"})
        self.assertContains(resp, "banco.ejemplo.com")
        self.assertNotContains(resp, "api.ejemplo.com")

    def test_htmx_returns_only_rows(self):
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse("certificate-list-forge"), {"q": "api"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(resp, "api.ejemplo.com")
        # El parcial NO trae el <html> de base.
        self.assertNotContains(resp, "<html")

    def test_table_is_sortable(self):
        # PASE DE FIDELIDAD: la CertTable habilita orden por columna nativo
        # (data-forge-sortable en el wrapper data-forge-table).
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, "data-forge-sortable")
        # Las columnas de selección, responsables y acciones NO se ordenan.
        self.assertContains(resp, "data-no-sort")
        # No se duplica búsqueda client-side: la FilterBar ya filtra server-side.
        self.assertNotContains(resp, "data-forge-search")

    def test_empty_state_es_do(self):
        Certificate.objects.all().delete()
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"))
        self.assertContains(resp, "Sin resultados")
        self.assertContains(resp, 'id="certs-empty"')

    def test_chip_present_when_filtering(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"), {"q": "api"})
        self.assertContains(resp, "forge-chip")
        self.assertContains(resp, "Búsqueda")

    def test_pagination_wrapper_present(self):
        # El listado completo envuelve la tabla en [data-forge-table]; ForgeTable
        # (componente propio, vanilla) la cablea en cliente desde forge-table.js.
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, "forge-table-scroll")
        self.assertContains(resp, 'data-page-size="8"')
        self.assertContains(resp, "js/forge-table.js")
        # DataTables fue eliminado: ya no se carga el bundle de CDN.
        self.assertNotContains(resp, "cdn.datatables.net")

    def test_empty_row_marked_for_pager(self):
        # La fila de "sin resultados" lleva data-empty-row para que el paginación
        # no la cuente como dato.
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"), {"q": "no-existe-xyz"})
        self.assertContains(resp, "data-empty-row")

    def test_htmx_partial_has_no_pager(self):
        # El swap de HTMX reemplaza solo el <tbody>; el wrapper/paginación persiste
        # en la página y ForgeDataTable re-renderiza en htmx:afterSwap.
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse("certificate-list-forge"), {"q": "api"}, HTTP_HX_REQUEST="true"
        )
        self.assertNotContains(resp, "data-forge-pagesize")

    def test_responsables_recipient_user_then_group_fallback(self):
        # Destinatario con usuario vinculado en cert_a.
        recip_user = User.objects.create_user("recip@certforge.test", "x", first_name="Rita")
        CertificateRecipient.objects.create(
            certificate=self.cert_a, email=recip_user.email, user=recip_user
        )
        # cert_b sin destinatarios -> fallback a Colaboradores del grupo.
        admin = User.objects.create_user("adminb@certforge.test", "x", first_name="Bea")
        Membership.objects.create(user=admin, team=self.team_b, role=MembershipRole.CONTRIBUTOR)
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"))
        # La tabla de certificados muestra correos planos, sin avatar/icono.
        self.assertContains(resp, "recip@certforge.test")
        self.assertContains(resp, "adminb@certforge.test")
        self.assertNotContains(resp, 'title="Rita"')
        self.assertNotContains(resp, 'title="Bea"')

    def test_recipient_email_is_visible_even_without_user(self):
        CertificateRecipient.objects.create(
            certificate=self.cert_a,
            email="legacy@claro.com.do",
            alert_threshold_days=45,
        )
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("certificate-list-forge"))
        self.assertContains(resp, "legacy@claro.com.do")
        self.assertContains(resp, "umbral 45d")


@override_settings(ROOT_URLCONF=URLCONF)
class CertCreateTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user("member@certforge.test", "x")
        self.team = Team.objects.create(name="Plataforma")
        self.other = Team.objects.create(name="Ajeno")
        Membership.objects.create(user=self.member, team=self.team, role=MembershipRole.CONTRIBUTOR)

    def test_member_gets_modal(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("cert-create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Nuevo certificado")
        self.assertContains(resp, "Guardar y probar")
        # Solo aparece su grupo en el selector (RBAC).
        self.assertContains(resp, "Plataforma")
        self.assertNotContains(resp, ">Ajeno<")

    def test_create_guardar(self):
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse("cert-create"),
            {"domain": "nuevo.ejemplo.com", "port": 443, "team": self.team.id,
             "alert_threshold_days": 30, "notify_platform": "on", "notify_email": "on"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "nuevo.ejemplo.com")
        self.assertContains(resp, 'hx-swap-oob="afterbegin"')
        self.assertContains(resp, "Certificado guardado")
        cert = Certificate.objects.get(domain="nuevo.ejemplo.com")
        self.assertEqual(cert.team, self.team)
        self.assertEqual(cert.created_by, self.member)

    def test_create_guardar_y_probar_runs_check(self):
        self.client.force_login(self.member)
        with mock.patch("apps.monitoring.runner.run_check") as run:
            run.return_value = (None, _ok_result())
            resp = self.client.post(
                reverse("cert-create"),
                {"domain": "probar.ejemplo.com", "port": 443, "team": self.team.id,
                 "alert_threshold_days": 30, "save_and_test": "1"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Certificate.objects.filter(domain="probar.ejemplo.com").exists())
        run.assert_called_once()

    def test_create_duplicate_domain_blocked(self):
        Certificate.objects.create(domain="dup.ejemplo.com", port=443, team=self.team)
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse("cert-create"),
            {"domain": "dup.ejemplo.com", "port": 443, "team": self.team.id,
             "alert_threshold_days": 30},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertContains(resp, "Ya existe un certificado", status_code=422)
        self.assertEqual(Certificate.objects.filter(domain="dup.ejemplo.com").count(), 1)

    def test_create_foreign_team_blocked(self):
        # El miembro intenta crear en un grupo ajeno (manipulando el POST).
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse("cert-create"),
            {"domain": "hack.ejemplo.com", "port": 443, "team": self.other.id,
             "alert_threshold_days": 30},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertFalse(Certificate.objects.filter(domain="hack.ejemplo.com").exists())


@override_settings(ROOT_URLCONF=URLCONF)
class CertBulkTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.team = Team.objects.create(name="Plataforma")
        self.dest = Team.objects.create(name="Destino")
        self.c1 = Certificate.objects.create(domain="a.ejemplo.com", port=443, team=self.team)
        self.c2 = Certificate.objects.create(domain="b.ejemplo.com", port=443, team=self.team)

    def test_bulk_delete_requires_confirmation(self):
        self.client.force_login(self.owner)
        # Sin confirm=1 -> devuelve el modal de confirmación, NO borra.
        resp = self.client.post(
            reverse("cert-bulk"),
            {"action": "delete", "ids": [self.c1.id, self.c2.id]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Eliminar 2 certificados")
        self.assertContains(resp, "no se puede deshacer")
        self.assertEqual(Certificate.objects.count(), 2)

    def test_bulk_delete_confirmed(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("cert-bulk"),
            {"action": "delete", "confirm": "1", "ids": [self.c1.id, self.c2.id]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Certificados eliminados")
        self.assertEqual(Certificate.objects.count(), 0)

    def test_bulk_test_runs_checks(self):
        self.client.force_login(self.owner)
        with mock.patch("apps.monitoring.runner.run_check") as run:
            run.return_value = (None, _ok_result())
            resp = self.client.post(
                reverse("cert-bulk"),
                {"action": "test", "ids": [self.c1.id, self.c2.id]},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Chequeo en curso")
        self.assertEqual(run.call_count, 2)

    def test_bulk_assign_group(self):
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse("cert-bulk"),
            {"action": "assign", "team": self.dest.id, "ids": [self.c1.id, self.c2.id]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Grupo asignado")
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.team, self.dest)

    def test_bulk_assign_foreign_group_blocked(self):
        member = User.objects.create_user("m@certforge.test", "x")
        Membership.objects.create(user=member, team=self.team, role=MembershipRole.CONTRIBUTOR)
        foreign = Team.objects.create(name="Foraneo")
        self.client.force_login(member)
        resp = self.client.post(
            reverse("cert-bulk"),
            {"action": "assign", "team": foreign.id, "ids": [self.c1.id]},
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(ROOT_URLCONF=URLCONF)
class CertTestDrawerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.member = User.objects.create_user("member@certforge.test", "x")
        self.team = Team.objects.create(name="Plataforma")
        self.other = Team.objects.create(name="Ajeno")
        Membership.objects.create(user=self.member, team=self.team, role=MembershipRole.CONTRIBUTOR)
        self.cert = Certificate.objects.create(domain="api.ejemplo.com", port=443, team=self.team)
        self.foreign_cert = Certificate.objects.create(domain="x.ejemplo.com", port=443, team=self.other)

    def test_get_opens_drawer_shell(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("cert-test", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Probar ahora")
        self.assertContains(resp, "api.ejemplo.com")

    def test_post_real_result_ok(self):
        self.client.force_login(self.member)
        with mock.patch("apps.monitoring.runner.run_check") as run:
            run.return_value = (None, _ok_result())
            resp = self.client.post(reverse("cert-test", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Certificado leído y validado")
        self.assertContains(resp, "Let&#x27;s Encrypt")

    def test_post_error_timeout_path(self):
        # Sin mockear el runner: el servicio anti-SSRF rechaza un host interno
        # (.localhost resuelve a loopback) => CheckResult ok=False (ERROR).
        self.cert.domain = "localhost"
        self.cert.save(update_fields=["domain"])
        self.client.force_login(self.member)
        resp = self.client.post(reverse("cert-test", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "El chequeo falló")

    def test_member_cannot_test_foreign_cert(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse("cert-test", args=[self.foreign_cert.id]))
        self.assertEqual(resp.status_code, 404)

    def test_throttle_returns_429(self):
        self.client.force_login(self.member)
        from apps.web import views_certificates as vc
        with mock.patch.object(vc, "TEST_THROTTLE_MAX", 2), \
                mock.patch("apps.monitoring.runner.run_check") as run:
            run.return_value = (None, _ok_result())
            # Las primeras dos pasan; la tercera supera el límite.
            self.client.post(reverse("cert-test", args=[self.cert.id]))
            self.client.post(reverse("cert-test", args=[self.cert.id]))
            resp = self.client.post(reverse("cert-test", args=[self.cert.id]))
        self.assertEqual(resp.status_code, 429)
        self.assertContains(resp, "Demasiadas pruebas", status_code=429)


@override_settings(ROOT_URLCONF=URLCONF)
class CertExportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@certforge.test", "x", is_owner=True)
        self.team = Team.objects.create(name="Plataforma")
        Certificate.objects.create(domain="api.ejemplo.com", port=443, team=self.team)

    def test_export_csv(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("cert-export"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", resp["Content-Disposition"])
        body = resp.content.decode("utf-8")
        self.assertIn("Dominio", body)
        self.assertIn("api.ejemplo.com", body)
