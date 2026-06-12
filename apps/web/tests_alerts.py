"""Tests del Centro de Alertas y del panel de notificaciones (work-stream B).

Diseño nuevo:
- La campana muestra las alertas OPEN del ámbito (ya NO se aplica el sello
  ``panel_cleared_at``: limpiar = resolver).
- "Resolver" (estado compartido) es Admin/Owner: pasa la alerta a RESUELTA, sale
  del panel y del set "abierto", pero permanece en el Centro (histórico).
- "Marcar leída" (estado personal) lo puede hacer cualquiera con visibilidad.
- Detalle de la alerta en un drawer (alert-detail).
"""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alerts.models import Alert, AlertDelivery, AlertUserState
from apps.certificates.models import Certificate  # noqa: F401  (usado en setUp/tests)
from apps.core.enums import (
    AlertSeverity,
    AlertStatus,
    MembershipRole,
    NotificationChannel,
)
from apps.teams.models import Membership, Team
from apps.web.views_alerts import _panel_count

User = get_user_model()

HX = {"HTTP_HX_REQUEST": "true"}


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class AlertCenterBaseTest(TestCase):
    """Fixtures comunes: un grupo, un miembro (NO admin) y varias alertas."""

    def setUp(self):
        self.team = Team.objects.create(name="Infra")
        self.user = User.objects.create_user(email="miembro@cf.test", password="x")
        Membership.objects.create(user=self.user, team=self.team, role=MembershipRole.CONTRIBUTOR)
        self.cert = Certificate.objects.create(domain="api.cf.test", team=self.team)
        self.client.force_login(self.user)

    def _alert(self, severity=AlertSeverity.POR_VENCER, status=AlertStatus.OPEN,
               message="Vence pronto", channel=NotificationChannel.EMAIL):
        alert = Alert.objects.create(
            certificate=self.cert, severity=severity, status=status, message=message,
        )
        AlertDelivery.objects.create(alert=alert, channel=channel, target="x@cf.test")
        return alert

    def _make_admin(self, email="admin@cf.test"):
        admin = User.objects.create_user(email=email, password="x")
        Membership.objects.create(user=admin, team=self.team, role=MembershipRole.ADMIN)
        return admin


