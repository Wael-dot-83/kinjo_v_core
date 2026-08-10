"""The network-summary and classification endpoints must not be N+1.

Both used to call a per-kindergarten KPI routine inside a loop. At 446 active
kindergartens that exceeded the 30s request timeout and returned 504, taking
/admin/kpi and /admin/classification down with it. These tests pin the query
count flat in the number of kindergartens so the regression cannot return
silently the next time the network grows.
"""
from datetime import date, timedelta

from sqlalchemy import event

import models
from classification_service import BenchmarkingService
from kpi_service import KPIService

PERIOD_START = date(2026, 7, 5)
PERIOD_END = date(2026, 7, 9)

_SEQ = {"n": 0}


def _next():
    _SEQ["n"] += 1
    return _SEQ["n"]


def _kg(db, name="حضانة"):
    n = _next()
    kg = models.Kindergarten(
        name_ar=f"{name} {n}", name_en=f"KG {n}",
        license_number=f"LIC-SCALE-{n:04d}",
        governorate="Amman", district="Amman", area="Abdoun",
        address_line="1 Test St", contact_phone="+96279000000",
        contact_email=f"scale{n}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


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


def test_network_bundles_query_count_is_flat(test_db, sample_kindergarten):
    """3 kindergartens and 15 must cost about the same number of queries."""
    few = [sample_kindergarten.id] + [_kg(test_db).id for _ in range(2)]
    q_few = _count_queries(test_db, lambda: KPIService.compute_kpi_bundles_bulk(
        test_db, few, PERIOD_START, PERIOD_END))

    many = few + [_kg(test_db).id for _ in range(12)]
    q_many = _count_queries(test_db, lambda: KPIService.compute_kpi_bundles_bulk(
        test_db, many, PERIOD_START, PERIOD_END))

    growth_per_kg = (q_many - q_few) / (len(many) - len(few))
    assert growth_per_kg < 0.5, (
        f"{q_few} queries for {len(few)} kindergartens vs {q_many} for {len(many)} "
        f"= {growth_per_kg:.2f} extra queries per kindergarten; this is an N+1"
    )


def test_classification_bundles_bulk_query_count_is_flat(test_db, sample_kindergarten):
    """The leaderboard fetches two periods; both must stay flat in KG count."""
    few = [sample_kindergarten.id] + [_kg(test_db).id for _ in range(2)]
    q_few = _count_queries(test_db, lambda: BenchmarkingService._bundles_bulk(
        test_db, few, PERIOD_START, PERIOD_END))

    many = few + [_kg(test_db).id for _ in range(12)]
    # a different period so the cache warmed above cannot mask the query cost
    q_many = _count_queries(test_db, lambda: BenchmarkingService._bundles_bulk(
        test_db, many, PERIOD_START - timedelta(days=60), PERIOD_END - timedelta(days=60)))

    growth_per_kg = (q_many - q_few) / (len(many) - len(few))
    assert growth_per_kg < 0.5, (
        f"{q_few} queries for {len(few)} vs {q_many} for {len(many)} "
        f"= {growth_per_kg:.2f} per kindergarten; classification is still N+1"
    )


def test_classification_bulk_matches_single_bundle(test_db, sample_kindergarten):
    """_bundles_bulk must be interchangeable with _bundle, including the
    enrichment keys the leaderboard ranks on."""
    kg_id = sample_kindergarten.id
    single = BenchmarkingService._bundle(test_db, kg_id, PERIOD_START, PERIOD_END)
    # different period so the shared cache cannot make this pass trivially
    p2s, p2e = PERIOD_START - timedelta(days=30), PERIOD_END - timedelta(days=30)
    single2 = BenchmarkingService._bundle(test_db, kg_id, p2s, p2e)
    bulk2 = BenchmarkingService._bundles_bulk(test_db, [kg_id], p2s, p2e)[kg_id]

    for key in ("expected_child_days", "coverage_pct_total", "governance_score",
                "gqi_score", "cei_score"):
        assert bulk2[key] == single2[key], (
            f"{key}: bulk={bulk2[key]} single={single2[key]}"
        )
    assert isinstance(single, dict)
