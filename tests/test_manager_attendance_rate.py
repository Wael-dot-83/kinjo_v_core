"""B1/B2 — manager attendance-rate math.

Numerator counts only PRESENT/LATE (ABSENT and EXCUSED excluded); denominator is
active enrollments * *operating* days from OperatingCalendar (closed days
excluded), not raw calendar days. Returns a percentage in [0, 100].
"""
from datetime import date

import models
from manager_analytics import ManagerAnalyticsService as MA


# A Mon–Fri window in 2026: Jun 1 Mon .. Jun 5 Fri.
START = date(2026, 6, 1)
END = date(2026, 6, 5)


def _log(test_db, child_id, class_id, d, status, recorded_by):
    test_db.add(models.AttendanceLog(child_id=child_id, class_id=class_id, date=d,
                                     status=status, recorded_by=recorded_by))


def test_absences_and_excused_excluded_from_numerator(test_db, sample_kindergarten,
                                                      sample_child, sample_class, active_enrollment,
                                                      manager_user):
    kg = sample_kindergarten.id
    c, cls, rb = sample_child.id, sample_class.id, manager_user.id
    # Default operating days for Jun 1–5: Mon–Thu open, Fri(4) closed => 4 days.
    _log(test_db, c, cls, date(2026, 6, 1), models.AttendanceStatus.PRESENT, rb)  # counts
    _log(test_db, c, cls, date(2026, 6, 2), models.AttendanceStatus.LATE, rb)     # counts
    _log(test_db, c, cls, date(2026, 6, 3), models.AttendanceStatus.ABSENT, rb)   # excluded
    _log(test_db, c, cls, date(2026, 6, 4), models.AttendanceStatus.EXCUSED, rb)  # excluded
    test_db.commit()

    rate = MA.compute_attendance_rate(test_db, kg, START, END)
    # attended = 2 (present+late); expected = 1 active * 4 operating days = 4 => 50%
    assert rate == 50.0


def test_closed_days_excluded_from_denominator(test_db, sample_kindergarten,
                                               sample_child, sample_class, active_enrollment,
                                               manager_user):
    kg = sample_kindergarten.id
    c, cls, rb = sample_child.id, sample_class.id, manager_user.id
    _log(test_db, c, cls, date(2026, 6, 1), models.AttendanceStatus.PRESENT, rb)
    _log(test_db, c, cls, date(2026, 6, 2), models.AttendanceStatus.PRESENT, rb)
    # Explicitly close Jun 3 and Jun 4 => operating days drop from 4 to 2.
    test_db.add(models.OperatingCalendar(kindergarten_id=kg, date=date(2026, 6, 3), is_open=False))
    test_db.add(models.OperatingCalendar(kindergarten_id=kg, date=date(2026, 6, 4), is_open=False))
    test_db.commit()

    rate = MA.compute_attendance_rate(test_db, kg, START, END)
    # attended = 2; expected = 1 * 2 operating days = 2 => 100%
    assert rate == 100.0


def test_rate_below_100_when_absence_exists(test_db, sample_kindergarten,
                                            sample_child, sample_class, active_enrollment,
                                            manager_user):
    kg = sample_kindergarten.id
    c, cls, rb = sample_child.id, sample_class.id, manager_user.id
    _log(test_db, c, cls, date(2026, 6, 1), models.AttendanceStatus.PRESENT, rb)
    _log(test_db, c, cls, date(2026, 6, 2), models.AttendanceStatus.ABSENT, rb)
    test_db.commit()

    rate = MA.compute_attendance_rate(test_db, kg, START, END)
    assert 0.0 <= rate < 100.0


def test_operating_days_default_excludes_weekend(test_db, sample_kindergarten):
    # Jun 1 (Mon) .. Jun 7 (Sun): Mon–Thu + Sun open, Fri/Sat closed => 5 days.
    days = MA._count_operating_days(test_db, sample_kindergarten.id, date(2026, 6, 1), date(2026, 6, 7))
    assert days == 5