class AlertCenterViewTests(AlertCenterBaseTest):
    def test_center_returns_200_and_lists_all(self):
        self._alert(message="A1")
        self._alert(severity=AlertSeverity.ERROR, status=AlertStatus.OPEN, message="A2")
        resp = self.client.get(reverse("alert-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Centro de alertas")
        self.assertContains(resp, "A1")
        self.assertContains(resp, "A2")

    def test_htmx_request_returns_only_rows(self):
        self._alert(message="solo-filas")
        resp = self.client.get(reverse("alert-list"), **HX)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "solo-filas")
        self.assertNotContains(resp, "<html")

    def test_tab_unread_filters_read(self):
        a_read = self._alert(message="YA-VISTA")
        self._alert(message="PENDIENTE")
        AlertUserState.objects.create(alert=a_read, user=self.user, read_at=timezone.now())
        resp = self.client.get(reverse("alert-list"), {"tab": "noleidas"}, **HX)
        self.assertContains(resp, "PENDIENTE")
        self.assertNotContains(resp, "YA-VISTA")

    def test_tab_criticas_includes_critico_and_vencido(self):
        self._alert(severity=AlertSeverity.CRITICO, message="crit")
        self._alert(severity=AlertSeverity.VENCIDO, message="venc")
        self._alert(severity=AlertSeverity.POR_VENCER, message="porvencer")
        resp = self.client.get(reverse("alert-list"), {"tab": "criticas"}, **HX)
        self.assertContains(resp, "crit")
        self.assertContains(resp, "venc")
        self.assertNotContains(resp, "porvencer")

    def test_tab_error_filters_error_only(self):
        self._alert(severity=AlertSeverity.ERROR, message="err1")
        self._alert(severity=AlertSeverity.POR_VENCER, message="pv1")
        resp = self.client.get(reverse("alert-list"), {"tab": "error"}, **HX)
        self.assertContains(resp, "err1")
        self.assertNotContains(resp, "pv1")

    def test_invalid_tab_falls_back_to_todas(self):
        self._alert(message="vis")
        resp = self.client.get(reverse("alert-list"), {"tab": "bogus"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "vis")

    def test_scope_isolation_other_team_not_listed(self):
        other = Team.objects.create(name="Otro")
        cert2 = Certificate.objects.create(domain="ajeno.test", team=other)
        Alert.objects.create(
            certificate=cert2, severity=AlertSeverity.ERROR,
            status=AlertStatus.OPEN, message="AJENA",
        )
        resp = self.client.get(reverse("alert-list"))
        self.assertNotContains(resp, "AJENA")


class PanelEndpointTests(AlertCenterBaseTest):
    def test_panel_lists_open_alerts(self):
        self._alert(message="en-panel")
        resp = self.client.get(reverse("alert-panel"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "en-panel")

    def test_panel_empty_message(self):
        resp = self.client.get(reverse("alert-panel"))
        self.assertContains(resp, "No tienes alertas abiertas")

    def test_open_alerts_appear_regardless_of_old_seal(self):
        """Regresión: una alerta OPEN aparece en la campana aunque exista un
        sello panel_cleared_at antiguo (ya no se aplica)."""
        from apps.accounts.models import get_or_create_preferences

        prefs = get_or_create_preferences(self.user)
        prefs.panel_cleared_at = timezone.now()
        prefs.save(update_fields=["panel_cleared_at"])
        self._alert(message="aparece-igual")
        self.assertEqual(_panel_count(self.user), 1)
        resp = self.client.get(reverse("alert-panel"))
        self.assertContains(resp, "aparece-igual")


class ReadStateTests(AlertCenterBaseTest):
    def test_read_marks_read_without_resolving(self):
        alert = self._alert()
        self.assertEqual(_panel_count(self.user), 1)
        resp = self.client.post(reverse("alert-read", args=[alert.id]), **HX)
        self.assertEqual(resp.status_code, 200)
        state = AlertUserState.objects.get(alert=alert, user=self.user)
        self.assertIsNotNone(state.read_at)
        # read baja el badge de nuevas pero NO resuelve: la alerta sigue abierta.
        self.assertEqual(_panel_count(self.user), 0)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.OPEN)
        panel = self.client.get(reverse("alert-panel"))
        self.assertContains(panel, "Vence pronto")

    def test_read_response_includes_toast_and_badge_oob(self):
        alert = self._alert()
        resp = self.client.post(reverse("alert-read", args=[alert.id]), **HX)
        self.assertContains(resp, "forge-toast")
        self.assertContains(resp, "forge-notif-badge")
        self.assertEqual(resp["HX-Trigger"], "cf:alerts-changed")

    def test_read_is_idempotent(self):
        alert = self._alert()
        self.client.post(reverse("alert-read", args=[alert.id]), **HX)
        first = AlertUserState.objects.get(alert=alert, user=self.user).read_at
        self.client.post(reverse("alert-read", args=[alert.id]), **HX)
        second = AlertUserState.objects.get(alert=alert, user=self.user).read_at
        self.assertEqual(first, second)


class ReadAllTests(AlertCenterBaseTest):
    def test_read_all_marks_all_and_clears_badge(self):
        self._alert(message="a")
        self._alert(message="b")
        self.assertEqual(_panel_count(self.user), 2)
        resp = self.client.post(reverse("alert-read-all"), **HX)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            AlertUserState.objects.filter(user=self.user, read_at__isnull=False).count(), 2
        )
        self.assertEqual(_panel_count(self.user), 0)
        panel = self.client.get(reverse("alert-panel"))
        self.assertContains(panel, "a")
        self.assertContains(panel, "b")


