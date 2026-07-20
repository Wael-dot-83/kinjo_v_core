"""B3 — forecast/anomaly attendance series is computed with a bounded number of
queries and yields identical results to the per-day computation."""
from datetime import date

from sqlalchemy import event

import models
from manager_analytics import ManagerAnalyticsService as MA

WIN_START = date(2026, 6, 1)   # Mon
WIN_END = date(2026, 6, 10)    # Wed (spans a Fri/Sat weekend + a closed day)


def _log(test_db, child_id, class_id, d, status, rb):
    test_db.add(models.AttendanceLog(child_id=child_id, class_id=class_id, date=d,
                                     status=status, recorded_by=rb))


def _seed(test_db, kg, cls, child, rb):
    S = models.AttendanceStatus
    _log(test_db, child, cls, date(2026, 6, 1), S.PRESENT, rb)
    _log(test_db, child, cls, date(2026, 6, 2), S.LATE, rb)
    _log(test_db, child, cls, date(2026, 6, 3), S.ABSENT, rb)     # excluded from numerator
    _log(test_db, child, cls, date(2026, 6, 4), S.PRESENT, rb)
    _log(test_db, child, cls, date(2026, 6, 8), S.PRESENT, rb)
    # explicitly close Jun 4 -> that day's rate must be 0 even though present
    test_db.add(models.OperatingCalendar(kindergarten_id=kg, date=date(2026, 6, 4), is_open=False))
    test_db.commit()


def _count_queries(test_db, fn):
    bind = test_db.get_bind()
    n = {"c": 0}
    def before(*a, **k):
        n["c"] += 1
    event.listen(bind, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(bind, "before_cursor_execute", before)
    return n["c"]


def test_batched_daily_rates_match_per_day(test_db, sample_kindergarten, sample_child,
                                           sample_class, active_enrollment, manager_user):
    kg, cls, child, rb = sample_kindergarten.id, sample_class.id, sample_child.id, manager_user.id
    _seed(test_db, kg, cls, child, rb)

    batched = MA._compute_daily_attendance_rates(test_db, kg, WIN_START, WIN_END)

    cursor = WIN_START
    while cursor <= WIN_END:
        reference = MA.compute_attendance_rate(test_db, kg, cursor, cursor)
        assert batched[cursor] == reference, f"mismatch on {cursor}: {batched[cursor]} != {reference}"
        cursor = date.fromordinal(cursor.toordinal() + 1)

    # every day in the range is a key; days with no expected attendance are None
    # ("nothing was expected") rather than 0.0 ("nobody turned up")
    assert (WIN_END.toordinal() - WIN_START.toordinal() + 1) == len(batched)
    assert batched[date(2026, 6, 4)] is None   # closed day
    assert batched[date(2026, 6, 6)] is None   # Saturday, no data


def test_batched_daily_rates_query_count_bounded(test_db, sample_kindergarten, sample_child,
                                                 sample_class, active_enrollment, manager_user):
    kg, cls, child, rb = sample_kindergarten.id, sample_class.id, sample_child.id, manager_user.id
    _seed(test_db, kg, cls, child, rb)
    # 40-day window would be ~120 queries with the old per-day loop.
    q = _count_queries(test_db, lambda: MA._compute_daily_attendance_rates(
        test_db, kg, date(2026, 5, 1), date(2026, 6, 10)))
    assert q <= 5, f"expected <=5 queries, got {q}"
