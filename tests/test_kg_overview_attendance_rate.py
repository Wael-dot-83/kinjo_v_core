"""kg-overview's attendance rate must be a real rate, and the same one the KPI engine reports.

The endpoint computed `present_rows / active_children * 100` inline: a count of PRESENT
rows *across the whole window* divided by a *single-day* headcount. The two have
different dimensions, so the answer scaled with the window. Measured before the fix,
with one child, one active enrolment and five PRESENT days:

    1-day   window -> 100.0%   'on_target'
    10-day  window -> 500.0%   'on_target'
    365-day window -> 500.0%   'on_target'

500% is not a rate, and every band still read 'on_target' because 500 >= the target.
The same shape appeared three times in this endpoint — the per-kindergarten card, the
network `avg_attendance`, and the per-governorate chart — so all three are pinned here.

The fix routes all three through KPIService, which already defines attendance as
(PRESENT + LATE child-days) / expected child-days, where expected respects working days
(Sun–Thu plus OperatingCalendar) and each enrolment's own date range. Duplicating that
inline is what let this number drift from the KPI dashboard in the first place
(CLAUDE.md: KPI computations belong in kpi_service.py).
"""
from datetime import date, timedelta

import models
from kpi_service import KPIService


def _seed(test_db, kg, cls, child, admin_id, present_days, start):
    test_db.add(models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        status=models.EnrollmentStatus.ACTIVE,
    ))
    test_db.commit()
    for i in range(present_days):
        test_db.add(models.AttendanceLog(
            child_id=child.id,
            class_id=cls.id,
            date=start + timedelta(days=i),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=admin_id,
        ))
    test_db.commit()


def test_rate_is_bounded_and_does_not_scale_with_the_window(
    client, admin_token, admin_user, test_db, sample_kindergarten, sample_class, sample_child
):
    """The regression: a wider window inflated the same attendance into a bigger number."""
    # 2026-07-05 is a Sunday: five consecutive school days, Sun–Thu.
    _seed(test_db, sample_kindergarten, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 5))
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

    for label, rate in rates.items():
        assert 0.0 <= rate <= 100.0, (
            f"{label} window reported attendance_rate={rate}% — a rate cannot exceed "
            f"100%. All windows: {rates}"
        )


def test_network_and_governorate_rates_are_bounded(
    client, admin_token, admin_user, test_db, sample_kindergarten, sample_class, sample_child
):
    """The same bad formula also fed executive_health.avg_attendance and the
    per-governorate chart; a fix to the card alone would leave both wrong."""
    _seed(test_db, sample_kindergarten, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 5))
    client.cookies.clear()
    r = client.get(
        "/api/admin/kg-overview?period=custom&start_date=2026-07-01&end_date=2026-07-10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()

    # The network average is surfaced as the "Attendance Rate" KPI card.
    cards = [c for c in body["kpis"] if c["title_en"] == "Attendance Rate"]
    assert cards, f"no Attendance Rate KPI card; titles={[c['title_en'] for c in body['kpis']]}"
    avg = cards[0]["value"]
    assert 0.0 <= avg <= 100.0, f"network Attendance Rate KPI card reported {avg}% — exceeds 100%"

    gov_rows = body["charts"]["governorate_comparison"]
    assert gov_rows, f"no governorate rows to check; charts keys={list(body['charts'])}"
    for row in gov_rows:
        assert 0.0 <= row["attendance_rate"] <= 100.0, (
            f"governorate {row['name']} reported attendance_rate="
            f"{row['attendance_rate']}% — exceeds 100%"
        )


def test_bulk_attendance_rate_matches_per_kg(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """The bulk helper exists only to avoid an N+1; it must not become a second
    definition. If these two ever disagree, kg-overview and the KPI dashboard are
    reporting different attendance for the same kindergarten and period."""
    _seed(test_db, sample_kindergarten, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 5))
    start, end = date(2026, 7, 1), date(2026, 7, 10)

    scalar = KPIService.compute_attendance_rate(test_db, sample_kindergarten.id, start, end)
    bulk = KPIService.compute_attendance_rates_bulk(test_db, [sample_kindergarten.id], start, end)

    assert bulk[sample_kindergarten.id] == scalar, (
        f"bulk={bulk[sample_kindergarten.id]} but compute_attendance_rate={scalar} — "
        "the bulk path has drifted from the authoritative definition"
    )
    assert 0.0 <= scalar <= 100.0, f"even the authoritative rate is out of range: {scalar}"


def test_bulk_is_not_an_n_plus_one(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """The reason the bulk helper exists. compute_attendance_rate costs 4 queries per
    kindergarten; a listing endpoint calling it in a loop is the N+1 CLAUDE.md forbids.
    The bulk form must stay flat as kindergartens are added."""
    from sqlalchemy import event

    _seed(test_db, sample_kindergarten, sample_class, sample_child, admin_user.id, 5, date(2026, 7, 5))

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
        f"bulk attendance took {n_for_5} queries for 5 kindergartens — it is supposed "
        "to be a fixed handful regardless of count, otherwise it is the N+1 it replaced"
    )
