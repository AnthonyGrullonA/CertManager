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

    def test_check_uses_cron_within_window(self):
        import datetime

        from apscheduler.schedulers.background import BackgroundScheduler

        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()
        org.preferred_check_window_start = datetime.time(2, 0)
        org.save()
        s = scheduler._build(BackgroundScheduler())
        job = s.get_job("check_certificates")
        self.assertEqual(type(job.trigger).__name__, "CronTrigger")

    def test_check_falls_back_to_interval_without_window(self):
        from apscheduler.schedulers.background import BackgroundScheduler

        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()
        org.preferred_check_window_start = None
        org.preferred_check_window_end = None
        org.save()
        s = scheduler._build(BackgroundScheduler())
        job = s.get_job("check_certificates")
        self.assertEqual(type(job.trigger).__name__, "IntervalTrigger")

    def test_interval_uses_org_check_interval_hours(self):
        from apscheduler.schedulers.background import BackgroundScheduler

        from apps.core.models import OrganizationSettings

        org = OrganizationSettings.load()
        org.preferred_check_window_start = None
        org.preferred_check_window_end = None
        org.check_interval_hours = 6
        org.save()
        s = scheduler._build(BackgroundScheduler())
        job = s.get_job("check_certificates")
        self.assertEqual(job.trigger.interval.total_seconds(), 6 * 3600)

    @override_settings(SCHEDULER={"CERT_CHECK_HOURS": 24, "REPORTS_MINUTES": 60})
    def test_run_scheduler_command_importable(self):
        # El comando existe y es importable (no lo arrancamos: bloquearía).
        from apps.monitoring.management.commands import run_scheduler
        self.assertTrue(hasattr(run_scheduler, "Command"))
