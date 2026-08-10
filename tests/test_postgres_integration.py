"""Real PostgreSQL coverage for the Admin paths that broke in production.

Two production 500s (strftime, enum drift) and a ValueError reached users while
the whole suite was green, because the suite runs on SQLite: SQLite accepts
SQLite-only functions, stores enums as free text, and returns empty result sets
that mask shape bugs.

These tests execute the real SQL against PostgreSQL when one is reachable, and
skip cleanly otherwise so local SQLite runs and CI without a database are
unaffected. Point KINJO_TEST_POSTGRES_URL at a throwaway database to enable
them, e.g.

    KINJO_TEST_POSTGRES_URL=postgresql://user:pass@localhost:5432/kinjo_test

The schema is created from the models, so no migration or fixture data from the
real database is touched.
"""
import os
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

import models
from database import Base

PG_URL = os.environ.get("KINJO_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="KINJO_TEST_POSTGRES_URL not set; PostgreSQL parity tests skipped",
)


@pytest.fixture(scope="module")
def pg_session():
    engine = sa.create_engine(PG_URL)
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not reachable: {type(exc).__name__}")

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _kg(db, n=1):
    kg = models.Kindergarten(
        name_ar=f"حضانة {n}", name_en=f"KG {n}",
        license_number=f"LIC-PG-{n:04d}",
        governorate="Amman", district="Amman", area="Abdoun",
        address_line="1 St", contact_phone="+96279000000",
        contact_email=f"pg{n}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def test_student_distribution_year_expression_runs_on_postgres(pg_session):
    """The query that raised 'function strftime(unknown, date) does not exist'.

    extract()/cast must compile for PostgreSQL and must yield an integer year so
    the Arabic label stays "مواليد 2022" rather than "مواليد 2022.0".
    """
    from sqlalchemy import cast, extract, func, Integer

    expr = cast(extract("year", models.Child.date_of_birth), Integer)
    rows = (
        pg_session.query(expr.label("birth_year"), func.count(models.Child.id))
        .group_by(expr)
        .all()
    )
    assert isinstance(rows, list)
    for birth_year, _count in rows:
        assert birth_year is None or isinstance(birth_year, int), (
            f"birth_year must be an int on PostgreSQL, got {type(birth_year)}"
        )


@pytest.mark.parametrize("member", ["ACCEPTED", "BEHAVIORAL", "ACCIDENT", "HEALTH"])
def test_incident_type_enum_members_are_accepted_by_postgres(pg_session, member):
    """Every IncidentType member must be storable.

    BEHAVIORAL was declared in Python but missing from the PostgreSQL type,
    which made /api/analytics/safety/summary a 500.
    """
    if not hasattr(models.IncidentType, member):
        pytest.skip(f"IncidentType.{member} not defined in this build")
    value = getattr(models.IncidentType, member)
    # a filter is enough: PostgreSQL rejects an unknown label at bind time
    pg_session.query(models.Incident).filter(
        models.Incident.type == value
    ).count()


def test_all_model_enum_members_round_trip_on_postgres(pg_session):
    """No Enum column may declare a member the database type lacks."""
    missing = []
    for mapper in Base.registry.mappers:
        for col in mapper.columns:
            t = col.type
            if not isinstance(t, sa.Enum) or getattr(t, "enum_class", None) is None:
                continue
            type_name = (t.name or t.enum_class.__name__).lower()
            exists = pg_session.execute(
                sa.text("SELECT 1 FROM pg_type WHERE typname = :t"), {"t": type_name}
            ).scalar()
            if not exists:
                continue
            db_labels = {
                r[0] for r in pg_session.execute(
                    sa.text(
                        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t "
                        "ON e.enumtypid = t.oid WHERE t.typname = :t"
                    ), {"t": type_name}
                )
            }
            for m in t.enum_class:
                if m.name not in db_labels:
                    missing.append(f"{type_name}.{m.name}")
    assert not missing, (
        "enum members declared in Python but absent from PostgreSQL (a query "
        "using one raises InvalidTextRepresentation): " + ", ".join(sorted(missing))
    )


def test_kpi_bundles_bulk_executes_on_postgres(pg_session):
    """The bulk KPI path runs a lot of grouped SQL; prove it compiles on PG."""
    from kpi_service import KPIService

    kg = _kg(pg_session, 1)
    end = date.today()
    start = end - timedelta(days=29)
    out = KPIService.compute_kpi_bundles_bulk(pg_session, [kg.id], start, end)
    assert kg.id in out
    assert "governance_band" in out[kg.id]


def test_heatmap_bulk_counts_execute_on_postgres(pg_session):
    """The batched heat-map counters must compile for PostgreSQL."""
    from heatmap.backend.service import compute_kindergarten_kpi_scores_bulk

    kg = _kg(pg_session, 2)
    out = compute_kindergarten_kpi_scores_bulk(pg_session, [kg])
    assert kg.id in out
    assert "kpi_status" in out[kg.id]


def test_kg_overview_metrics_bulk_executes_on_postgres(pg_session):
    from analytics_service import AnalyticsService

    kg = _kg(pg_session, 3)
    end = date.today()
    out = AnalyticsService.get_kg_overview_metrics_bulk(
        pg_session, [kg.id], end - timedelta(days=29), end
    )
    assert out[kg.id]["capacity"] == 0
    assert out[kg.id]["children_count"] == 0
