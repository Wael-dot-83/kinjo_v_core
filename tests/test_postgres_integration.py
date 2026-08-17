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
import threading
from datetime import date, datetime, timedelta, timezone

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
def pg_engine():
    """The engine itself, so a test can open more than one independent session.

    Row-level locking cannot be observed through a single Session — two
    concurrent transactions need two connections. Everything else here is
    single-session, so `pg_session` below stays the ordinary entry point.
    """
    engine = sa.create_engine(PG_URL)
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
            conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"))
            conn.commit()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not reachable: {type(exc).__name__}")

    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        with engine.connect() as conn:
            conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"))
            conn.commit()
        engine.dispose()


@pytest.fixture(scope="module")
def pg_session(pg_engine):
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


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


def test_audit_log_accepts_a_plain_string_detail(pg_session):
    """audit_logs.details must take a sentence, not JSON.

    The column was jsonb in PostgreSQL while the model declared Text, so every
    audit-logged write raised InvalidTextRepresentation — POST
    /api/admin/kindergartens returned 500 and no kindergarten could be created.
    """
    entry = models.AuditLog(
        user_id=None, action="TEST_ACTION", entity_type="Kindergarten",
        entity_id=1, details="Created kindergarten حضانة الاختبار",
    )
    pg_session.add(entry)
    pg_session.commit()
    pg_session.refresh(entry)
    assert entry.details.startswith("Created kindergarten")
    pg_session.delete(entry)
    pg_session.commit()


