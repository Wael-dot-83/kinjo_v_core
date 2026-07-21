"""Deployment tests for c7d9e1a4b820 — the columns models.py declares but no migration made.

These deliberately drive **Alembic**, not `Base.metadata.create_all()`. The whole bug class
this file guards against is invisible to the rest of the suite precisely because conftest
builds its schema with `create_all`: every declared column simply exists there, so a column
that no migration creates still passes every normal test and only fails on a freshly
migrated deployment.

**SQLite alone is not enough here, and this file learned that the hard way.** The first
version of this migration passed every SQLite test and then failed on the first real
PostgreSQL run with `relation "idx_ai_features_entity_feature" already exists`, because
PostgreSQL keeps indexes and constraints in one namespace and SQLite does not. Two more
divergences bit during the same session:

  * SQLite does not enforce foreign keys unless `PRAGMA foreign_keys=ON`, so a seed with
    `children.parent_id` pointing at `users` (it must point at `parent_profiles`) passes on
    SQLite and is rejected by PostgreSQL.
  * SQLite stores enums as plain VARCHAR, so a wrong label like 'Open' inserts happily;
    PostgreSQL rejects it with `invalid input value for enum incidentstatus`.

So the PostgreSQL tests below are the ones with real authority. They run automatically when
a PostgreSQL URL is available (the `migrations` CI job provides one via DATABASE_URL) and
skip otherwise, which keeps a laptop-only run fast without pretending SQLite proved
something it cannot.

Covered:
  * fresh database, base -> head
  * an existing pre-migration database with rows, upgraded to head (the backfill path)
  * the real workflows against the drifted columns, with rows that actually persist
  * upgrade -> downgrade -> upgrade
  * `alembic check` reports no add_table/add_column/add_constraint drift
  * PostgreSQL only: the enum type is reused not recreated, the constraint rename lands,
    the owner FK is enforced, and 'Open' is rejected
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

_ROOT = Path(__file__).resolve().parents[1]
_PREV_REV = "1417f512f696"


def _pg_admin_url() -> str | None:
    """A PostgreSQL URL to create throwaway test databases on, or None to skip."""
    url = os.environ.get("MIGRATION_TEST_POSTGRES_URL") or os.environ.get("DATABASE_URL", "")
    return url if url.startswith("postgresql") else None


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, DATABASE_URL=db_url)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=900,
    )


def _sqlite_url(db: Path) -> str:
    return f"sqlite:///{db.as_posix()}"


def _cols(db_url: str, table: str) -> set[str]:
    engine = sa.create_engine(db_url)
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def _seed_rows(db_url: str, n_incidents: int = 3) -> dict[str, int]:
    """Insert a valid row graph, at `_PREV_REV` or at head. Returns the ids the tests need.

    The FK graph matters more than it looks: `children.parent_id` references
    **parent_profiles**, not users. PostgreSQL enforces that; SQLite leaves foreign keys off
    by default, so seeding `parent_id` with a user id passes on SQLite and is rejected by
    PostgreSQL. Get this wrong and the test proves nothing on the engine that ships.

    Incidents are seeded with an explicit status only once the column exists — after this
    migration it is NOT NULL with no server default, so the insert has to supply it, while
    before the migration the column is not there at all.
    """
    engine = sa.create_engine(db_url)
    has_status = "status" in {c["name"] for c in sa.inspect(engine).get_columns("incidents")}
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO kindergartens (name_ar,governorate,district,area,address_line,"
                "contact_phone,status) VALUES ('حضانة','عمان','ماركا','منطقة','addr','07','ACTIVE')"
            ))
            kg = conn.execute(sa.text("SELECT id FROM kindergartens ORDER BY id LIMIT 1")).scalar_one()

            for name in ("reporter", "owner"):
                conn.execute(
                    sa.text(
                        "INSERT INTO users (username,email,hashed_password,role,status,"
                        "must_change_password,mfa_enabled,failed_login_count) "
                        "VALUES (:u,:e,'x','ADMIN','ACTIVE',:f,:f,0)"
                    ),
                    {"u": name, "e": f"{name}@t.co", "f": False},
                )
            reporter = conn.execute(
                sa.text("SELECT id FROM users WHERE username='reporter'")
            ).scalar_one()
            owner = conn.execute(
                sa.text("SELECT id FROM users WHERE username='owner'")
            ).scalar_one()

            conn.execute(
                sa.text(
                    "INSERT INTO parent_profiles (user_id,first_name,last_name,phone_number,"
                    "gender,nationality,home_governorate,home_district,home_area,"
                    "home_address_line,correspondence_preference,profile_complete) "
                    "VALUES (:uid,'p','q','0790000000','FEMALE','JO','عمان','ماركا','منطقة',"
                    "'addr',:t,:t)"
                ),
                {"uid": reporter, "t": True},
            )
            parent = conn.execute(sa.text("SELECT id FROM parent_profiles LIMIT 1")).scalar_one()

            conn.execute(
                sa.text(
                    "INSERT INTO children (parent_id,first_name,last_name,gender,date_of_birth,"
                    "father_name,mother_first_name,mother_last_name,mother_nationality,"
                    "media_consent,correspondence_flag,profile_complete,has_special_needs,"
                    "has_medical_condition) VALUES (:pid,'a','b','MALE','2022-01-01','f','m','l',"
                    "'JO',:f,:f,:f,:f,:f)"
                ),
                {"pid": parent, "f": False},
            )
            child = conn.execute(sa.text("SELECT id FROM children LIMIT 1")).scalar_one()

            status_col = ",status" if has_status else ""
            status_val = ",'OPEN'" if has_status else ""
            for i in range(n_incidents):
                conn.execute(
                    sa.text(
                        "INSERT INTO incidents (child_id,kindergarten_id,type,severity_level,"
                        "description,occurred_at,followup_required_flag,parent_informed,"
                        f"reported_by{status_col}) VALUES (:c,:k,'INJURY','LOW',:d,"
                        f"'2026-07-01 10:00:00+03',:f,:f,:r{status_val})"
                    ),
                    {"c": child, "k": kg, "d": f"incident {i}", "f": False, "r": reporter},
                )
        return {"kindergarten": kg, "reporter": reporter, "owner": owner, "child": child}
    finally:
        engine.dispose()


# --------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------

@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return _sqlite_url(tmp_path / "fresh.db")


@pytest.fixture
def pg_url():
    """A throwaway PostgreSQL database, dropped afterwards. Skips when no server is set."""
    admin = _pg_admin_url()
    if not admin:
        pytest.skip(
            "no PostgreSQL available — set MIGRATION_TEST_POSTGRES_URL (or DATABASE_URL) to a "
            "postgresql:// URL. SQLite cannot prove enum reuse or index/constraint namespacing."
        )
    name = f"pr59_{uuid.uuid4().hex[:12]}"
    base = admin.rsplit("/", 1)[0]
    engine = sa.create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()
    try:
        yield f"{base}/{name}"
    finally:
        engine = sa.create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                conn.execute(sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ), {"n": name})
                conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        finally:
            engine.dispose()


@pytest.fixture
def fresh_sqlite(sqlite_url: str) -> str:
    r = _alembic(sqlite_url, "upgrade", "head")
    assert r.returncode == 0, f"base -> head failed on sqlite:\n{r.stderr[-2000:]}"
    return sqlite_url


@pytest.fixture
def fresh_pg(pg_url: str) -> str:
    r = _alembic(pg_url, "upgrade", "head")
    assert r.returncode == 0, f"base -> head failed on postgres:\n{r.stderr[-3000:]}"
    return pg_url


# --------------------------------------------------------------------------------------
# engine-agnostic: schema shape
# --------------------------------------------------------------------------------------

def test_fresh_sqlite_has_the_drifted_columns(fresh_sqlite: str) -> None:
    """base -> head must produce every column models.py declares."""
    incidents = _cols(fresh_sqlite, "incidents")
    reports = _cols(fresh_sqlite, "reports")
    assert "status" in incidents, "incidents.status missing from a chain-built DB"
    assert "owner_id" in incidents, "incidents.owner_id missing from a chain-built DB"
    assert "district" in reports, "reports.district missing from a chain-built DB"
    assert "area" in reports, "reports.area missing from a chain-built DB"


def test_fresh_postgres_has_the_drifted_columns(fresh_pg: str) -> None:
    """The same assertion on the engine that actually ships.

    This is not redundant with the SQLite test: reaching `head` at all on PostgreSQL is the
    assertion. The first cut of this migration got here and aborted.
    """
    incidents = _cols(fresh_pg, "incidents")
    reports = _cols(fresh_pg, "reports")
    assert {"status", "owner_id"} <= incidents
    assert {"district", "area"} <= reports


# --------------------------------------------------------------------------------------
# the backfill path, on both engines
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("engine_name", ["sqlite", "postgres"])
def test_existing_database_with_rows_upgrades_and_backfills(
    engine_name: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """A pre-migration DB **with rows** must upgrade, and every row must get a status.

    status is NOT NULL with no server default, so a wrong backfill fails the ALTER here. It
    also pins the enum representation: SQLAlchemy stores the member NAME ('OPEN'), not its
    value ('Open'). On PostgreSQL the value is rejected outright by the enum type; on SQLite
    it would silently store the wrong string, which is why this runs on both.
    """
    if engine_name == "postgres":
        db_url = request.getfixturevalue("pg_url")
    else:
        db_url = _sqlite_url(tmp_path / "existing.db")

    r = _alembic(db_url, "upgrade", _PREV_REV)
    assert r.returncode == 0, f"upgrade to {_PREV_REV} failed:\n{r.stderr[-2000:]}"
    assert "status" not in _cols(db_url, "incidents"), (
        "incidents.status already exists at the previous revision — the premise of this "
        "test (and of the migration) is wrong"
    )

    _seed_rows(db_url, n_incidents=3)

    r = _alembic(db_url, "upgrade", "head")
    assert r.returncode == 0, f"existing DB -> head failed:\n{r.stderr[-3000:]}"

    engine = sa.create_engine(db_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(
                sa.text("SELECT COUNT(*) FROM incidents WHERE status IS NULL")
            ).scalar_one() == 0, "backfill left NULLs — NOT NULL cannot hold"
            assert conn.execute(
                sa.text("SELECT DISTINCT status FROM incidents")
            ).scalars().all() == ["OPEN"], "pre-existing rows must backfill to the enum NAME"
            assert conn.execute(
                sa.text("SELECT COUNT(*) FROM incidents WHERE owner_id IS NULL")
            ).scalar_one() == 3, "existing rows must keep owner_id NULL, not be invented"
    finally:
        engine.dispose()


# --------------------------------------------------------------------------------------
# the real workflows — rows that actually persist
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("engine_name", ["sqlite", "postgres"])
def test_drifted_columns_carry_the_real_workflows(
    engine_name: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """Assign an owner, transition status, record history, file a scoped report — and read
    every one of them back.

    An earlier version of this test updated `WHERE id = -1` and selected from an empty
    `reports`, so it proved the columns *parse* and nothing else. These assertions fail if
    the columns exist but do not persist.
    """
    if engine_name == "postgres":
        db_url = request.getfixturevalue("fresh_pg")
    else:
        db_url = request.getfixturevalue("fresh_sqlite")

    ids = _seed_rows(db_url, n_incidents=1)
    engine = sa.create_engine(db_url)
    try:
        with engine.begin() as conn:
            incident = conn.execute(sa.text("SELECT id FROM incidents LIMIT 1")).scalar_one()

            # a real owner assignment + status transition
            conn.execute(
                sa.text("UPDATE incidents SET owner_id = :o, status = 'UNDER_INVESTIGATION' "
                        "WHERE id = :i"),
                {"o": ids["owner"], "i": incident},
            )
            row = conn.execute(
                sa.text("SELECT status, owner_id FROM incidents WHERE id = :i"), {"i": incident}
            ).one()
            assert row.status == "UNDER_INVESTIGATION", "status transition did not persist"
            assert row.owner_id == ids["owner"], "owner assignment did not persist"

            # the history row that records that transition
            conn.execute(
                sa.text(
                    "INSERT INTO incident_history (incident_id,changed_by,status_from,status_to,"
                    "owner_from_id,owner_to_id,notes) VALUES (:i,:by,'OPEN','UNDER_INVESTIGATION',"
                    "NULL,:to,'assigned')"
                ),
                {"i": incident, "by": ids["reporter"], "to": ids["owner"]},
            )
            hist = conn.execute(
                sa.text("SELECT status_from, status_to, owner_to_id FROM incident_history "
                        "WHERE incident_id = :i"),
                {"i": incident},
            ).one()
            assert hist.status_from == "OPEN"
            assert hist.status_to == "UNDER_INVESTIGATION"
            assert hist.owner_to_id == ids["owner"]

            # a complete, scoped report — the reason reports.district/area exist
            conn.execute(
                # metrics_json goes through a bind parameter: an inline '{"filed":1}' literal
                # would have its ':1' swallowed as a bind parameter by sa.text().
                sa.text(
                    "INSERT INTO reports (report_type,scope_type,start_date,end_date,"
                    "metrics_json,created_by,district,area) VALUES ('ATTENDANCE_SUMMARY',"
                    "'KINDERGARTEN','2026-07-01','2026-07-31',:m,:by,'ماركا','منطقة')"
                ),
                {"m": '{"filed": 1}', "by": ids["reporter"]},
            )
            rep = conn.execute(sa.text("SELECT district, area FROM reports")).one()
            assert rep.district == "ماركا", "reports.district did not persist"
            assert rep.area == "منطقة", "reports.area did not persist"

            # the list filter live code runs
            assert conn.execute(
                sa.text("SELECT COUNT(*) FROM incidents WHERE status = 'UNDER_INVESTIGATION'")
            ).scalar_one() == 1
    finally:
        engine.dispose()


# --------------------------------------------------------------------------------------
# reversibility
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("engine_name", ["sqlite", "postgres"])
def test_upgrade_downgrade_upgrade_is_clean(
    engine_name: str, request: pytest.FixtureRequest
) -> None:
    db_url = request.getfixturevalue("fresh_pg" if engine_name == "postgres" else "fresh_sqlite")

    # Downgrade to the revision *before* c7d9e1a4b820 (which added the incidents/reports
    # columns asserted below). A relative "-1" would only undo whichever migration is
    # currently the head, so target the parent revision explicitly to stay correct as
    # new migrations (e.g. canon_gov_cap_01) are stacked on top.
    r = _alembic(db_url, "downgrade", "1417f512f696")
    assert r.returncode == 0, f"downgrade failed:\n{r.stderr[-3000:]}"
    assert "status" not in _cols(db_url, "incidents"), "downgrade left incidents.status"
    assert "owner_id" not in _cols(db_url, "incidents"), "downgrade left incidents.owner_id"
    assert "district" not in _cols(db_url, "reports"), "downgrade left reports.district"

    r = _alembic(db_url, "upgrade", "head")
    assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr[-3000:]}"
    assert {"status", "owner_id"} <= _cols(db_url, "incidents")


# --------------------------------------------------------------------------------------
# PostgreSQL-only: the things SQLite structurally cannot check
# --------------------------------------------------------------------------------------

def test_postgres_has_exactly_one_incidentstatus_enum(fresh_pg: str) -> None:
    """1417f512f696 already created the type; this migration must reuse it, not recreate it.

    A second CREATE TYPE aborts the deploy, which is why the migration passes
    create_type=False. SQLite renders the enum as VARCHAR + CHECK, so it cannot see this.
    """
    engine = sa.create_engine(fresh_pg)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text(
                "SELECT COUNT(*) FROM pg_type WHERE typname = 'incidentstatus'"
            )).scalar_one() == 1, "incidentstatus must exist exactly once"
            assert conn.execute(sa.text(
                "SELECT e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
                "WHERE t.typname = 'incidentstatus' ORDER BY e.enumsortorder"
            )).scalars().all() == [
                "OPEN", "UNDER_INVESTIGATION", "ACTION_REQUIRED", "RESOLVED", "CLOSED"
            ]
    finally:
        engine.dispose()


def test_postgres_rejects_the_enum_value_spelling(fresh_pg: str) -> None:
    """'Open' is the enum's *value*; 'OPEN' is the member NAME that SQLAlchemy persists.

    Backfilling 'Open' was the specified approach and would have aborted every PostgreSQL
    deploy. This pins the distinction so nobody re-introduces it.
    """
    engine = sa.create_engine(fresh_pg)
    try:
        with engine.connect() as conn:
            with pytest.raises(sa.exc.DBAPIError, match="invalid input value for enum"):
                conn.execute(sa.text("SELECT 'Open'::incidentstatus"))
    finally:
        engine.dispose()


def test_postgres_unique_guarantees_are_intact_and_not_duplicated(fresh_pg: str) -> None:
    """All three "missing" unique constraints: enforced, correctly named, exactly once.

    None of them was ever missing. ai_features and governorate are unique *indexes*
    (autogenerate reports a unique index as a missing unique constraint, forever), and
    imported_kindergartens only had a stale name. The `== 1` assertions are the point: the
    first cut of this migration would have added a redundant second unique index over
    governorate.slug.
    """
    engine = sa.create_engine(fresh_pg)
    try:
        with engine.connect() as conn:
            def n_relations(name: str) -> int:
                return conn.execute(sa.text(
                    "SELECT COUNT(*) FROM pg_class WHERE relname = :n"
                ), {"n": name}).scalar_one()

            assert n_relations("idx_ai_features_entity_feature") == 1
            assert n_relations("ix_governorate_slug") == 1
            assert n_relations("uq_governorate_slug") == 0, (
                "a second unique index over governorate.slug is redundant — slug is already "
                "unique via ix_governorate_slug"
            )

            assert conn.execute(sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'uq_imported_kindergartens_name_district_phone'"
            )).scalar_one() == "UNIQUE (name_ar, district, phone)"
            assert conn.execute(sa.text(
                "SELECT COUNT(*) FROM pg_constraint "
                "WHERE conname = 'uq_imported_kindergartens_name_city_phone'"
            )).scalar_one() == 0, "the stale 'city' name must be gone after the rename"

            # the uniqueness is real, not just declared
            with pytest.raises(sa.exc.IntegrityError):
                with engine.begin() as w:
                    w.execute(sa.text(
                        "INSERT INTO governorate (code,slug,name_en,name_ar,center_lon,"
                        "center_lat,display_order) VALUES ('XX','amman','Dup','مكرر',1,1,99)"
                    ))
    finally:
        engine.dispose()


def test_postgres_enforces_the_owner_foreign_key(fresh_pg: str) -> None:
    """owner_id must be a real FK. SQLite leaves foreign keys off, so it cannot show this."""
    ids = _seed_rows(fresh_pg, n_incidents=1)
    engine = sa.create_engine(fresh_pg)
    try:
        with engine.connect() as conn:
            incident = conn.execute(
                sa.text("SELECT id FROM incidents LIMIT 1")
            ).scalar_one()
        with pytest.raises(sa.exc.IntegrityError, match="fk_incidents_owner_id_users"):
            with engine.begin() as conn:
                conn.execute(
                    sa.text("UPDATE incidents SET owner_id = 999999 WHERE id = :i"),
                    {"i": incident},
                )
        # and a valid owner still works
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE incidents SET owner_id = :o WHERE id = :i"),
                {"o": ids["owner"], "i": incident},
            )
    finally:
        engine.dispose()


# --------------------------------------------------------------------------------------
# drift
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("engine_name", ["sqlite", "postgres"])
def test_alembic_check_reports_no_missing_schema(
    engine_name: str, request: pytest.FixtureRequest
) -> None:
    """No add_* drift: nothing models.py declares may be absent from the chain.

    Scope is deliberate. add_table/add_column/add_constraint are the shapes that break a
    fresh deployment, and they are what this PR closes. The check still reports
    add_index/add_fk and a large remove_*/modify_* surface — all pre-existing, none of it a
    crash, and none of it safe to assume harmless (orphaned schema can still carry
    retention, security, or raw-SQL dependencies). Those are tracked separately rather than
    fixed under cover of this migration.
    """
    db_url = request.getfixturevalue("fresh_pg" if engine_name == "postgres" else "fresh_sqlite")

    out = _alembic(db_url, "check")
    blob = out.stdout + out.stderr
    for op in ("'add_table'", "'add_column'", "'add_constraint'"):
        assert op not in blob, (
            f"{op} drift is back: models.py declares schema no migration creates, which "
            f"fails on a fresh deployment.\n{blob[-1500:]}"
        )
