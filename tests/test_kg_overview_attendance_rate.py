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

**What is still wrong — read this before trusting the number.** The rate can still
exceed 100%. `_attended_child_days_by_child` (kpi_service.py) filters only on child_id
and the window, while the denominator additionally respects working days and each
enrolment's effective range. The numerator therefore counts days the denominator never
expected. Reproduced (see `test_rate_can_still_exceed_100_percent` below):

    enrolled 07-07..07-09, attendance logged 07-01..07-10, window 07-01..07-15 -> 333.33%
    PRESENT every calendar day including Fri/Sat, window 07-01..07-15         -> 136.36%

This is **pre-existing and shared**: identical on the merge base and reached by ~9
analytics_service.py call sites plus the KPI dashboard, all through the same
compute_attendance_rate. So this branch makes kg-overview *agree* with the rest of the
system — which was the point — and removes the window-scaling. It does not make the
shared definition sound. Fixing that means constraining the numerator to the same
day-set as the denominator inside kpi_service, which changes KPI values system-wide and
needs its own branch and verification.

An earlier version of this file asserted "a rate cannot exceed 100%" and passed only
because its seed happened to avoid both cases. The bound tests below now assert exact
values instead, so gutting the implementation cannot satisfy them.
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


def test_rate_can_still_exceed_100_percent(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """Pins a KNOWN, UNFIXED defect so it stays visible and cannot be re-discovered.

    The numerator counts every attendance row for the child in the window; the
    denominator counts only working days inside the enrolment's effective range. Days
    outside the enrolment (or on Fri/Sat) inflate the numerator against a denominator
    that never expected them.

    Pre-existing and shared with the KPI dashboard and ~9 analytics_service call sites.
    **If this test starts failing, the shared definition was fixed** — delete this test
    and tighten the bound in the two above to `<= 100.0`.
    """
    _enroll(test_db, sample_kindergarten, sample_child,
            start=date(2026, 7, 7), end=date(2026, 7, 9))
    _present(test_db, sample_class, sample_child, admin_user.id, 10, date(2026, 7, 1))

    rate = KPIService.compute_attendance_rate(
        test_db, sample_kindergarten.id, date(2026, 7, 1), date(2026, 7, 15)
    )
    assert rate > 100.0, (
        f"compute_attendance_rate now returns {rate}% for attendance logged outside the "
        "enrolment range. If that is because the numerator was constrained to the "
        "denominator's day-set, this defect is fixed: remove this test and tighten the "
        "bounds above."
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
