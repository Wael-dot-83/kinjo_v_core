"""kg-overview's attendance rate: what it now is, and what is still wrong with it.

**What was fixed.** The endpoint computed `present_rows / active_children * 100` inline:
a count of PRESENT rows *across the whole window* divided by a *single-day* headcount.
Different dimensions, so the answer scaled with the window. Measured before the fix,
one child, one active enrolment, five PRESENT days:

    1-day window -> 100.0%    10-day -> 500.0%    365-day -> 500.0%    all 'on_target'

The wider the range an admin picked, the better a struggling kindergarten looked. The
same shape appeared three times — the card, the network avg_attendance KPI, and the
governorate chart. All three now route through KPIService, which defines attendance as
(PRESENT + LATE child-days) / expected child-days, with expected respecting working days
(Sun–Thu plus OperatingCalendar) and each enrolment's own date range.

**The numerator is now constrained to the expected day-set.** The earlier fix removed
the window-scaling but left a deeper asymmetry: `_attended_child_days_by_child` counted
every PRESENT/LATE log in the window, while the denominator counted only working days
within each enrolment. A child present outside their enrolment, or on a closed day,
pushed the rate past 100% (measured at 333% and 136%).

The canonical `KPIService._attendance_components_by_child` now takes numerator and
denominator over the SAME per-child day-set (working days ∩ enrolment range), so
attended ⊆ expected and the rate is bounded to [0, 100]. Every attendance-rate consumer
— kg-overview (card, network KPI, governorate chart), the KPI dashboard, and the
analytics call sites — routes through it, so they agree by construction. Incident rates
deliberately keep counting ALL physical-attendance days as exposure (an incident can
happen on any day a child is present); that split is documented in kpi_service.py.

The bound tests below assert exact values, so a gutted numerator returning 0 cannot
satisfy them.
"""
from datetime import date, timedelta

import models
from kpi_service import KPIService


def _enroll(test_db, kg, child, start=None, end=None):
    test_db.add(models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=start,
        enrollment_end_date=end,
    ))
    test_db.commit()


def _present(test_db, cls, child, admin_id, days, start):
    for i in range(days):
        test_db.add(models.AttendanceLog(
            child_id=child.id, class_id=cls.id, date=start + timedelta(days=i),
            status=models.AttendanceStatus.PRESENT, recorded_by=admin_id,
        ))
    test_db.commit()


def test_rate_does_not_scale_with_the_window(
    client, admin_token, admin_user, test_db, sample_kindergarten, sample_class, sample_child
):
    """The regression this file exists for: the same attendance, read over a wider
    window, used to report a bigger number (100% -> 500%).

    Attendance sits inside the enrolment and on working days, so the asymmetry noted in
    the module docstring is not in play and the rate is exactly checkable.
    2026-07-05 is a Sunday: five consecutive school days, Sun–Thu.
    """
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 5), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 5))
    hdr = {"Authorization": f"Bearer {admin_token}"}

    rates = {}
    for label, params in [
        ("1-day", "period=custom&start_date=2026-07-06&end_date=2026-07-06"),
        ("10-day", "period=custom&start_date=2026-07-01&end_date=2026-07-10"),
        ("365-day", "period=custom&start_date=2025-07-11&end_date=2026-07-10"),
    ]:
        client.cookies.clear()
        r = client.get(f"/api/admin/kg-overview?{params}", headers=hdr)
        assert r.status_code == 200, f"{label}: HTTP {r.status_code} {r.text[:200]}"
        card = next(c for c in r.json()["kindergartens"] if c["id"] == sample_kindergarten.id)
        rates[label] = card["attendance_rate"]

    # Enrolled for exactly the 5 school days it attended, so every window that contains
    # the enrolment sees 5 attended / 5 expected. Exact values, not a range: a gutted
    # implementation returning 0.0 must fail.
    assert rates["10-day"] == 100.0, f"expected 100.0 over the 10-day window, got {rates}"
    assert rates["365-day"] == 100.0, f"expected 100.0 over the 365-day window, got {rates}"
    assert rates["365-day"] == rates["10-day"], (
        f"the rate changed with window width — the old present_rows/headcount bug is "
        f"back: {rates}"
    )