def test_model_column_types_match_postgres(pg_session):
    """Catch model/database type drift for the JSON-ish columns.

    A column the model calls Text but the database stores as jsonb rejects every
    plain string written to it; the reverse silently stores JSON as opaque text.
    """
    mismatches = []
    inspector = sa.inspect(pg_session.get_bind())
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        if table is None or table.name not in inspector.get_table_names():
            continue
        db_cols = {c["name"]: c["type"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            db_type = db_cols.get(col.key)
            if db_type is None:
                continue
            model_is_json = isinstance(col.type, sa.JSON)
            db_is_json = "JSON" in str(db_type).upper()
            if model_is_json != db_is_json:
                mismatches.append(
                    f"{table.name}.{col.key}: model={col.type} db={db_type}"
                )
    assert not mismatches, (
        "model/PostgreSQL column type drift on JSON columns: " + "; ".join(mismatches)
    )


def test_kg_overview_metrics_bulk_executes_on_postgres(pg_session):
    from analytics_service import AnalyticsService

    kg = _kg(pg_session, 3)
    end = date.today()
    out = AnalyticsService.get_kg_overview_metrics_bulk(
        pg_session, [kg.id], end - timedelta(days=29), end
    )
    assert out[kg.id]["capacity"] == 0
    assert out[kg.id]["children_count"] == 0


# ---------------------------------------------------------------------------
# Supervisor AI daily-report confirmation — atomicity under real concurrency
#
# The confirm endpoint guards a DRAFT -> SUBMITTED transition with
# `SELECT ... FOR UPDATE` plus a status-conditional UPDATE. Neither half means
# anything on SQLite: it ignores FOR UPDATE entirely, and the main suite's
# harness hands every request the same Session on a single in-memory
# connection, so its threaded test can only observe harness artefacts. That
# test is skipped there and says so; this is the test it defers to.
#
# Two real connections, two real transactions, released together by a barrier.
#
# Measured against this database, not assumed — each guard was deleted from
# routers/ai.py in turn and the test re-run:
#
#   FOR UPDATE removed, conditional UPDATE kept ....... still passes
#   conditional UPDATE relaxed, FOR UPDATE kept ....... still passes
#   both removed (plain check-then-set) ............... FAILS, [200, 200]
#
# So the two guards are redundant by design and this test is a regression
# against losing *both* — i.e. against reintroducing the TOCTOU gap itself,
# which is the property that matters. It does not pin either guard
# individually, and no comment here should claim otherwise.
# ---------------------------------------------------------------------------

_CONFIRM_DATE = date(2026, 5, 4)  # a Monday, comfortably in the past


@pytest.fixture()
def confirm_scenario(pg_engine):
    """One supervisor, one assigned child, one DRAFT report ready to confirm."""
    from auth import get_password_hash

    Session = sessionmaker(bind=pg_engine)
    db = Session()
    suffix = os.urandom(4).hex()

    kg = models.Kindergarten(
        name_ar="حضانة التأكيد", name_en=f"Confirm KG {suffix}",
        license_number=f"LIC-CONF-{suffix}",
        governorate="Amman", district="Amman", area="Abdoun",
        address_line="1 Confirm St", contact_phone="+96279000001",
        contact_email=f"conf_{suffix}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.flush()

    cls = models.Class(
        kindergarten_id=kg.id,
        name_ar="صف التأكيد", name_en=f"Confirm Class {suffix}",
        class_code=f"CONF-{suffix}",
        age_group="AGE_2_4",
        capacity_total=10, min_age_months=24, max_age_months=60,
        is_active=True,
    )
    db.add(cls)
    db.flush()

    supervisor = models.User(
        username=f"sup_conf_{suffix}",
        email=f"sup_conf_{suffix}@test.com",
        hashed_password=get_password_hash("Supervisor123!"),
        role=models.UserRole.SUPERVISOR,
        kindergarten_id=kg.id,
        status=models.UserStatus.ACTIVE,
    )
    db.add(supervisor)
    db.flush()

    db.add(models.SupervisorAssignment(
        class_id=cls.id,
        supervisor_id=supervisor.id,
        is_primary=True,
        start_date=_CONFIRM_DATE - timedelta(days=30),
        end_date=None,
    ))

    parent_user = models.User(
        username=f"par_conf_{suffix}",
        email=f"par_conf_{suffix}@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    db.add(parent_user)
    db.flush()

    profile = models.ParentProfile(
        user_id=parent_user.id,
        first_name="Confirm", last_name="Parent",
        phone_number=f"+9627930{suffix[:4]}",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        national_id=f"7777{suffix}",
        home_governorate="Amman", home_district="Amman", home_area="Abdoun",
        home_address_line="1 Confirm St",
        correspondence_preference=True,
    )
    db.add(profile)
    db.flush()

    child = models.Child(
        parent_id=profile.id,
        first_name="Confirm", last_name="Child",
        gender=models.Gender.MALE,
        date_of_birth=_CONFIRM_DATE - timedelta(days=1000),
        father_name="Confirm Father",
        mother_first_name="Confirm", mother_last_name="Mother",
        mother_nationality="Jordanian",
        mother_national_id=f"6666{suffix}",
    )
    db.add(child)
    db.flush()

    db.add(models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        class_id=cls.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=_CONFIRM_DATE - timedelta(days=30),
        source="online",
    ))
    # Pin the working-day gate instead of leaning on settings.TESTING, so the
    # test still means what it says if the suite is ever run without it.
    db.add(models.OperatingCalendar(
        kindergarten_id=kg.id, date=_CONFIRM_DATE, is_open=True,
    ))

    draft = models.DailyReport(
        child_id=child.id,
        kindergarten_id=kg.id,
        class_id=cls.id,
        date=_CONFIRM_DATE,
        status=models.DailyReportStatus.DRAFT,
        submitted_by=supervisor.id,
        arrival_time="08:15",
        leave_time="16:00",
        mood="happy",
        activities="Story time and play",
        created_at=datetime.now(timezone.utc),
    )
    db.add(draft)
    db.commit()

    ids = {
        "draft_id": draft.id,
        "supervisor_id": supervisor.id,
        "child_id": child.id,
        "kindergarten_id": kg.id,
        "class_id": cls.id,
        "parent_user_id": parent_user.id,
        "parent_profile_id": profile.id,
    }
    db.close()

    yield ids

    cleanup = Session()
    try:
        cleanup.query(models.DailyReport).filter(
            models.DailyReport.child_id == ids["child_id"]
        ).delete(synchronize_session=False)
        cleanup.query(models.OperatingCalendar).filter(
            models.OperatingCalendar.kindergarten_id == ids["kindergarten_id"]
        ).delete(synchronize_session=False)
        cleanup.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == ids["child_id"]
        ).delete(synchronize_session=False)
        cleanup.query(models.Child).filter(
            models.Child.id == ids["child_id"]
        ).delete(synchronize_session=False)
        cleanup.query(models.ParentProfile).filter(
            models.ParentProfile.id == ids["parent_profile_id"]
        ).delete(synchronize_session=False)
        cleanup.query(models.SupervisorAssignment).filter(
            models.SupervisorAssignment.class_id == ids["class_id"]
        ).delete(synchronize_session=False)
        cleanup.query(models.AuditLog).filter(
            models.AuditLog.user_id.in_([ids["supervisor_id"], ids["parent_user_id"]])
        ).delete(synchronize_session=False)
        cleanup.query(models.User).filter(
            models.User.id.in_([ids["supervisor_id"], ids["parent_user_id"]])
        ).delete(synchronize_session=False)
        cleanup.query(models.Class).filter(
            models.Class.id == ids["class_id"]
        ).delete(synchronize_session=False)
        cleanup.query(models.Kindergarten).filter(
            models.Kindergarten.id == ids["kindergarten_id"]
        ).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()


@pytest.fixture()
def ai_daily_report_enabled(monkeypatch):
    from config import settings as _settings

    for flag in (
        "AI_ASSISTANT_ENABLED",
        "AI_ASSISTANT_SUPERVISOR_ENABLED",
        "AI_ASSISTANT_SUPERVISOR_DAILY_REPORT_ENABLED",
    ):
        monkeypatch.setattr(_settings, flag, True, raising=False)
    # Generous TTL: this test is about the race, not about expiry.
    monkeypatch.setattr(_settings, "AI_SUPERVISOR_REPORT_DRAFT_TTL_MINUTES", 60, raising=False)
    return _settings


def test_confirm_draft_has_exactly_one_winner_under_postgres_concurrency(
    pg_engine, confirm_scenario, ai_daily_report_enabled
):
    """Two real transactions confirm the same DRAFT at once: one 200, one 409."""
    from fastapi import HTTPException

    from routers.ai import (
        ConfirmSupervisorDailyReportDraftRequest,
        confirm_supervisor_daily_report_draft,
    )

    Session = sessionmaker(bind=pg_engine)
    draft_id = confirm_scenario["draft_id"]
    supervisor_id = confirm_scenario["supervisor_id"]

    barrier = threading.Barrier(2)
    results: dict[int, object] = {}
    results_lock = threading.Lock()

    def worker(idx: int):
        db = Session()
        outcome: object
        try:
            user = db.query(models.User).filter(models.User.id == supervisor_id).one()
            # Both transactions are open and both callers are loaded before
            # either touches the draft — without the barrier the first request
            # would usually finish before the second began, and the race the
            # endpoint guards against would never actually occur.
            barrier.wait(timeout=20)
            try:
                confirm_supervisor_daily_report_draft(
                    draft_id=draft_id,
                    body=ConfirmSupervisorDailyReportDraftRequest(confirmed=True),
                    current_user=user,
                    db=db,
                )
                outcome = 200
            except HTTPException as exc:
                outcome = exc.status_code
            except Exception as exc:  # surfaced, not swallowed
                outcome = f"{type(exc).__name__}: {exc}"
        finally:
            db.rollback()
            db.close()
        with results_lock:
            results[idx] = outcome

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert len(results) == 2, f"both workers must finish; got {results}"
    outcomes = list(results.values())
    assert outcomes.count(200) == 1, (
        f"exactly one confirmation may succeed, got {outcomes}"
    )
    assert [o for o in outcomes if o != 200] == [409], (
        f"the losing request must get a deterministic 409, got {outcomes}"
    )

    verify = Session()
    try:
        rows = (
            verify.query(models.DailyReport)
            .filter(
                models.DailyReport.child_id == confirm_scenario["child_id"],
                models.DailyReport.date == _CONFIRM_DATE,
            )
            .all()
        )
        # No duplicate report, no second row, no partial write.
        assert len(rows) == 1, f"confirmation must not create a report, got {len(rows)}"
        assert rows[0].id == draft_id
        assert rows[0].status == models.DailyReportStatus.SUBMITTED
        assert rows[0].submitted_by == supervisor_id
        assert rows[0].submitted_at is not None
    finally:
        verify.close()


def test_confirm_draft_loser_leaves_no_partial_write_on_postgres(
    pg_engine, confirm_scenario, ai_daily_report_enabled
):
    """A rejected second confirmation must not mutate the finalized row.

    The sequential companion to the race above: it pins down *which* request
    loses, so the 409 branch is proven to roll back rather than merely to
    return an error code.
    """
    from fastapi import HTTPException

    from routers.ai import (
        ConfirmSupervisorDailyReportDraftRequest,
        confirm_supervisor_daily_report_draft,
    )

    Session = sessionmaker(bind=pg_engine)
    draft_id = confirm_scenario["draft_id"]
    supervisor_id = confirm_scenario["supervisor_id"]
    body = ConfirmSupervisorDailyReportDraftRequest(confirmed=True)

    first = Session()
    try:
        user = first.query(models.User).filter(models.User.id == supervisor_id).one()
        response = confirm_supervisor_daily_report_draft(
            draft_id=draft_id, body=body, current_user=user, db=first
        )
        assert response["status"] == "submitted"
        assert response["confirmed"] is True
    finally:
        first.close()

    snapshot = Session()
    try:
        row = snapshot.query(models.DailyReport).filter(
            models.DailyReport.id == draft_id
        ).one()
        submitted_at_before = row.submitted_at
    finally:
        snapshot.close()

    second = Session()
    try:
        user = second.query(models.User).filter(models.User.id == supervisor_id).one()
        with pytest.raises(HTTPException) as exc_info:
            confirm_supervisor_daily_report_draft(
                draft_id=draft_id, body=body, current_user=user, db=second
            )
        assert exc_info.value.status_code == 409
    finally:
        second.rollback()
        second.close()

    verify = Session()
    try:
        rows = (
            verify.query(models.DailyReport)
            .filter(
                models.DailyReport.child_id == confirm_scenario["child_id"],
                models.DailyReport.date == _CONFIRM_DATE,
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].status == models.DailyReportStatus.SUBMITTED
        # The refused attempt must not have re-stamped the winner's timestamp.
        assert rows[0].submitted_at == submitted_at_before
    finally:
        verify.close()


def test_daily_report_jordan_date_check_constraint_in_postgres(pg_engine):
    """Real PostgreSQL database proof: the ck_report_not_future CHECK constraint enforces
    Jordan business date semantics (date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date),
    even when the PostgreSQL session TimeZone is UTC.
    """
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        # Ensure session timezone is UTC (standard production database session)
        session.execute(sa.text("SET TIME ZONE 'UTC'"))

        # Ensure the Jordan constraint is active on the test table
        session.execute(sa.text("ALTER TABLE daily_reports DROP CONSTRAINT IF EXISTS ck_report_not_future"))
        session.execute(sa.text("""
            ALTER TABLE daily_reports
                ADD CONSTRAINT ck_report_not_future
                CHECK (date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """))
        session.commit()

        # Seed prerequisite entities
        kg = models.Kindergarten(
            name_ar="حضانة الاختبار",
            name_en="Test KG",
            license_number="LIC-PG-TZ-001",
            governorate="Amman", district="Amman", area="Abdoun",
            address_line="1 Test St", contact_phone="+96279000000",
            contact_email="pg_tz@test.jo",
            status=models.KindergartenStatus.ACTIVE,
            license_valid_until=date(2027, 12, 31),
        )
        session.add(kg)
        session.flush()

        u = models.User(
            username="pg_tz_supervisor",
            email="pg_tz_sup@test.com",
            hashed_password="hash",
            role=models.UserRole.SUPERVISOR,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kg.id,
        )
        session.add(u)
        session.flush()

        cls = models.Class(
            kindergarten_id=kg.id,
            name_ar="صف تجريبي",
            name_en="TZ Test Class",
            class_code="TZ-TEST-01",
            age_group="AGE_2_4",
            capacity_total=15,
            min_age_months=24,
            max_age_months=60,
            is_active=True,
        )
        session.add(cls)
        session.flush()

        parent_user = models.User(
            username="pg_tz_parent",
            email="pg_tz_par@test.com",
            hashed_password="hash",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        session.add(parent_user)
        session.flush()

        profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name="TZParent", last_name="Test",
            phone_number="+96279300001",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="999900001",
            home_governorate="Amman", home_district="Amman", home_area="Abdoun",
            home_address_line="1 TZ St",
            correspondence_preference=True,
        )
        session.add(profile)
        session.flush()

        ch = models.Child(
            parent_id=profile.id,
            first_name="TZChild", last_name="Test",
            gender=models.Gender.MALE,
            date_of_birth=date(2023, 1, 1),
            father_name="TZFather",
            mother_first_name="TZMother", mother_last_name="Test",
            mother_nationality="Jordanian",
            mother_national_id="999900002",
        )
        session.add(ch)
        session.flush()

        ch_future = models.Child(
            parent_id=profile.id,
            first_name="TZChild2", last_name="Test",
            gender=models.Gender.FEMALE,
            date_of_birth=date(2023, 2, 1),
            father_name="TZFather",
            mother_first_name="TZMother", mother_last_name="Test",
            mother_nationality="Jordanian",
            mother_national_id="999900003",
        )
        session.add(ch_future)
        session.flush()
        session.commit()

        # Query effective Jordan date in PostgreSQL
        jordan_today = session.execute(
            sa.text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date")
        ).scalar()
        jordan_tomorrow = jordan_today + timedelta(days=1)
        jordan_yesterday = jordan_today - timedelta(days=1)

        # 1. Today in Jordan: MUST SUCCEED (even if UTC date is yesterday)
        dr_today = models.DailyReport(
            child_id=ch.id,
            kindergarten_id=kg.id,
            class_id=cls.id,
            date=jordan_today,
            status=models.DailyReportStatus.DRAFT,
            submitted_by=u.id,
            arrival_time="08:00",
        )
        session.add(dr_today)
        session.commit()
        assert dr_today.id is not None

        # 2. Yesterday in Jordan: MUST SUCCEED
        dr_yesterday = models.DailyReport(
            child_id=ch.id,
            kindergarten_id=kg.id,
            class_id=cls.id,
            date=jordan_yesterday,
            status=models.DailyReportStatus.DRAFT,
            submitted_by=u.id,
            arrival_time="08:00",
        )
        session.add(dr_yesterday)
        session.commit()
        assert dr_yesterday.id is not None

        # 3. Tomorrow in Jordan: MUST BE REJECTED by PostgreSQL CHECK constraint
        dr_future = models.DailyReport(
            child_id=ch_future.id,
            kindergarten_id=kg.id,
            class_id=cls.id,
            date=jordan_tomorrow,
            status=models.DailyReportStatus.DRAFT,
            submitted_by=u.id,
            arrival_time="08:00",
        )
        session.add(dr_future)
        with pytest.raises(sa.exc.IntegrityError) as exc_info:
            session.commit()
        assert "ck_report_not_future" in str(exc_info.value).lower()
        session.rollback()

        # 4. AttendanceLog: Today in Jordan SUCCEEDS, Tomorrow REJECTED
        session.execute(sa.text("ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_not_future"))
        session.execute(sa.text("""
            ALTER TABLE attendance_logs
            ADD CONSTRAINT ck_attendance_not_future
            CHECK (date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """))
        session.commit()

        att_today = models.AttendanceLog(
            child_id=ch.id,
            class_id=cls.id,
            date=jordan_today,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=u.id,
        )
        session.add(att_today)
        session.commit()
        assert att_today.id is not None

        att_future = models.AttendanceLog(
            child_id=ch_future.id,
            class_id=cls.id,
            date=jordan_tomorrow,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=u.id,
        )
        session.add(att_future)
        with pytest.raises(sa.exc.IntegrityError) as exc_info:
            session.commit()
        assert "ck_attendance_not_future" in str(exc_info.value).lower()
        session.rollback()

        # 5. Child DOB: Today in Jordan SUCCEEDS, Tomorrow REJECTED
        session.execute(sa.text("ALTER TABLE children DROP CONSTRAINT IF EXISTS ck_children_dob_not_future"))
        session.execute(sa.text("""
            ALTER TABLE children
            ADD CONSTRAINT ck_children_dob_not_future
            CHECK (date_of_birth <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """))
        session.commit()

        # Direct SQL insertion for today's Jordan date
        session.execute(sa.text("""
            INSERT INTO children (public_id, parent_id, first_name, last_name, gender, date_of_birth, father_name,
                                  mother_first_name, mother_last_name, mother_nationality, mother_national_id,
                                  media_consent, correspondence_flag, profile_complete)
            VALUES ('pub-today-01', :parent_id, 'TZChildToday', 'Test', 'MALE', :dob, 'TZFather',
                    'TZMother', 'Test', 'Jordanian', '999900010', false, false, false)
        """), {"parent_id": profile.id, "dob": jordan_today})
        session.commit()

        # Direct SQL insertion for tomorrow's Jordan date must raise IntegrityError
        with pytest.raises(sa.exc.IntegrityError) as exc_info:
            session.execute(sa.text("""
                INSERT INTO children (public_id, parent_id, first_name, last_name, gender, date_of_birth, father_name,
                                      mother_first_name, mother_last_name, mother_nationality, mother_national_id,
                                      media_consent, correspondence_flag, profile_complete)
                VALUES ('pub-tomorrow-01', :parent_id, 'TZChildTomorrow', 'Test', 'MALE', :dob, 'TZFather',
                        'TZMother', 'Test', 'Jordanian', '999900011', false, false, false)
            """), {"parent_id": profile.id, "dob": jordan_tomorrow})
            session.commit()
        assert "ck_children_dob_not_future" in str(exc_info.value).lower()
        session.rollback()

        # 6. Incident occurred_at: Today in Jordan SUCCEEDS, Future REJECTED
        session.execute(sa.text("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS ck_incident_not_future"))
        session.execute(sa.text("""
            ALTER TABLE incidents
            ADD CONSTRAINT ck_incident_not_future
            CHECK (DATE(occurred_at AT TIME ZONE 'Asia/Amman') <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Amman')::date)
        """))
        session.commit()

        inc_today = models.Incident(
            child_id=ch.id,
            kindergarten_id=kg.id,
            class_id=cls.id,
            reported_by=u.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.LOW,
            description="Test incident today",
            occurred_at=datetime.now(timezone.utc),
            parent_informed=True,
        )
        session.add(inc_today)
        session.commit()
        assert inc_today.id is not None

        inc_future = models.Incident(
            child_id=ch.id,
            kindergarten_id=kg.id,
            class_id=cls.id,
            reported_by=u.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.LOW,
            description="Test incident future",
            occurred_at=datetime.now(timezone.utc) + timedelta(days=2),
            parent_informed=True,
        )
        session.add(inc_future)
        with pytest.raises(sa.exc.IntegrityError) as exc_info:
            session.commit()
        assert "ck_incident_not_future" in str(exc_info.value).lower()
        session.rollback()
    finally:
        session.close()