class ResolveTests(AlertCenterBaseTest):
    """Resolver = estado compartido (Admin/Owner). Sale del panel; queda en centro."""

    def test_admin_resolve_removes_from_panel_keeps_in_center(self):
        admin = self._make_admin()
        alert = self._alert(message="resuelveme")
        self.client.force_login(admin)
        resp = self.client.post(reverse("alert-resolve", args=[alert.id]), **HX)
        self.assertEqual(resp.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)
        self.assertIsNotNone(alert.resolved_at)
        # Sale del panel para todos (estado compartido).
        self.assertEqual(_panel_count(admin), 0)
        self.assertEqual(_panel_count(self.user), 0)
        # Permanece en el centro con tag "Resuelta".
        center = self.client.get(reverse("alert-list"))
        self.assertContains(center, "resuelveme")
        self.assertContains(center, "Resuelta")

    def test_member_cannot_resolve(self):
        alert = self._alert(message="protegida")
        resp = self.client.post(reverse("alert-resolve", args=[alert.id]), **HX)
        self.assertEqual(resp.status_code, 403)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.OPEN)

    def test_owner_can_resolve(self):
        owner = User.objects.create_user(email="own@cf.test", password="x", is_owner=True)
        alert = self._alert(message="por-owner")
        self.client.force_login(owner)
        resp = self.client.post(reverse("alert-resolve", args=[alert.id]), **HX)
        self.assertEqual(resp.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)

    def test_resolve_is_idempotent(self):
        admin = self._make_admin()
        alert = self._alert()
        self.client.force_login(admin)
        self.client.post(reverse("alert-resolve", args=[alert.id]), **HX)
        first = Alert.objects.get(pk=alert.id).resolved_at
        self.client.post(reverse("alert-resolve", args=[alert.id]), **HX)
        second = Alert.objects.get(pk=alert.id).resolved_at
        self.assertEqual(first, second)