def test_network_and_governorate_rates_match_the_card(
    client, admin_token, admin_user, test_db, sample_kindergarten, sample_class, sample_child
):
    """The bad formula also fed executive_health's avg_attendance KPI and the
    per-governorate chart; a fix to the card alone would leave both wrong. With one
    kindergarten, all three must report the same number."""
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 5), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 5))
    client.cookies.clear()
    r = client.get(
        "/api/admin/kg-overview?period=custom&start_date=2026-07-01&end_date=2026-07-10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()

    card = next(c for c in body["kindergartens"] if c["id"] == sample_kindergarten.id)
    kpi = next(c for c in body["kpis"] if c["title_en"] == "Attendance Rate")
    gov = body["charts"]["governorate_comparison"][0]

    assert card["attendance_rate"] == 100.0, f"card={card['attendance_rate']}"
    assert kpi["value"] == 100.0, f"network KPI={kpi['value']} but card={card['attendance_rate']}"
    assert gov["attendance_rate"] == 100.0, f"governorate={gov['attendance_rate']}"


def test_attendance_outside_the_enrollment_range_does_not_exceed_100(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """The 333% regression, now fixed and pinned the other way.

    Enrolled for three days (07-07..07-09) but present across ten (07-01..07-10). The
    seven present days outside the enrollment used to be counted in the numerator
    against a denominator that only expected the three — 333%. The canonical helper
    (`_attendance_components_by_child`) now counts attendance only on expected days
    (working days ∩ enrollment range), so the numerator is a subset of the denominator
    and the rate cannot exceed 100%.

    The child was present on 07-07/08/09 (the three expected days), so the rate is
    exactly 100 — an exact value, not just a bound, so a gutted numerator returning 0
    cannot satisfy it.
    """
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 7), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id, 10, date(2026, 7, 1))

    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 7, 15)
    )
    # 07-07 (Tue), 07-08 (Wed), 07-09 (Thu) are all Sun–Thu working days, all attended.
    assert rate == 100.0, (
        f"expected 100.0 (present on all three expected days), got {rate}. A value over "
        "100 means the numerator is again counting days the denominator did not expect."
    )


def test_attendance_on_closed_days_does_not_exceed_100(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """The other half of the 333% class: present every calendar day, including Fri/Sat.

    With no OperatingCalendar rows, Fri/Sat are closed and not expected. Logging
    attendance on them used to inflate the numerator (136% before the fix). Enrolled and
    present for the full window, so every expected (Sun–Thu) day is attended -> 100.
    """
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 1), end=date(2026, 7, 15))
    _present(test_db, sample_class, sample_child, admin_user.id, 15, date(2026, 7, 1))

    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 7, 15)
    )
    assert rate == 100.0, (
        f"expected 100.0 (present on every working day), got {rate}. A value over 100 "
        "means attendance on closed (Fri/Sat) days is being counted."
    )


def test_bulk_matches_per_kg_including_the_awkward_cases(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """The bulk helper exists only to avoid an N+1; it must not become a second
    definition. If these disagree, kg-overview and the KPI dashboard report different
    attendance for the same kindergarten and period.

    Deliberately exercises the cases a trivial seed would miss: a partial enrolment
    range, attendance outside it, an OperatingCalendar override closing a working day,
    and a LATE row (which counts as physical attendance).
    """
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 6), end=date(2026, 7, 9))
    # PRESENT 07-01..07-05 — entirely OUTSIDE the enrolment, which is the asymmetry.
    # (attendance_logs is unique on (child_id, date), so these must not overlap.)
    _present(test_db, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 1))
    # LATE 07-08 — inside the enrolment; counts as physical attendance.
    test_db.add(models.AttendanceLog(
        child_id=sample_child.id, class_id=sample_class.id, date=date(2026, 7, 8),
        status=models.AttendanceStatus.LATE, recorded_by=admin_user.id,
    ))
    test_db.add(models.OperatingCalendar(
        kindergarten_id=sample_kindergarten.id, date=date(2026, 7, 7), is_open=False,
    ))
    test_db.commit()

    start, end = date(2026, 7, 1), date(2026, 7, 15)
    scalar = KPIService.compute_attendance_rate(test_db, sample_kindergarten.id, start, end)
    bulk = KPIService.compute_attendance_rates_bulk(test_db, [sample_kindergarten.id], start, end)
    assert bulk[sample_kindergarten.id] == scalar, (
        f"bulk={bulk[sample_kindergarten.id]} vs compute_attendance_rate={scalar} — the "
        "bulk path has drifted from the authoritative definition"
    )


def test_bulk_is_not_an_n_plus_one(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """The reason the bulk helper exists. compute_attendance_rate costs 4 queries per
    kindergarten; calling it per card is the N+1 CLAUDE.md forbids. The bulk form must
    stay flat as kindergartens are added."""
    from sqlalchemy import event

    _enroll(test_db, sample_kindergarten, sample_child)
    _present(test_db, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 5))

    extra_ids = []
    for i in range(4):
        kg = models.Kindergarten(
            name_ar=f"روضة {i}", name_en=f"KG {i}", license_number=f"LIC-BULK-{i}",
            governorate="Amman", district="Amman", area="Abdoun",
            address_line="x", contact_phone="+962790000000",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()
        extra_ids.append(kg.id)

    counter = {"n": 0}

    def _count(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    engine = test_db.get_bind()
    event.listen(engine, "before_cursor_execute", _count)
    try:
        counter["n"] = 0
        KPIService.compute_attendance_rates_bulk(
            test_db, [sample_kindergarten.id] + extra_ids, date(2026, 7, 1), date(2026, 7, 10)
        )
        n_for_5 = counter["n"]
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert n_for_5 <= 4, (
        f"bulk attendance took {n_for_5} queries for 5 kindergartens — it is supposed to "
        "be a fixed handful regardless of count, otherwise it is the N+1 it replaced"
    )
