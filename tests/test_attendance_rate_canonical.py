"""Canonical attendance-rate definition: bounded, consistent, and not an N+1.

Attendance rate = attended-among-expected child-days / expected child-days × 100, where
a day counts for a child iff it is a working day of the kindergarten (Sun–Thu plus
OperatingCalendar overrides) within the child's effective enrollment range. Because the
attended set is a subset of the expected set, the rate is bounded to [0, 100].

Before this fix the numerator counted every PRESENT/LATE log in the window regardless of
working day or enrollment range, against a denominator that respected both — so a child
present outside enrollment, or on a closed day, produced rates like 333% and 136%.

Every attendance-rate consumer shares one definition (`KPIService._attendance_components_by_child`
and its batched sibling `compute_attendance_components_bulk`): the admin kg-overview
card / network KPI / governorate chart, the KPI dashboard, and the analytics call sites.
These tests pin the definition itself and that the consumers agree.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import models
from kpi_service import KPIService


# ── helpers ────────────────────────────────────────────────────────────────
def _enroll(db, kg, child, start=None, end=None):
    db.add(models.EnrollmentApplication(
        child_id=child.id, kindergarten_id=kg.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=start, enrollment_end_date=end,
    ))
    db.commit()


def _present(db, cls, child, recorder_id, dates, status=None):
    status = status or models.AttendanceStatus.PRESENT
    for d in dates:
        db.add(models.AttendanceLog(
            child_id=child.id, class_id=cls.id, date=d,
            status=status, recorded_by=recorder_id,
        ))
    db.commit()


def _new_child(db, parent_user, first="C"):
    child = models.Child(
        first_name=first, last_name="Test",
        date_of_birth=date(2022, 1, 1), gender="male",
        parent_id=parent_user.id if hasattr(parent_user, "id") else None,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


# ── 1. bounded for ordinary valid data ──────────────────────────────────────
def test_rate_never_exceeds_100_for_valid_data(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """Enrolled the whole window, present every working day AND every weekend day.
    A correct rate is exactly 100 — the weekend logs must not push it over."""
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 1), end=date(2026, 7, 31))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 1) + timedelta(days=i) for i in range(31)])
    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 7, 31))
    assert 0.0 <= rate <= 100.0
    assert rate == 100.0, f"present every working day should be exactly 100, got {rate}"


# ── 2. multi-day window uses expected child-days, not headcount ──────────────
def test_denominator_is_expected_child_days_not_headcount(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """One child, present on exactly half of the working days in a multi-day window.

    A headcount denominator (present_rows / children) would scale with the window and
    give a nonsense number; an expected-child-days denominator gives ~50% regardless of
    window length. 2026-07-05..07-09 is Sun–Thu (5 working days); present on 3 of them.
    """
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 5), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 5), date(2026, 7, 6), date(2026, 7, 7)])  # 3 of 5 working days
    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 7, 31))
    assert rate == 60.0, f"3 attended / 5 expected = 60%, got {rate}"


def test_rate_is_stable_across_window_width(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """The window-scaling regression: the same attendance read over a wider window must
    give the same rate, because the denominator grows with the window too."""
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 5), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 5) + timedelta(days=i) for i in range(5)])  # all 5 working days
    r_small = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 5), date(2026, 7, 9))
    r_large = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 12, 31))
    assert r_small == r_large == 100.0, f"rate scaled with window: {r_small} vs {r_large}"


# ── 3. zero-child and zero-expected windows are explicit ─────────────────────
def test_zero_children_returns_none(test_db, sample_kindergarten):
    """No enrollments -> no expected days -> None ("no data"), not 0.0.

    compute_attendance_rate reserves 0.0 for "days were expected but nobody
    attended"; reporting 0.0 here would show an empty kindergarten as having
    total absenteeism."""
    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 7, 31))
    assert rate is None


def test_zero_expected_days_returns_none(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """A window containing only weekend days has zero expected child-days even with an
    enrolled, present child -> 0.0. 2026-07-10 is Fri, 07-11 is Sat."""
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 10), end=date(2026, 7, 11))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 10), date(2026, 7, 11)])
    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 10), date(2026, 7, 11))
    assert rate is None, f"weekend-only window has no expected days, got {rate}"


def test_reversed_window_is_none(test_db, admin_user, sample_kindergarten, sample_class, sample_child):
    """period_start > period_end has no working days -> None, no crash."""
    _enroll(test_db, sample_kindergarten, sample_child)
    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 31), date(2026, 7, 1))
    assert rate is None


# ── 4. scalar / bulk agree (kg-overview uses bulk) ───────────────────────────
def test_scalar_and_bulk_agree_on_awkward_data(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """kg-overview uses the bulk helper; everything else uses the scalar. They must
    return the same number, including for a partial enrollment, out-of-range and
    weekend attendance, a calendar override, and a LATE row."""
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 6), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 1) + timedelta(days=i) for i in range(5)])   # outside enrollment
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 8)], status=models.AttendanceStatus.LATE)     # LATE, inside
    test_db.add(models.OperatingCalendar(
        kindergarten_id=sample_kindergarten.id, date=date(2026, 7, 7), is_open=False))
    test_db.commit()

    s, e = date(2026, 7, 1), date(2026, 7, 15)
    scalar = KPIService.compute_attendance_rate(test_db, sample_kindergarten.id, s, e)
    bulk = KPIService.compute_attendance_rates_bulk(test_db, [sample_kindergarten.id], s, e)
    assert scalar == bulk[sample_kindergarten.id], f"scalar {scalar} != bulk {bulk}"
    assert scalar <= 100.0


# ── 5. kg-overview and KPI dashboard endpoints agree ─────────────────────────
def _find_attendance_rate(payload):
    """Pull the attendance-rate value out of either endpoint's JSON, wherever it sits."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "attendance_rate":
                    # kg-overview card: {"attendance_rate": n}
                    if isinstance(v, (int, float)):
                        found.append(float(v))
                    # KPI dashboard card: {"attendance_rate": {"value": n, ...}}
                    elif isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
                        found.append(float(v["value"]))
                # KPI list form: {"key": "attendance_rate", "value": n}
                if o.get("key") == "attendance_rate" and k == "value" and isinstance(v, (int, float)):
                    found.append(float(v))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    return found


