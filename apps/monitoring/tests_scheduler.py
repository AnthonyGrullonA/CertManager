"""El planificador en-proceso registra los jobs correctos (sin arrancarlo)."""
from django.test import TestCase, override_settings

from apps.monitoring import scheduler


class SchedulerJobsTests(TestCase):
    def test_build_registers_both_jobs(self):
        from apscheduler.schedulers.background import BackgroundScheduler

        s = scheduler._build(BackgroundScheduler())
        ids = {j.id for j in s.get_jobs()}
        # Certs + reportes + backup (BACKUP_HOURS por defecto > 0).
        self.assertEqual(
            ids, {"check_certificates", "send_scheduled_reports", "backup_db"}
        )

    @override_settings(SCHEDULER={"CERT_CHECK_HOURS": 24, "REPORTS_MINUTES": 60, "BACKUP_HOURS": 0})
    def test_backup_job_omitted_when_disabled(self):
        from apscheduler.schedulers.background import BackgroundScheduler

        s = scheduler._build(BackgroundScheduler())
        ids = {j.id for j in s.get_jobs()}
        self.assertNotIn("backup_db", ids)

    @override_settings(SCHEDULER={"CERT_CHECK_HOURS": 24, "REPORTS_MINUTES": 60})
    def test_run_scheduler_command_importable(self):
        # El comando existe y es importable (no lo arrancamos: bloquearía).
        from apps.monitoring.management.commands import run_scheduler
        self.assertTrue(hasattr(run_scheduler, "Command"))
