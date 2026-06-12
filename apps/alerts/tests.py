"""Tests de la migración de datos read_by -> AlertUserState (PASO 2).

Verifica que la migración 0003 es REVERSIBLE y que preserva el estado 'leído':
- forward: cada par (alert, user) de read_by produce un AlertUserState.read_at.
- backward: reconstruye read_by y elimina los estados creados.
"""
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.db.migrations.executor import MigrationExecutor
from django.db import connection

from apps.certificates.models import Certificate
from apps.core.enums import AlertSeverity, AlertStatus
from apps.teams.models import Team

User = get_user_model()


class ReadByDataMigrationTests(TransactionTestCase):
    """Aplica/retrocede la migración de datos sobre datos reales."""

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        executor.loader.build_graph()

    def test_forward_creates_state_and_backward_restores_read_by(self):
        from apps.alerts.models import Alert, AlertUserState

        # Estado de partida: posicionarse ANTES de la migración de datos (0002).
        self._migrate([("alerts", "0002_webhookintegration_rich_format_alertuserstate")])

        user = User.objects.create_user(email="lector@cf.test", password="x")
        team = Team.objects.create(name="MigGroup")
        cert = Certificate.objects.create(domain="mig.test", team=team)
        alert = Alert.objects.create(
            certificate=cert, severity=AlertSeverity.POR_VENCER,
            status=AlertStatus.OPEN, message="x",
        )
        alert.read_by.add(user)

        # Forward: la migración de datos crea el estado con read_at.
        self._migrate([("alerts", "0003_migrate_read_by_to_user_state")])
        state = AlertUserState.objects.get(alert_id=alert.id, user_id=user.id)
        self.assertIsNotNone(state.read_at)

        # Backward: reconstruye read_by y borra el estado.
        self._migrate([("alerts", "0002_webhookintegration_rich_format_alertuserstate")])
        self.assertFalse(AlertUserState.objects.filter(alert_id=alert.id, user_id=user.id).exists())
        self.assertTrue(alert.read_by.filter(id=user.id).exists())

    def tearDown(self):
        # Deja la base en el estado más reciente para no afectar otros tests.
        self._migrate([("alerts", "0003_migrate_read_by_to_user_state")])
        super().tearDown()