def test_kg_overview_and_kpi_dashboard_report_the_same_rate(
    client, test_db, admin_user, auth_headers_admin,
    sample_kindergarten, sample_class, sample_child,
):
    """The headline cross-consumer guarantee: the two admin surfaces that show an
    attendance rate for the same kindergarten and window must show the same number."""
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 5), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 5), date(2026, 7, 6), date(2026, 7, 7)])  # 3/5 -> 60%
    params = {"period": "custom", "start_date": "2026-07-01", "end_date": "2026-07-15"}

    kg_resp = client.get("/api/admin/kg-overview", headers=auth_headers_admin, params=params)
    assert kg_resp.status_code == 200, kg_resp.text[:300]
    card = next(c for c in kg_resp.json()["kindergartens"] if c["id"] == sample_kindergarten.id)
    kg_rate = card["attendance_rate"]

    kpi_resp = client.get(
        "/api/kpi/dashboard-data", headers=auth_headers_admin,
        params={"kindergarten_ids": [sample_kindergarten.id],
                "period_start": "2026-07-01", "period_end": "2026-07-15"},
    )
    assert kpi_resp.status_code == 200, kpi_resp.text[:300]
    kpi_rates = _find_attendance_rate(kpi_resp.json())
    assert kpi_rates, f"no attendance_rate found in KPI dashboard payload: {list(kpi_resp.json())}"

    scalar = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 7, 15))

    assert kg_rate == scalar, f"kg-overview {kg_rate} != canonical {scalar}"
    assert any(abs(r - scalar) < 0.01 for r in kpi_rates), (
        f"KPI dashboard rates {kpi_rates} do not include the canonical {scalar}"
    )
    assert kg_rate <= 100.0


# ── 6. no N+1 as kindergarten count grows ────────────────────────────────────
def _count_queries(db, fn):
    counter = {"n": 0}

    def _cb(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _cb)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _cb)
    return counter["n"]


def test_bulk_query_count_is_flat_in_kindergarten_count(
    test_db, admin_user, parent_user, sample_kindergarten, sample_class, sample_child
):
    """The whole reason the bulk helper exists: a per-kg loop would be N+1. The query
    count for 1 kindergarten and for 6 must be the same small constant."""
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 5), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 5) + timedelta(days=i) for i in range(5)])

    extra = []
    for i in range(5):
        kg = models.Kindergarten(
            name_ar=f"روضة {i}", name_en=f"KG {i}", license_number=f"LIC-CANON-{i}",
            governorate="Amman", district="Amman", area="Abdoun",
            address_line="x", contact_phone="+962790000000",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()
        extra.append(kg.id)

    s, e = date(2026, 7, 1), date(2026, 7, 15)
    # Warm up once — the first ORM execution of a mapping can emit a one-off metadata
    # query that would otherwise skew the comparison.
    KPIService.compute_attendance_components_bulk(test_db, [sample_kindergarten.id], s, e)

    n1 = _count_queries(test_db, lambda: KPIService.compute_attendance_components_bulk(
        test_db, [sample_kindergarten.id], s, e))
    n6 = _count_queries(test_db, lambda: KPIService.compute_attendance_components_bulk(
        test_db, [sample_kindergarten.id] + extra, s, e))
    # The point is flatness: going from 1 to 6 kindergartens must not add queries. A
    # per-kg loop would make n6 ≈ n1 + 5.
    assert n6 <= n1, f"query count grew from {n1} (1 kg) to {n6} (6 kgs) — that is an N+1"
    assert n6 <= 4, f"bulk used {n6} queries for 6 kgs; expected a small constant (<=4)"


# ── 7. analytics network / governorate rates share the definition ────────────
def test_network_and_governorate_analytics_agree_with_canonical(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """`_compute_network_attendance_rate` / `_compute_governorate_attendance_rate` were a
    looser calendar-day, all-status formula that disagreed with kg-overview and the KPI
    dashboard. They now route through the canonical helper, so all three agree — on the
    same pathological data (present outside enrollment) that used to diverge."""
    from analytics_service import AnalyticsService

    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 7), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id,
             [date(2026, 7, 1) + timedelta(days=i) for i in range(10)])  # 07-01..07-10
    s, e = date(2026, 7, 1), date(2026, 7, 15)

    canonical = KPIService.compute_attendance_rate(test_db, sample_kindergarten.id, s, e)
    network = AnalyticsService._compute_network_attendance_rate(test_db, s, e, [sample_kindergarten.id])
    governorate = AnalyticsService._compute_governorate_attendance_rate(
        test_db, "Amman", s, e, [sample_kindergarten.id])

    assert network == governorate == canonical, (
        f"network={network} gov={governorate} canonical={canonical} — analytics still "
        "uses a different attendance definition"
    )
    assert canonical <= 100.0
