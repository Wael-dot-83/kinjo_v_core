"""Closed days must be unavailable observations, never 0% attendance.

Background: `_compute_daily_attendance_rates` mapped closed days, weekends and
days with no active enrolment to 0.0, while the scalar helper it documents itself
as matching returns None. Both consumers — the forecast regression and the anomaly
baseline — then consumed roughly two days in seven as a genuine 0% attendance day.
That dragged the trend line down and made every weekend a multi-sigma anomaly,
which also inflated the baseline standard deviation and masked real dips.

The distinction this pins down has three states, and the middle one is the whole
point — filtering "all zeros" would be just as wrong as the original bug:

    closed day / nothing expected -> None  (no observation)
    open day, nobody attended     -> 0.0   (a real, important observation)
    open day, some attended       -> >0.0
"""
from datetime import date, timedelta

import pytest

import models
from manager_analytics import ManagerAnalyticsService as MA

# 2026-06-01 is a Monday. Jordan's school week is Sun-Thu; Fri/Sat are closed.
MONDAY = date(2026, 6, 1)
FRIDAY = date(2026, 6, 5)
SATURDAY = date(2026, 6, 6)


def _enroll(db, kg, child, cls, start, end):
    db.add(models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        class_id=cls.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=start,
        enrollment_end_date=end,
    ))
    db.commit()


def _log(db, cls, child, recorded_by, day, status):
    db.add(models.AttendanceLog(
        child_id=child.id,
        class_id=cls.id,
        date=day,
        status=status,
        recorded_by=recorded_by,
    ))
    db.commit()


