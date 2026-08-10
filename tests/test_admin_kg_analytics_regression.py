"""Regressions for the two Admin analytics endpoints that failed in production.

GET /api/admin/analytics/kg/{id} returned 500 with
    ValueError: dictionary update sequence element #0 has length 3; 2 is required
because analytics_gap_service built `att_by_child` with dict() over a query that
selects three columns. dict() only consumes 2-tuples, so the endpoint failed for
every kindergarten that actually had attendance rows. With no attendance the
query returns [] and dict([]) succeeds, which is exactly why the whole suite
stayed green while production was broken — so the test below seeds attendance.

GET /api/analytics/kg-overview/kindergartens returned 504 because it called
get_kindergarten_metrics() once per kindergarten.
"""
from datetime import date, timedelta

from sqlalchemy import event

import models
from analytics_service import AnalyticsService

_SEQ = {"n": 0}


def _next():
    _SEQ["n"] += 1
    return _SEQ["n"]


def _kg(db):
    n = _next()
    kg = models.Kindergarten(
        name_ar=f"حضانة {n}", name_en=f"KG {n}",
        license_number=f"LIC-GA-{n:04d}",
        governorate="Amman", district="Amman", area="Abdoun",
        address_line="1 St", contact_phone="+96279000000",
        contact_email=f"ga{n}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _cls(db, kg):
    n = _next()
    c = models.Class(
        kindergarten_id=kg.id, name_ar=f"صف {n}", name_en=f"Class {n}",
        class_code=f"G{n:04d}", age_group="AGE_1_2",
        capacity_total=20, min_age_months=24, max_age_months=48, is_active=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


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


# ── the 500 ────────────────────────────────────────────────────────────────
def test_kg_metrics_with_attendance_rows_does_not_raise(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """Seeds attendance so the three-column query returns rows.

    Without attendance the offending dict() call receives an empty sequence and
    silently succeeds; this test only fails when rows exist, which is the state
    production was in.
    """
    today = date.today()
    test_db.add(models.EnrollmentApplication(
        child_id=sample_child.id, kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=today - timedelta(days=30),
        enrollment_end_date=today + timedelta(days=30),
    ))
    for i in range(3):
        test_db.add(models.AttendanceLog(
            child_id=sample_child.id, class_id=sample_class.id,
            date=today - timedelta(days=i),
            status=models.AttendanceStatus.PRESENT, recorded_by=admin_user.id,
        ))
    test_db.commit()

    from analytics_gap_service import AnalyticsGapService
    resp = AnalyticsGapService(test_db).get_kg_metrics(
        sample_kindergarten.id, locale="ar"
    )
    assert resp is not None
    metrics = getattr(resp, "metrics", None) or []
    names = {getattr(m, "metric", None) for m in metrics}
    assert "child_risk_composite" in names, (
        "child_risk_composite missing — the attendance branch did not run"
    )


# ── the 504 ────────────────────────────────────────────────────────────────
def test_overview_bulk_matches_single_kindergarten_metrics(
    test_db, admin_user, sample_kindergarten, sample_class, sample_child
):
    """Bulk overview metrics must equal what the per-KG path reported."""
    today = date.today()
    period_start, period_end = today - timedelta(days=29), today
    test_db.add(models.EnrollmentApplication(
        child_id=sample_child.id, kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=period_start, enrollment_end_date=period_end,
    ))
    test_db.commit()

    bulk = AnalyticsService.get_kg_overview_metrics_bulk(
        test_db, [sample_kindergarten.id], period_start, period_end
    )[sample_kindergarten.id]
    single = AnalyticsService.get_kindergarten_metrics(
        test_db, sample_kindergarten.id, period_start, period_end
    )

    assert bulk["capacity"] == (single.capacity or 0)
    assert bulk["children_count"] == (single.children_count or 0)
    # the endpoint coerces a missing rate with `or 0`; compare the same way
    assert (bulk["attendance_rate"] or 0) == (single.attendance_rate or 0)


def test_overview_bulk_handles_kindergarten_with_no_data(test_db):
    kg = _kg(test_db)
    out = AnalyticsService.get_kg_overview_metrics_bulk(
        test_db, [kg.id], date.today() - timedelta(days=29), date.today()
    )
    assert out[kg.id]["capacity"] == 0
    assert out[kg.id]["children_count"] == 0
    # no scheduled attendance is "unavailable", not a genuine zero
    assert out[kg.id]["attendance_rate"] is None


def test_overview_bulk_query_count_is_flat(test_db):
    period_start, period_end = date.today() - timedelta(days=29), date.today()

    few = [_kg(test_db).id for _ in range(3)]
    q_few = _count_queries(test_db, lambda: AnalyticsService.get_kg_overview_metrics_bulk(
        test_db, few, period_start, period_end))

    many = few + [_kg(test_db).id for _ in range(12)]
    q_many = _count_queries(test_db, lambda: AnalyticsService.get_kg_overview_metrics_bulk(
        test_db, many, period_start, period_end))

    growth = (q_many - q_few) / (len(many) - len(few))
    assert growth < 0.5, (
        f"{q_few} queries for {len(few)} vs {q_many} for {len(many)} = "
        f"{growth:.2f} per kindergarten; kg-overview is still N+1"
    )


# ── not-found handling ─────────────────────────────────────────────────────
def test_kg_analytics_returns_404_for_unknown_kindergarten(client, admin_token):
    """A missing kindergarten must 404, not return zeroed metrics.

    The calculators aggregate happily over an empty result set, so without an
    existence check the endpoint answered 200 with a full chart structure of
    zeros — indistinguishable from a real kindergarten with no data.
    """
    r = client.get(
        "/api/admin/analytics/kg/999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404, (
        f"expected 404 for a nonexistent kindergarten, got {r.status_code}"
    )


def test_kg_analytics_returns_200_for_existing_kindergarten(
    client, admin_token, sample_kindergarten
):
    r = client.get(
        f"/api/admin/analytics/kg/{sample_kindergarten.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200


def test_kg_analytics_requires_admin(client, manager_token, sample_kindergarten):
    r = client.get(
        f"/api/admin/analytics/kg/{sample_kindergarten.id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r.status_code == 403


def test_kg_analytics_requires_authentication(client, sample_kindergarten):
    r = client.get(f"/api/admin/analytics/kg/{sample_kindergarten.id}")
    assert r.status_code == 401


# ── predictive metrics: nested N+1 removed ─────────────────────────────────
def test_predictive_metrics_runs_and_is_not_nested_n_plus_1(
    test_db, admin_user, parent_user, sample_kindergarten, sample_class, sample_child
):
    """get_predictive_metrics looped 446 kindergartens x 12 weeks, twice.

    That is ~11,000 queries at production scale and returned 504. The weekly
    buckets are now grouped; this pins both that the endpoint still produces its
    metrics and that query count no longer grows per kindergarten.
    """
    from analytics_gap_service import AnalyticsGapService

    today = date.today()
    test_db.add(models.EnrollmentApplication(
        child_id=sample_child.id, kindergarten_id=sample_kindergarten.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=today - timedelta(days=60),
        enrollment_end_date=today + timedelta(days=60),
    ))
    for i in range(10):
        test_db.add(models.AttendanceLog(
            child_id=sample_child.id, class_id=sample_class.id,
            date=today - timedelta(days=i * 3),
            status=models.AttendanceStatus.PRESENT, recorded_by=admin_user.id,
        ))
    test_db.commit()

    svc = AnalyticsGapService(test_db)
    q_one = _count_queries(test_db, lambda: svc.get_predictive_metrics(locale="ar"))
    resp = svc.get_predictive_metrics(locale="ar")
    names = {getattr(m, "metric", None) for m in (getattr(resp, "metrics", None) or [])}
    assert "dropout_risk" in names or names, "predictive metrics produced nothing"

    for _ in range(10):
        _kg(test_db)
    q_many = _count_queries(test_db, lambda: svc.get_predictive_metrics(locale="ar"))

    growth = (q_many - q_one) / 10
    assert growth < 1.0, (
        f"{q_one} queries for 1 kindergarten vs {q_many} for 11 = {growth:.2f} "
        "per kindergarten; the predictive nested N+1 is back"
    )
