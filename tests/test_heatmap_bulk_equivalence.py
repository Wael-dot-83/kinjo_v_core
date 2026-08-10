"""The bulk heat-map scorer must agree with the per-kindergarten scorer.

compute_kindergarten_kpi_scores() drives the heat-map colours, so a bulk path
that disagreed would silently repaint the national map. The bulk function
therefore batches only the six counters and then calls the *same* scoring
function with them injected — these tests pin that the two produce identical
output across every band and edge case, and that the query count no longer
scales with kindergarten count.

Before this change the map-data and stats endpoints issued six queries per
kindergarten (~2,700 at 446 active) and took ~17.5s.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import models
from heatmap.backend.service import (
    compute_kindergarten_kpi_scores,
    compute_kindergarten_kpi_scores_bulk,
)

_SEQ = {"n": 0}


def _next():
    _SEQ["n"] += 1
    return _SEQ["n"]


def _kg(db, **kw):
    n = _next()
    defaults = dict(
        name_ar=f"حضانة {n}", name_en=f"KG {n}",
        license_number=f"LIC-HM-{n:04d}",
        governorate="Amman", district="Amman", area="Abdoun",
        address_line="1 St", contact_phone="+96279000000",
        contact_email=f"hm{n}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
        latitude=31.95, longitude=35.91,
    )
    defaults.update(kw)
    kg = models.Kindergarten(**defaults)
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _cls(db, kg):
    n = _next()
    c = models.Class(
        kindergarten_id=kg.id, name_ar=f"صف {n}", name_en=f"Class {n}",
        class_code=f"H{n:04d}", age_group="AGE_1_2",
        capacity_total=20, min_age_months=24, max_age_months=48, is_active=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _assert_same(db, kg, label):
    single = compute_kindergarten_kpi_scores(db, kg)
    bulk = compute_kindergarten_kpi_scores_bulk(db, [kg])[kg.id]
    assert bulk == single, (
        f"{label}: bulk != single\n  bulk  ={bulk}\n  single={single}"
    )
    return single


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


# ── bare kindergarten, no related data ─────────────────────────────────────
def test_bulk_matches_single_for_empty_kindergarten(test_db):
    kg = _kg(test_db)
    _assert_same(test_db, kg, "empty kindergarten")


# ── licence variants drive licence_score 100 / 25 / 50 ─────────────────────
@pytest.mark.parametrize("licence,label", [
    (date(2027, 12, 31), "valid licence"),
    (date(2020, 1, 1), "expired licence"),
    (None, "missing licence"),
])
def test_bulk_matches_single_across_licence_states(test_db, licence, label):
    kg = _kg(test_db, license_valid_until=licence)
    _assert_same(test_db, kg, label)


# ── status variants drive status_score 100 / 60 / 20 ───────────────────────
@pytest.mark.parametrize("status", [
    models.KindergartenStatus.ACTIVE,
    models.KindergartenStatus.DRAFT,
    models.KindergartenStatus.INACTIVE,
])
def test_bulk_matches_single_across_statuses(test_db, status):
    kg = _kg(test_db, status=status)
    _assert_same(test_db, kg, f"status={status.value}")


# ── missing coordinates drive location_score 60 vs 100 ─────────────────────
def test_bulk_matches_single_without_coordinates(test_db):
    kg = _kg(test_db, latitude=None, longitude=None)
    _assert_same(test_db, kg, "no coordinates")


# ── classes/supervisors drive staff_score, classes drive reports_score ─────
def test_bulk_matches_single_with_classes_and_supervisors(test_db, admin_user):
    kg = _kg(test_db)
    _cls(test_db, kg)
    _cls(test_db, kg)
    sup = models.User(
        username=f"hmsup{_next()}", email=f"hmsup{_next()}@t.jo",
        hashed_password="x", role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE, kindergarten_id=kg.id,
    )
    test_db.add(sup)
    test_db.commit()
    _assert_same(test_db, kg, "classes + supervisor")


# ── incidents drive safety_score, including the critical multiplier ────────
def test_bulk_matches_single_with_incidents(test_db, admin_user, sample_child):
    kg = _kg(test_db)
    from utils.time_utils import now_amman
    for sev in (models.SeverityLevel.LOW, models.SeverityLevel.CRITICAL):
        test_db.add(models.Incident(
            kindergarten_id=kg.id, child_id=sample_child.id,
            type=models.IncidentType.INJURY,
            severity_level=sev, status=models.IncidentStatus.OPEN,
            occurred_at=now_amman() - timedelta(days=3),
            description="test", reported_by=admin_user.id,
        ))
    test_db.commit()
    result = _assert_same(test_db, kg, "incidents present")
    # 100 - 2*8 - 1*25 = 59 -> confirms the bulk path fed both counters through
    assert result["indicators"]["safety_incidents"]["score"] == pytest.approx(59.0)


# ── several kindergartens with different data in one bulk call ─────────────
def test_bulk_matches_single_across_mixed_kindergartens(test_db, admin_user):
    a = _kg(test_db)
    _cls(test_db, a)
    b = _kg(test_db, license_valid_until=None, latitude=None, longitude=None)
    c = _kg(test_db, status=models.KindergartenStatus.INACTIVE)

    bulk = compute_kindergarten_kpi_scores_bulk(test_db, [a, b, c])
    assert set(bulk) == {a.id, b.id, c.id}
    for kg, label in ((a, "a"), (b, "b"), (c, "c")):
        assert bulk[kg.id] == compute_kindergarten_kpi_scores(test_db, kg), (
            f"mixed set: {label} differs between bulk and single"
        )
    # distinct inputs must still produce distinct scores
    assert bulk[a.id]["score"] != bulk[b.id]["score"]


# ── the regression that motivated the refactor ─────────────────────────────
def test_bulk_query_count_does_not_scale_with_kindergarten_count(test_db):
    def _fresh(ids):
        """Load the rows the way the endpoints do.

        The heat-map endpoints select their kindergartens with a single .all()
        and score those loaded objects. Re-selecting here reproduces that: without
        it every attribute access would emit a refresh SELECT, because commit()
        expires the instances, and the test would measure SQLAlchemy's expiry
        behaviour rather than the scorer's query count.
        """
        test_db.expire_all()
        return (
            test_db.query(models.Kindergarten)
            .filter(models.Kindergarten.id.in_(ids))
            .all()
        )

    few_ids = [_kg(test_db).id for _ in range(2)]
    few = _fresh(few_ids)
    q_few = _count_queries(
        test_db, lambda: compute_kindergarten_kpi_scores_bulk(test_db, few))

    many_ids = few_ids + [_kg(test_db).id for _ in range(12)]
    many = _fresh(many_ids)
    q_many = _count_queries(
        test_db, lambda: compute_kindergarten_kpi_scores_bulk(test_db, many))

    growth = (q_many - q_few) / (len(many) - len(few))
    assert growth < 0.5, (
        f"{q_few} queries for {len(few)} kindergartens vs {q_many} for "
        f"{len(many)} = {growth:.2f} per kindergarten; the heat-map N+1 is back"
    )


def test_single_path_is_unchanged_when_no_counts_supplied(test_db):
    """The injected-counts parameter must be a pure data-source switch."""
    kg = _kg(test_db)
    _cls(test_db, kg)
    explicit = compute_kindergarten_kpi_scores(test_db, kg, _counts=None)
    implicit = compute_kindergarten_kpi_scores(test_db, kg)
    assert explicit == implicit