class TestClosedDayIsUnavailable:
    def test_weekend_is_none_not_zero(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        _enroll(test_db, sample_kindergarten, sample_child, sample_class,
                MONDAY, MONDAY + timedelta(days=13))
        rates = MA._compute_daily_attendance_rates(
            test_db, sample_kindergarten.id, MONDAY, MONDAY + timedelta(days=13)
        )
        assert rates[FRIDAY] is None, "Friday is closed — not a 0% attendance day"
        assert rates[SATURDAY] is None, "Saturday is closed — not a 0% attendance day"

    def test_custom_closed_day_via_operating_calendar_is_none(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        """An explicitly closed working day must also be unavailable, not 0%."""
        _enroll(test_db, sample_kindergarten, sample_child, sample_class,
                MONDAY, MONDAY + timedelta(days=6))
        test_db.add(models.OperatingCalendar(
            kindergarten_id=sample_kindergarten.id, date=MONDAY, is_open=False,
        ))
        test_db.commit()
        rates = MA._compute_daily_attendance_rates(
            test_db, sample_kindergarten.id, MONDAY, MONDAY + timedelta(days=6)
        )
        assert rates[MONDAY] is None

    def test_every_day_in_range_is_still_a_key(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        """Unavailable must be expressed as None, not as an absent key."""
        end = MONDAY + timedelta(days=13)
        rates = MA._compute_daily_attendance_rates(
            test_db, sample_kindergarten.id, MONDAY, end
        )
        assert len(rates) == (end - MONDAY).days + 1


class TestGenuineZeroIsPreserved:
    """The case that makes "just filter zeros" wrong."""

    def test_open_day_with_no_attendance_is_zero_not_none(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        _enroll(test_db, sample_kindergarten, sample_child, sample_class,
                MONDAY, MONDAY + timedelta(days=6))
        # Monday is open and a child is enrolled, but nobody attended.
        rates = MA._compute_daily_attendance_rates(
            test_db, sample_kindergarten.id, MONDAY, MONDAY
        )
        assert rates[MONDAY] == 0.0, (
            "an open day with an enrolled child and no attendance is a real 0%, "
            "which must stay distinguishable from a closed day"
        )

    def test_open_day_with_attendance_is_positive(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        _enroll(test_db, sample_kindergarten, sample_child, sample_class,
                MONDAY, MONDAY + timedelta(days=6))
        _log(test_db, sample_class, sample_child, admin_user.id,
             MONDAY, models.AttendanceStatus.PRESENT)
        rates = MA._compute_daily_attendance_rates(
            test_db, sample_kindergarten.id, MONDAY, MONDAY
        )
        assert rates[MONDAY] == 100.0

    def test_no_enrolment_is_none_not_zero(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        """No expected child-days is 'no data', distinct from a 0% turnout."""
        rates = MA._compute_daily_attendance_rates(
            test_db, sample_kindergarten.id, MONDAY, MONDAY
        )
        assert rates[MONDAY] is None


class TestScalarAndBulkAgree:
    """The batched helper documents itself as matching the scalar one."""

    def test_batched_matches_scalar_for_every_day(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        from kpi_service import KPIService

        end = MONDAY + timedelta(days=13)
        _enroll(test_db, sample_kindergarten, sample_child, sample_class, MONDAY, end)
        _log(test_db, sample_class, sample_child, admin_user.id,
             MONDAY, models.AttendanceStatus.PRESENT)

        batched = MA._compute_daily_attendance_rates(
            test_db, sample_kindergarten.id, MONDAY, end
        )
        cursor = MONDAY
        while cursor <= end:
            scalar = KPIService.compute_attendance_rate(
                test_db, sample_kindergarten.id, cursor, cursor
            )
            assert batched[cursor] == scalar, f"disagreement on {cursor}"
            cursor += timedelta(days=1)


class TestConsumersExcludeClosedDays:
    """Closed days must not reach regression inputs or the anomaly baseline.

    These exercise the public consumers, which look back from *today*, so the
    fixture data is anchored to the project's current date rather than a fixed one.
    """

    @staticmethod
    def _seed_recent(db, kg, cls, child, recorder, lookback, skip=None):
        """Perfect attendance on every open day in the lookback window."""
        from utils.time_utils import today_amman

        today = today_amman()
        start = today - timedelta(days=lookback)
        _enroll(db, kg, child, cls, start, today)
        cursor = start
        while cursor <= today:
            if cursor.weekday() not in (4, 5) and cursor != skip:
                _log(db, cls, child, recorder, cursor,
                     models.AttendanceStatus.PRESENT)
            cursor += timedelta(days=1)
        return today, start

    def test_forecast_excludes_closed_days(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        """A perfect-attendance history must not forecast a decline from weekends."""
        self._seed_recent(test_db, sample_kindergarten, sample_class,
                          sample_child, admin_user.id, lookback=20)

        result = MA.compute_attendance_forecast(
            test_db, sample_kindergarten.id, lookback_days=20
        )
        observed = [h["rate"] for h in result["historical"] if h["rate"] is not None]
        assert observed, "expected some observed days"
        assert all(r == 100.0 for r in observed), (
            f"perfect attendance polluted by closed days: {sorted(set(observed))}"
        )
        assert result["trend"] != "declining", (
            "weekends must not manufacture a declining attendance trend"
        )

    def test_closed_days_are_null_in_the_series_not_zero(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        """The API contract keeps closed days visible but unmeasured."""
        self._seed_recent(test_db, sample_kindergarten, sample_class,
                          sample_child, admin_user.id, lookback=20)
        result = MA.compute_attendance_forecast(
            test_db, sample_kindergarten.id, lookback_days=20
        )
        by_date = {h["date"]: h["rate"] for h in result["historical"]}
        weekend = [
            d for d in by_date
            if date.fromisoformat(d).weekday() in (4, 5)
        ]
        assert weekend, "window should contain at least one closed day"
        assert all(by_date[d] is None for d in weekend), (
            "closed days must serialise as null, never as 0 — a chart would "
            "otherwise render them as catastrophic attendance"
        )

    def test_anomaly_baseline_ignores_weekends(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        """Uniform open-day attendance has zero variance — no weekend anomalies."""
        today, start = self._seed_recent(
            test_db, sample_kindergarten, sample_class, sample_child,
            admin_user.id, lookback=20,
        )
        result = MA.detect_anomalies(
            test_db, sample_kindergarten.id, lookback_days=20
        )
        flagged = {str(a["date"]) for a in result.get("anomalies", [])}
        weekend_days = {
            str(start + timedelta(days=i))
            for i in range((today - start).days + 1)
            if (start + timedelta(days=i)).weekday() in (4, 5)
        }
        assert not (flagged & weekend_days), (
            f"closed days flagged as anomalies: {sorted(flagged & weekend_days)}"
        )

    def test_real_dip_on_an_open_day_is_still_detectable(
        self, test_db, sample_kindergarten, sample_class, sample_child, admin_user
    ):
        """Excluding closed days must not blunt sensitivity to genuine drops."""
        from utils.time_utils import today_amman

        today = today_amman()
        dip = today - timedelta(days=5)
        while dip.weekday() in (4, 5):  # ensure the dip lands on an open day
            dip -= timedelta(days=1)
        self._seed_recent(test_db, sample_kindergarten, sample_class,
                          sample_child, admin_user.id, lookback=20, skip=dip)

        result = MA.detect_anomalies(
            test_db, sample_kindergarten.id, lookback_days=20
        )
        assert result.get("status") != "insufficient_data"
        flagged = {str(a["date"]) for a in result.get("anomalies", [])}
        assert str(dip) in flagged, (
            "a genuine open-day dip to 0% must still be flagged after closed days "
            f"are excluded; flagged={sorted(flagged)}"
        )