class ResolveAllTests(AlertCenterBaseTest):
    def test_admin_resolve_all_empties_panel_center_keeps_history(self):
        admin = self._make_admin()
        for i in range(3):
            self._alert(message=f"hist-{i}")
        self.client.force_login(admin)
        resp = self.client.post(reverse("alert-resolve-all"), **HX)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No tienes alertas abiertas")
        self.assertEqual(_panel_count(admin), 0)
        # El centro conserva las 3 como resueltas.
        center = self.client.get(reverse("alert-list"))
        for i in range(3):
            self.assertContains(center, f"hist-{i}")
        self.assertContains(center, "Resuelta")

    def test_member_resolve_all_does_nothing(self):
        for i in range(2):
            self._alert(message=f"m-{i}")
        resp = self.client.post(reverse("alert-resolve-all"), **HX)
        self.assertEqual(resp.status_code, 200)
        # El miembro no gestiona ninguna: siguen abiertas.
        self.assertEqual(Alert.objects.filter(status=AlertStatus.OPEN).count(), 2)


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class SharedVsPersonalTests(TestCase):
    """read es personal (aísla por usuario); resolve es compartido (afecta a todos)."""

    def setUp(self):
        self.team = Team.objects.create(name="Compartido")
        self.admin = User.objects.create_user(email="adm@cf.test", password="x")
        self.b = User.objects.create_user(email="b@cf.test", password="x")
        Membership.objects.create(user=self.admin, team=self.team, role=MembershipRole.ADMIN)
        Membership.objects.create(user=self.b, team=self.team, role=MembershipRole.CONTRIBUTOR)
        self.cert = Certificate.objects.create(domain="shared.test", team=self.team)
        for i in range(2):
            Alert.objects.create(
                certificate=self.cert, severity=AlertSeverity.POR_VENCER,
                status=AlertStatus.OPEN, message=f"shared-{i}",
            )

    def test_read_by_a_does_not_affect_b(self):
        alert = self.cert.alerts.first()
        self.client.force_login(self.admin)
        self.client.post(reverse("alert-read", args=[alert.id]), **HX)
        self.assertEqual(_panel_count(self.admin), 1)
        self.assertEqual(_panel_count(self.b), 2)

    def test_resolve_by_admin_affects_everyone(self):
        self.assertEqual(_panel_count(self.b), 2)
        self.client.force_login(self.admin)
        self.client.post(reverse("alert-resolve-all"), **HX)
        # Resolver es compartido: B también deja de verlas en la campana.
        self.assertEqual(_panel_count(self.b), 0)


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class RbacTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="RBAC")
        self.member = User.objects.create_user(email="m@cf.test", password="x")
        Membership.objects.create(user=self.member, team=self.team, role=MembershipRole.CONTRIBUTOR)
        self.cert = Certificate.objects.create(domain="rbac.test", team=self.team)
        self.alert = Alert.objects.create(
            certificate=self.cert, severity=AlertSeverity.ERROR,
            status=AlertStatus.OPEN, message="rbac",
        )

    def test_plain_member_can_read_but_not_resolve(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(reverse("alert-read", args=[self.alert.id]), **HX).status_code, 200)
        self.assertEqual(self.client.post(reverse("alert-resolve", args=[self.alert.id]), **HX).status_code, 403)

    def test_outsider_gets_404_on_other_scope_alert(self):
        outsider = User.objects.create_user(email="out@cf.test", password="x")
        other_team = Team.objects.create(name="Solo-suyo")
        Membership.objects.create(user=outsider, team=other_team, role=MembershipRole.CONTRIBUTOR)
        self.client.force_login(outsider)
        resp = self.client.post(reverse("alert-read", args=[self.alert.id]), **HX)
        self.assertEqual(resp.status_code, 404)

    def test_requires_authentication(self):
        resp = self.client.get(reverse("alert-list"))
        self.assertEqual(resp.status_code, 302)


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class AlertDetailTests(AlertCenterBaseTest):
    def test_detail_renders_drawer_with_message_and_channel(self):
        alert = self._alert(message="detalle-aqui", channel=NotificationChannel.EMAIL)
        resp = self.client.get(reverse("alert-detail", args=[alert.id]), **HX)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "forge-drawer")
        self.assertContains(resp, "detalle-aqui")
        self.assertContains(resp, "api.cf.test")
        self.assertContains(resp, "Entregas")

    def test_opening_detail_marks_read(self):
        alert = self._alert()
        self.assertEqual(_panel_count(self.user), 1)
        self.client.get(reverse("alert-detail", args=[alert.id]), **HX)
        state = AlertUserState.objects.get(alert=alert, user=self.user)
        self.assertIsNotNone(state.read_at)

    def test_detail_resolve_button_only_for_managers(self):
        alert = self._alert()
        # Miembro: sin botón resolver.
        resp = self.client.get(reverse("alert-detail", args=[alert.id]), **HX)
        self.assertNotContains(resp, reverse("alert-resolve", args=[alert.id]))
        # Admin: con botón resolver.
        admin = self._make_admin()
        self.client.force_login(admin)
        resp = self.client.get(reverse("alert-detail", args=[alert.id]), **HX)
        self.assertContains(resp, reverse("alert-resolve", args=[alert.id]))

    def test_detail_outsider_404(self):
        other = Team.objects.create(name="Ajeno")
        cert2 = Certificate.objects.create(domain="x.ajeno", team=other)
        alert = Alert.objects.create(
            certificate=cert2, severity=AlertSeverity.ERROR,
            status=AlertStatus.OPEN, message="no",
        )
        resp = self.client.get(reverse("alert-detail", args=[alert.id]), **HX)
        self.assertEqual(resp.status_code, 404)


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class AlertCenterStructureTests(AlertCenterBaseTest):
    def test_center_renders_four_tabs_with_counts(self):
        self._alert(message="A")
        self._alert(severity=AlertSeverity.ERROR, message="B")
        resp = self.client.get(reverse("alert-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'role="tab"', count=4)
        self.assertContains(resp, "Todas")
        self.assertContains(resp, "No leídas")
        self.assertContains(resp, "Críticas / vencidas")
        self.assertContains(resp, "Error")
        self.assertContains(resp, 'class="alert-tab__count"')

    def _active_tab_hrefs(self, html):
        anchors = re.findall(r'<a\b[^>]*\bclass="alert-tab[^"]*"[^>]*>', html)
        return [
            re.search(r'href="([^"]*)"', a).group(1)
            for a in anchors
            if "is-active" in a
        ]

    def test_full_page_marks_only_active_tab(self):
        self._alert(message="pend")
        resp = self.client.get(reverse("alert-list"), {"tab": "noleidas"})
        html = resp.content.decode()
        active = self._active_tab_hrefs(html)
        self.assertEqual(len(active), 1, "solo la tab seleccionada debe resaltarse")
        self.assertIn("tab=noleidas", active[0])
        self.assertEqual(html.count('aria-selected="true"'), 1)

    def test_htmx_tab_swap_returns_region_with_single_active(self):
        """El swap HX devuelve la REGIÓN completa (tabs + tabla) con SOLO la tab
        pedida activa, y sin swaps OOB dentro del <tbody> (causa del bug)."""
        self._alert(message="pend")
        resp = self.client.get(reverse("alert-list"), {"tab": "noleidas"}, **HX)
        html = resp.content.decode()
        self.assertContains(resp, 'id="alert-tabs"')
        self.assertContains(resp, 'id="alert-rows"')   # la tabla viene en la respuesta
        self.assertNotContains(resp, "hx-swap-oob")     # ya no hay OOB
        active = self._active_tab_hrefs(html)
        self.assertEqual(len(active), 1)
        self.assertIn("tab=noleidas", active[0])
        self.assertEqual(html.count('aria-selected="true"'), 1)

    def test_unread_pill_and_dot_present(self):
        self._alert(message="pendiente")
        resp = self.client.get(reverse("alert-list"))
        self.assertContains(resp, "sin leer")
        self.assertContains(resp, "alert-row__dot")
        self.assertContains(resp, "alert-row--unread")

    def test_row_badge_uses_status_family_class(self):
        self._alert(severity=AlertSeverity.CRITICO, message="crit-row")
        resp = self.client.get(reverse("alert-list"))
        self.assertContains(resp, "badge--crit")
        self.assertContains(resp, "alert-row__channel")
        self.assertContains(resp, "alert-row__time")

    def test_resolved_rows_shown_dim_with_tag(self):
        alert = self._alert(message="resuelta-vis")
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=["status", "resolved_at"])
        resp = self.client.get(reverse("alert-list"))
        self.assertContains(resp, "resuelta-vis")
        self.assertContains(resp, "alert-row--archived")
        self.assertContains(resp, "alert-row__tag")
        self.assertContains(resp, "Resuelta")

    def test_rows_open_detail_drawer(self):
        alert = self._alert(message="abreme")
        resp = self.client.get(reverse("alert-list"))
        self.assertContains(resp, reverse("alert-detail", args=[alert.id]))
        self.assertContains(resp, 'hx-target="#drawer-root"')

    def test_empty_state_when_no_matches(self):
        self._alert(severity=AlertSeverity.POR_VENCER, message="pv")
        resp = self.client.get(reverse("alert-list"), {"tab": "error"})
        self.assertContains(resp, "alert-empty")
        self.assertContains(resp, "Sin alertas en esta vista")


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class PanelMarkupTests(AlertCenterBaseTest):
    def test_panel_item_markup_and_badge(self):
        self._alert(severity=AlertSeverity.VENCIDO, message="venc-panel")
        resp = self.client.get(reverse("alert-panel"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "forge-notif__item")
        self.assertContains(resp, "forge-notif__item-domain")
        self.assertContains(resp, "forge-notif__item-meta")
        self.assertContains(resp, "badge--exp")
        self.assertContains(resp, "is-unread")
        self.assertContains(resp, "forge-notif__dot")

    def test_panel_item_opens_detail_drawer(self):
        alert = self._alert(message="abrir-detalle")
        resp = self.client.get(reverse("alert-panel"))
        self.assertContains(resp, reverse("alert-detail", args=[alert.id]))
        self.assertContains(resp, 'hx-target="#drawer-root"')

    def test_panel_resolve_button_only_for_managers(self):
        alert = self._alert(message="x")
        # Miembro: sin botón resolver en el ítem.
        resp = self.client.get(reverse("alert-panel"))
        self.assertNotContains(resp, reverse("alert-resolve", args=[alert.id]))
        # Admin: con botón resolver.
        admin = self._make_admin()
        self.client.force_login(admin)
        resp = self.client.get(reverse("alert-panel"))
        self.assertContains(resp, reverse("alert-resolve", args=[alert.id]))

    def test_badge_oob_has_correct_id(self):
        alert = self._alert(message="badge-id")
        resp = self.client.post(reverse("alert-read", args=[alert.id]), **HX)
        self.assertContains(resp, 'id="forge-notif-badge"')

    def test_panel_caps_at_eight_items(self):
        for i in range(12):
            self._alert(message=f"cap-{i}")
        self.assertEqual(_panel_count(self.user), 12)
        resp = self.client.get(reverse("alert-panel"))
        self.assertEqual(resp.content.count(b"forge-notif__item-domain"), 8)


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class PanelResolveLiveTests(AlertCenterBaseTest):
    """Resolver en vivo desde la campana (Admin): la X resuelve y baja el badge."""

    def test_resolve_from_panel_decrements_badge_oob(self):
        admin = self._make_admin()
        a1 = self._alert(message="d1")
        self._alert(message="d2")
        self.client.force_login(admin)
        self.assertEqual(_panel_count(admin), 2)
        resp = self.client.post(reverse("alert-resolve", args=[a1.id]), **HX)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="forge-notif-badge"')
        self.assertEqual(_panel_count(admin), 1)

    def test_resolve_all_empties_and_hides_badge(self):
        admin = self._make_admin()
        self._alert(message="ultima")
        self.client.force_login(admin)
        resp = self.client.post(reverse("alert-resolve-all"), **HX)
        self.assertContains(resp, "forge-notif__badge--empty")
        self.assertEqual(_panel_count(admin), 0)


@override_settings(ROOT_URLCONF="apps.web.test_urls_alerts")
class AlertCenterPaginationTests(AlertCenterBaseTest):
    def test_center_wraps_rows_in_paginated_table(self):
        self._alert(message="pag")
        resp = self.client.get(reverse("alert-list"))
        self.assertContains(resp, "data-forge-table")
        self.assertContains(resp, 'id="alert-rows"')
        self.assertContains(resp, "forge-table-scroll")
        self.assertContains(resp, 'data-page-size="8"')

    def test_rows_are_table_rows(self):
        self._alert(message="fila-tr")
        resp = self.client.get(reverse("alert-list"), **HX)
        self.assertContains(resp, "<tr")
        self.assertContains(resp, "alert-row")
        self.assertNotContains(resp, "<html")

    def test_empty_row_marked_to_skip_pagination(self):
        self._alert(severity=AlertSeverity.POR_VENCER, message="pv")
        resp = self.client.get(reverse("alert-list"), {"tab": "error"})
        self.assertContains(resp, "data-empty-row")


class AlertCenterSortTests(AlertCenterBaseTest):
    def test_table_wrapper_is_sortable(self):
        self._alert(message="ord")
        resp = self.client.get(reverse("alert-list"))
        self.assertContains(resp, "data-forge-sortable")

    def test_header_marks_actions_column_as_no_sort(self):
        self._alert(message="th")
        resp = self.client.get(reverse("alert-list"))
        self.assertContains(resp, "<thead")
        self.assertContains(resp, "data-no-sort")

    def test_htmx_region_includes_full_table(self):
        """El swap HX devuelve la región completa (con <thead> y wrapper), no solo
        el <tbody>: así el parseo es válido y los estilos no se rompen."""
        self._alert(message="con-region")
        full = self.client.get(reverse("alert-list"))
        self.assertContains(full, "<thead")
        region = self.client.get(reverse("alert-list"), **HX)
        self.assertContains(region, "<thead")
        self.assertContains(region, "data-forge-table")
        self.assertNotContains(region, "<html")
