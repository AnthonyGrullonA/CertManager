"""Tests de la lógica de vencimiento de reportes programados (work-stream C).

Cubre EVERY_N_DAYS / MONTHLY_DAY_1, el ajuste de fin de semana → lunes y la
idempotencia por last_run_at.
"""
from datetime import date, datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.enums import ReportFrequency, ReportTemplate
from apps.reports.management.commands.send_scheduled_reports import (
    is_due,
    shift_weekend,
)
from apps.reports.models import ScheduledReport


def _aware_noon(d):
    """Datetime aware a mediodía (evita cruces de fecha por zona horaria)."""
    return timezone.make_aware(datetime.combine(d, time(12, 0)))


def _next_weekday(start, weekday):
    d = start
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


class ShiftWeekendTests(TestCase):
    def test_saturday_moves_to_monday(self):
        sat = _next_weekday(date(2026, 6, 1), 5)
        self.assertEqual(shift_weekend(sat), sat + timedelta(days=2))
        self.assertEqual(shift_weekend(sat).weekday(), 0)

    def test_sunday_moves_to_monday(self):
        sun = _next_weekday(date(2026, 6, 1), 6)
        self.assertEqual(shift_weekend(sun), sun + timedelta(days=1))
        self.assertEqual(shift_weekend(sun).weekday(), 0)

    def test_weekday_unchanged(self):
        wed = _next_weekday(date(2026, 6, 1), 2)
        self.assertEqual(shift_weekend(wed), wed)


class IsDueBaseTest(TestCase):
    def _report(self, **kw):
        kw.setdefault("name", "R")
        kw.setdefault("template", ReportTemplate.INVENTORY)
        return ScheduledReport.objects.create(**kw)


class EveryNDaysTests(IsDueBaseTest):
    def test_due_on_anchor_and_each_interval(self):
        anchor = _next_weekday(date(2026, 6, 1), 0)  # un lunes
        r = self._report(frequency=ReportFrequency.EVERY_N_DAYS, start_date=anchor, interval_days=15)
        self.assertTrue(is_due(r, _aware_noon(anchor)))
        self.assertFalse(is_due(r, _aware_noon(anchor + timedelta(days=1))))
        self.assertTrue(is_due(r, _aware_noon(anchor + timedelta(days=15))))
        self.assertFalse(is_due(r, _aware_noon(anchor + timedelta(days=14))))

    def test_not_due_before_anchor(self):
        anchor = date(2026, 6, 15)
        r = self._report(frequency=ReportFrequency.EVERY_N_DAYS, start_date=anchor, interval_days=15)
        self.assertFalse(is_due(r, _aware_noon(anchor - timedelta(days=1))))

    def test_idempotent_once_sent_today(self):
        anchor = _next_weekday(date(2026, 6, 1), 0)
        r = self._report(frequency=ReportFrequency.EVERY_N_DAYS, start_date=anchor, interval_days=15)
        now = _aware_noon(anchor)
        self.assertTrue(is_due(r, now))
        r.last_run_at = now
        self.assertFalse(is_due(r, now))


class WeekendShiftDueTests(IsDueBaseTest):
    def test_weekend_occurrence_defers_to_monday(self):
        # Ancla en sábado con intervalo diario: el sábado y el domingo NO envían;
        # el lunes sí (reciben los corridos del fin de semana).
        sat = _next_weekday(date(2026, 6, 1), 5)
        r = self._report(frequency=ReportFrequency.EVERY_N_DAYS, start_date=sat, interval_days=1)
        self.assertFalse(is_due(r, _aware_noon(sat)))           # sábado
        self.assertFalse(is_due(r, _aware_noon(sat + timedelta(days=1))))  # domingo
        self.assertTrue(is_due(r, _aware_noon(sat + timedelta(days=2))))   # lunes


class MonthlyDay1Tests(IsDueBaseTest):
    def test_due_on_first_when_weekday(self):
        # Buscamos un mes cuyo día 1 sea día hábil.
        d = date(2026, 1, 1)
        while d.weekday() in (5, 6):
            d = (d.replace(day=28) + timedelta(days=10)).replace(day=1)
        r = self._report(frequency=ReportFrequency.MONTHLY_DAY_1, start_date=date(2026, 1, 1))
        self.assertTrue(is_due(r, _aware_noon(d)))
        self.assertFalse(is_due(r, _aware_noon(d + timedelta(days=1))))

    def test_first_on_weekend_defers_to_monday(self):
        # Mes cuyo día 1 cae fin de semana → el envío es el lunes siguiente.
        d = date(2026, 1, 1)
        while d.weekday() != 6:  # domingo 1
            d = (d.replace(day=28) + timedelta(days=10)).replace(day=1)
        r = self._report(frequency=ReportFrequency.MONTHLY_DAY_1, start_date=date(2026, 1, 1))
        self.assertFalse(is_due(r, _aware_noon(d)))                      # domingo 1
        self.assertTrue(is_due(r, _aware_noon(d + timedelta(days=1))))   # lunes 2


class SendTimeGateTests(IsDueBaseTest):
    def test_not_due_before_send_time(self):
        anchor = _next_weekday(date(2026, 6, 1), 0)
        r = self._report(frequency=ReportFrequency.EVERY_N_DAYS, start_date=anchor,
                         interval_days=1, send_time=time(18, 0))
        morning = timezone.make_aware(datetime.combine(anchor, time(8, 0)))
        evening = timezone.make_aware(datetime.combine(anchor, time(19, 0)))
        self.assertFalse(is_due(r, morning))
        self.assertTrue(is_due(r, evening))
