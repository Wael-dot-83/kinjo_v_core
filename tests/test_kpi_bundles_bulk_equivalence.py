"""The bulk KPI bundle must agree with the authoritative per-kindergarten bundle.

`compute_kpi_bundles_bulk` was hoisted out of `get_consolidated_kpi_dashboard_data`
so the network-summary and classification endpoints could stop calling
`compute_kpi_bundle` once per kindergarten. At 446 active kindergartens that loop
issued well over a thousand queries and exceeded the 30s request timeout, which is
the N+1 CLAUDE.md forbids.

Hoisting shared code is only safe if the numbers are provably identical, so these
tests pin the bulk output against the per-kindergarten implementation across
no-data, single, multiple and mixed-data kindergartens — and pin the query count so
the N+1 cannot creep back.

They also pin the one place the two forms legitimately differ: the bundle reports
0.0 for a kindergarten with no scheduled attendance where `compute_attendance_rate`
returns None. Callers must recover the None from `quality.attendance_rate.has_data`;
`get_kpi_network_summary` does, because averaging a 0.0 in instead of dropping it
would drag every network average toward zero.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import models
from kpi_service import KPIService

PERIOD_START = date(2026, 7, 5)
PERIOD_END = date(2026, 7, 9)

# Keys the bulk builder does not emit; they are not consumed by any bulk caller.
PER_KG_ONLY = {"denominators", "numerators", "excused_absence_rate",
               "override_rules_triggered"}


# ── helpers ────────────────────────────────────────────────────────────────
_SEQ = {"n": 0}


def _next():
    _SEQ["n"] += 1
    return _SEQ["n"]


def _kg(db, name):
    n = _next()
    kg = models.Kindergarten(
        name_ar=name, name_en=f"KG {n}",
        license_number=f"LIC-BULK-{n:04d}",
        governorate="Amman", district="Amman", area="Abdoun",
        address_line="1 Test St", contact_phone="+96279000000",
        contact_email=f"kg{n}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _cls(db, kg, name="A"):
    n = _next()
    c = models.Class(
        kindergarten_id=kg.id, name_ar=f"صف {n}", name_en=f"Class {n}",
        class_code=f"C{n:04d}", age_group="AGE_1_2",
        capacity_total=20, min_age_months=24, max_age_months=48,
        is_active=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _child(db, parent_user, first):
    c = models.Child(
        parent_id=parent_user.parent_profile.id,
        first_name=first, last_name="T",
        gender=models.Gender.MALE,
        date_of_birth=date(2022, 1, 1),
        father_name="Ahmad T",
        mother_first_name="Fatima", mother_last_name="Hassan",
        mother_nationality="Jordanian", mother_national_id=f"{_next():010d}",
        media_consent=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _enroll(db, kg, child, start=PERIOD_START, end=PERIOD_END):
    db.add(models.EnrollmentApplication(
        child_id=child.id, kindergarten_id=kg.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=start, enrollment_end_date=end,
    ))
    db.commit()


def _attend(db, cls, child, recorder_id, days, status=None):
    status = status or models.AttendanceStatus.PRESENT
    for d in days:
        db.add(models.AttendanceLog(
            child_id=child.id, class_id=cls.id, date=d,
            status=status, recorded_by=recorder_id,
        ))
    db.commit()


def _assert_bundles_match(bulk, per_kg, kg_label):
    """Every shared key must match; floats compared exactly since both round."""
    shared = (set(bulk) & set(per_kg)) - PER_KG_ONLY
    assert shared, f"{kg_label}: no shared keys to compare"
    mismatched = {}
    for key in sorted(shared):
        if key == "quality":
            continue  # compared separately below
        if bulk[key] != per_kg[key]:
            mismatched[key] = (bulk[key], per_kg[key])
    assert not mismatched, f"{kg_label}: bulk != per-kg for {mismatched}"

    # quality metadata drives null-recovery for callers, so has_data must agree
    for metric, per_item in (per_kg.get("quality") or {}).items():
        bulk_item = (bulk.get("quality") or {}).get(metric)
        if bulk_item is None:
            continue
        assert bulk_item.get("has_data") == per_item.get("has_data"), (
            f"{kg_label}: quality.{metric}.has_data differs "
            f"(bulk={bulk_item.get('has_data')} per_kg={per_item.get('has_data')})"
        )


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


# ── 1. a kindergarten with no data at all ──────────────────────────────────
def test_bulk_matches_per_kg_for_kindergarten_with_no_data(test_db, sample_kindergarten):
    kg_id = sample_kindergarten.id
    bulk = KPIService.compute_kpi_bundles_bulk(
        test_db, [kg_id], PERIOD_START, PERIOD_END)[kg_id]
    per_kg = KPIService.compute_kpi_bundle(test_db, kg_id, PERIOD_START, PERIOD_END)
    _assert_bundles_match(bulk, per_kg, "no-data kg")


def test_no_data_kindergarten_is_unavailable_not_zero(test_db, sample_kindergarten):
    """0 and "no data" are different answers and must stay different.

    The bundle carries 0.0, so the has_data flag is the only thing standing between
    a network average over real reporters and one silently diluted by every
    non-reporting kindergarten.
    """
    kg_id = sample_kindergarten.id
    bulk = KPIService.compute_kpi_bundles_bulk(
        test_db, [kg_id], PERIOD_START, PERIOD_END)[kg_id]

    assert bulk["quality"]["attendance_rate"]["has_data"] is False
    assert KPIService.compute_attendance_rate(
        test_db, kg_id, PERIOD_START, PERIOD_END) is None


# ── 2. a single kindergarten with real data ────────────────────────────────
def test_bulk_matches_per_kg_for_single_kindergarten_with_data(
    test_db, admin_user, parent_user, sample_kindergarten, sample_class
):
    kg_id = sample_kindergarten.id
    child = _child(test_db, parent_user, "Solo")
    _enroll(test_db, sample_kindergarten, child)
    _attend(test_db, sample_class, child, admin_user.id,
            [PERIOD_START + timedelta(days=i) for i in range(3)])

    bulk = KPIService.compute_kpi_bundles_bulk(
        test_db, [kg_id], PERIOD_START, PERIOD_END)[kg_id]
    per_kg = KPIService.compute_kpi_bundle(test_db, kg_id, PERIOD_START, PERIOD_END)
    _assert_bundles_match(bulk, per_kg, "single kg with data")
    assert bulk["quality"]["attendance_rate"]["has_data"] is True


# ── 3. several kindergartens with materially different data ────────────────
def test_bulk_matches_per_kg_across_mixed_kindergartens(
    test_db, admin_user, parent_user, sample_kindergarten, sample_class
):
    """Full attendance, partial attendance, enrolled-but-absent, and empty — in one
    bulk call. A bulk implementation that leaked one kindergarten's rows into
    another would show up here and nowhere else."""
    days = [PERIOD_START + timedelta(days=i) for i in range(5)]

    full = sample_kindergarten
    c_full = _child(test_db, parent_user, "Full")
    _enroll(test_db, full, c_full)
    _attend(test_db, sample_class, c_full, admin_user.id, days)

    partial = _kg(test_db, "جزئي")
    p_cls = _cls(test_db, partial)
    c_part = _child(test_db, parent_user, "Part")
    _enroll(test_db, partial, c_part)
    _attend(test_db, p_cls, c_part, admin_user.id, days[:2])

    absent = _kg(test_db, "غائب")
    _cls(test_db, absent)
    c_abs = _child(test_db, parent_user, "Abs")
    _enroll(test_db, absent, c_abs)

    empty = _kg(test_db, "فارغ")

    kg_ids = [full.id, partial.id, absent.id, empty.id]
    bulk = KPIService.compute_kpi_bundles_bulk(
        test_db, kg_ids, PERIOD_START, PERIOD_END)

    assert set(bulk) == set(kg_ids), "bulk must answer for every requested kindergarten"
    for kg_id, label in zip(kg_ids, ("full", "partial", "absent", "empty")):
        per_kg = KPIService.compute_kpi_bundle(
            test_db, kg_id, PERIOD_START, PERIOD_END)
        _assert_bundles_match(bulk[kg_id], per_kg, label)

    # the distinct inputs must produce distinct attendance answers
    assert bulk[full.id]["attendance_rate"] != bulk[partial.id]["attendance_rate"]


# ── 4. boundary: enrollment outside the period ─────────────────────────────
def test_bulk_matches_per_kg_when_enrollment_is_outside_period(
    test_db, admin_user, parent_user, sample_kindergarten, sample_class
):
    kg_id = sample_kindergarten.id
    child = _child(test_db, parent_user, "Later")
    _enroll(test_db, sample_kindergarten, child,
            start=PERIOD_END + timedelta(days=10),
            end=PERIOD_END + timedelta(days=40))

    bulk = KPIService.compute_kpi_bundles_bulk(
        test_db, [kg_id], PERIOD_START, PERIOD_END)[kg_id]
    per_kg = KPIService.compute_kpi_bundle(test_db, kg_id, PERIOD_START, PERIOD_END)
    _assert_bundles_match(bulk, per_kg, "enrollment outside period")


# ── 5. the regression that motivated the refactor ──────────────────────────
def test_bulk_query_count_does_not_scale_with_kindergarten_count(
    test_db, admin_user, parent_user, sample_kindergarten, sample_class
):
    """One kindergarten and twelve must cost the same order of queries.

    This is the guard against the N+1 returning: the old network-summary path grew
    ~18 queries per kindergarten, so 446 of them blew the request timeout.
    """
    child = _child(test_db, parent_user, "Q")
    _enroll(test_db, sample_kindergarten, child)
    _attend(test_db, sample_class, child, admin_user.id,
            [PERIOD_START + timedelta(days=i) for i in range(3)])

    one = _count_queries(test_db, lambda: KPIService.compute_kpi_bundles_bulk(
        test_db, [sample_kindergarten.id], PERIOD_START, PERIOD_END))

    many_ids = [sample_kindergarten.id]
    for i in range(11):
        kg = _kg(test_db, f"حضانة {i}")
        _cls(test_db, kg)
        many_ids.append(kg.id)

    many = _count_queries(test_db, lambda: KPIService.compute_kpi_bundles_bulk(
        test_db, many_ids, PERIOD_START, PERIOD_END))

    assert many <= one + 5, (
        f"query count scales with kindergarten count: {one} for 1 vs {many} for "
        f"{len(many_ids)} — the N+1 has returned"
    )
