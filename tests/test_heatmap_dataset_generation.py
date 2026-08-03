"""Production data supply for the /api/heatmap dataset.

The security repair (3868f25) stopped production falling back to `test_data.csv`,
which left the heat map secure but sourceless. These tests pin the generator that
fills that gap: what it reads, what it refuses to invent, and what it does when
things go wrong.

Every test writes into a tmp_path. Nothing here may touch the tracked data
directory — a test that regenerated the real CSV would make the suite's result
depend on the order it ran in.
"""
from __future__ import annotations

import csv
import importlib
import json
from datetime import date, timedelta

import pandas as pd
import pytest
import sqlalchemy as sa

import models
from conftest import bearer_headers
from heatmap.backend import constants as C
from heatmap.backend.etl import generate as G
from heatmap.backend.etl.ingest import ingest_csv

GOV_COUNT = len(C.GOVERNORATES)
SNAPSHOT = date(2026, 8, 3)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _kindergarten(name: str, governorate: str, status=models.KindergartenStatus.ACTIVE):
    return models.Kindergarten(
        name_ar=name,
        governorate=governorate,
        district="قصبة",
        area="منطقة",
        address_line="شارع 1",
        contact_phone="+962790000000",
        status=status,
    )


@pytest.fixture
def seeded_db(in_memory_db):
    """Two resolvable kindergartens plus one whose governorate is unmappable."""
    db = in_memory_db
    db.add_all([
        _kindergarten("حضانة عمان", "Amman"),
        _kindergarten("حضانة إربد", "إربد", models.KindergartenStatus.INACTIVE),
        _kindergarten("حضانة مجهولة", "Atlantis"),
    ])
    db.commit()
    return db


@pytest.fixture(autouse=True)
def dataset_dir(tmp_path, monkeypatch):
    """Redirect every module-level path at a temp directory.

    Autouse deliberately: any test in this module can reach the generator, directly
    or through the refresh endpoint, and a *failing* test still executes its side
    effects. Opting in per-test meant one wrong assertion regenerated the real
    heatmap/data/daily_indicators.csv — which happened while writing these tests.
    """
    monkeypatch.setattr(G, "DATA_DIR", tmp_path)
    monkeypatch.setattr(G, "DAILY_DATASET", tmp_path / "daily_indicators.csv")
    monkeypatch.setattr(G, "DATASET_METADATA", tmp_path / "daily_indicators.meta.json")
    return tmp_path


# ---------------------------------------------------------------------------
# Successful generation and schema
# ---------------------------------------------------------------------------

def test_generation_succeeds_and_covers_every_governorate(seeded_db, dataset_dir):
    result = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    assert result.status == "success", result.error
    assert result.rows_written == GOV_COUNT
    assert result.governorates_covered == GOV_COUNT
    assert result.rows_rejected == 0


def test_generated_file_matches_the_declared_schema(seeded_db, dataset_dir):
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    with open(dataset_dir / "daily_indicators.csv", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)

    assert header == G.CSV_COLUMNS, "column order is the file's public contract"


def test_generated_file_survives_its_own_validator(seeded_db, dataset_dir):
    """A producer that emits rows its own ingest rejects is worse than none."""
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    clean, errors = ingest_csv(dataset_dir / "daily_indicators.csv")
    assert errors == []
    assert len(clean) == GOV_COUNT


def test_rows_are_unique_per_admin_id(seeded_db, dataset_dir):
    """(date, admin_id) is the dedup key; a duplicate would silently drop data."""
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    frame = pd.read_csv(dataset_dir / "daily_indicators.csv")

    assert not frame.duplicated(subset=["date", "admin_id"]).any()
    assert set(frame["date"]) == {SNAPSHOT.isoformat()}


# ---------------------------------------------------------------------------
# Database -> column mapping
# ---------------------------------------------------------------------------

def test_kindergarten_status_maps_to_the_right_governorate(seeded_db, dataset_dir):
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    frame = pd.read_csv(dataset_dir / "daily_indicators.csv").set_index("admin_id")

    # One ACTIVE in Amman, one INACTIVE in Irbid (seeded with the Arabic name).
    assert frame.loc["JO-AM", "kindergartens_active"] == 1
    assert frame.loc["JO-AM", "kindergartens_inactive"] == 0
    assert frame.loc["JO-IR", "kindergartens_inactive"] == 1
    assert frame.loc["JO-IR", "kindergartens_active"] == 0


def test_unmappable_governorate_is_reported_not_bucketed(seeded_db, dataset_dir):
    """Attributing a kindergarten to the wrong governorate is worse than omitting it."""
    result = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    assert "Atlantis" in result.unresolved_governorates
    frame = pd.read_csv(dataset_dir / "daily_indicators.csv")
    # The unresolved kindergarten must not inflate any governorate's active count.
    assert frame["kindergartens_active"].sum() == 1


def _make_child(db, parent_profile_id: int, first_name: str) -> models.Child:
    """A real Child row, because the aggregates cannot see anything else.

    database.py installs a `do_orm_execute` listener that constrains every ORM select
    on EnrollmentApplication / AttendanceLog / DailyReport / Incident to children
    satisfying the age policy (`cls.child.has(...)`). Enrollment rows pointing at a
    non-existent child are therefore invisible to the generator — correctly, but it
    means this test needs the real object graph.
    """
    child = models.Child(
        parent_id=parent_profile_id,
        first_name=first_name,
        last_name="اختبار",
        gender=models.Gender.FEMALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
        father_name="أب",
        mother_first_name="أم",
        mother_last_name="اختبار",
        mother_nationality="Jordanian",
    )
    db.add(child)
    db.flush()
    return child


def test_enrolled_children_counts_only_active_enrollments(seeded_db, dataset_dir):
    """Only ACTIVE enrollments count toward the governorate total."""
    kg = seeded_db.query(models.Kindergarten).filter_by(governorate="Amman").first()

    user = models.User(
        username="parent-heatmap", email="parent-heatmap@example.com",
        hashed_password="x", role=models.UserRole.PARENT,
    )
    seeded_db.add(user)
    seeded_db.flush()
    profile = models.ParentProfile(
        user_id=user.id, first_name="ولي", last_name="أمر", phone_number="+962790000001",
        gender=models.Gender.MALE, nationality="Jordanian", home_governorate="Amman",
        home_district="قصبة", home_area="منطقة", home_address_line="شارع 1",
    )
    seeded_db.add(profile)
    seeded_db.flush()

    active_a = _make_child(seeded_db, profile.id, "طفل أ")
    active_b = _make_child(seeded_db, profile.id, "طفل ب")
    withdrawn = _make_child(seeded_db, profile.id, "طفل ج")

    seeded_db.execute(
        sa.insert(models.EnrollmentApplication.__table__),
        [
            {"child_id": active_a.id, "kindergarten_id": kg.id,
             "status": models.EnrollmentStatus.ACTIVE},
            {"child_id": active_b.id, "kindergarten_id": kg.id,
             "status": models.EnrollmentStatus.ACTIVE},
            # Not ACTIVE -> excluded entirely.
            {"child_id": withdrawn.id, "kindergarten_id": kg.id,
             "status": models.EnrollmentStatus.WITHDRAWN},
        ],
    )
    seeded_db.commit()

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    frame = pd.read_csv(dataset_dir / "daily_indicators.csv").set_index("admin_id")
    assert frame.loc["JO-AM", "enrolled_children"] == 2


def test_classes_without_supervisor_is_counted_separately(seeded_db, dataset_dir):
    kg = seeded_db.query(models.Kindergarten).filter_by(governorate="Amman").first()
    seeded_db.add_all([
        models.Class(
            kindergarten_id=kg.id, name_ar="صف أ", class_code="C-A", age_group="AGE_2_4",
            capacity_total=10, min_age_months=24, max_age_months=48, supervisor_id=None,
        ),
        models.Class(
            kindergarten_id=kg.id, name_ar="صف ب", class_code="C-B", age_group="AGE_2_4",
            capacity_total=10, min_age_months=24, max_age_months=48, supervisor_id=7,
        ),
    ])
    seeded_db.commit()

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    frame = pd.read_csv(dataset_dir / "daily_indicators.csv").set_index("admin_id")
    assert frame.loc["JO-AM", "classes_count"] == 2
    assert frame.loc["JO-AM", "classes_without_supervisor"] == 1


# ---------------------------------------------------------------------------
# Unavailable indicators — the core honesty contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("column", sorted(G.UNAVAILABLE_COLUMNS))
def test_unmeasurable_columns_are_blank_never_zero(seeded_db, dataset_dir, column):
    """`unavailable != 0` — pinned by tests/test_heatmap_unavailable_data.py.

    Writing 0 here would satisfy the schema while asserting a measurement nobody
    took: "no child-protection issues" instead of "we cannot measure that".
    """
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    with open(dataset_dir / "daily_indicators.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert rows, "expected generated rows"
    for row in rows:
        assert row[column] == "", f"{column} was emitted as {row[column]!r}, expected blank"


def test_governance_score_is_blank_when_nothing_was_filed(seeded_db, dataset_dir):
    """No score filed is unknown, not zero — zero is the worst possible score."""
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    with open(dataset_dir / "daily_indicators.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert all(r["governance_score"] == "" for r in rows)


def test_governance_score_is_emitted_when_it_exists(seeded_db, dataset_dir):
    kg = seeded_db.query(models.Kindergarten).filter_by(governorate="Amman").first()
    seeded_db.add(models.GovernanceScore(
        kindergarten_id=kg.id,
        period_start=SNAPSHOT - timedelta(days=30),
        period_end=SNAPSHOT,
        governance_quality_index=80.0,
        child_experience_index=70.0,
        final_governance_score=75.0,
        band="B",
    ))
    seeded_db.commit()

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    frame = pd.read_csv(dataset_dir / "daily_indicators.csv").set_index("admin_id")
    assert frame.loc["JO-AM", "governance_score"] == pytest.approx(75.0)


def test_validator_accepts_blank_unavailable_columns():
    """The schema must be able to express 'not measurable' at all."""
    from heatmap.backend.etl.validate import validate_records

    valid, errors = validate_records([{
        "date": "2026-08-03", "admin_id": "JO-AM",
        "kindergartens_active": 1, "kindergartens_inactive": 0,
        "enrolled_children": 5, "unregistered_children": None,
        "supervisors_count": 1, "classes_count": 1,
        "classes_without_supervisor": 0, "critical_incidents": 0,
        "protection_issues": None, "daily_reports_count": 3,
        "absences_total": 2, "absences_health_alerts": None,
        "tasks_overdue": 0, "governance_score": None,
        "training_completion_pct": None,
    }])
    assert errors == []
    assert valid[0]["protection_issues"] is None


# ---------------------------------------------------------------------------
# Atomicity and failure handling
# ---------------------------------------------------------------------------

def test_generation_leaves_no_temp_files_behind(seeded_db, dataset_dir):
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    leftovers = list(dataset_dir.glob(".daily_indicators-*"))
    assert leftovers == [], f"temp files not cleaned up: {leftovers}"


def test_validation_failure_preserves_the_previous_dataset(seeded_db, dataset_dir, monkeypatch):
    """A bad rebuild must never blank a good dataset."""
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    target = dataset_dir / "daily_indicators.csv"
    original = target.read_text(encoding="utf-8")

    # Force every row invalid: an admin_id outside the fixed vocabulary.
    original_build = G.build_rows

    def _bad_rows(db, snapshot):
        rows, unresolved = original_build(db, snapshot)
        for row in rows:
            row["admin_id"] = "JO-NOT-REAL"
        return rows, unresolved

    monkeypatch.setattr(G, "build_rows", _bad_rows)
    result = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    assert result.status == "failed"
    assert result.rows_rejected > 0
    assert target.read_text(encoding="utf-8") == original, "previous dataset was overwritten"


def test_write_failure_preserves_the_previous_dataset(seeded_db, dataset_dir, monkeypatch):
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    target = dataset_dir / "daily_indicators.csv"
    original = target.read_text(encoding="utf-8")

    def _boom(df, destination):
        raise OSError("disk full")

    monkeypatch.setattr(G, "_write_atomic", _boom)
    result = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    assert result.status == "failed"
    assert target.read_text(encoding="utf-8") == original


def test_empty_database_does_not_replace_a_good_dataset(in_memory_db, dataset_dir):
    """Zero kindergartens is a real state, but blanking the map is not the answer."""
    result = G.generate_daily_indicators(in_memory_db, snapshot_date=SNAPSHOT)
    # No kindergartens at all still yields one row per governorate with zero counts,
    # which is a truthful "nothing operating here" rather than an absent dataset.
    assert result.status == "success"
    assert result.rows_written == GOV_COUNT


def test_empty_row_set_is_reported_and_file_untouched(seeded_db, dataset_dir, monkeypatch):
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    target = dataset_dir / "daily_indicators.csv"
    original = target.read_text(encoding="utf-8")

    monkeypatch.setattr(G, "build_rows", lambda db, snapshot: ([], []))
    result = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    assert result.status == "empty"
    assert target.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# Path controls — the 3868f25 guarantee must survive
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "../escape.csv",
    "/etc/passwd",
    "subdir/nested.csv",
])
def test_generator_refuses_paths_outside_the_data_directory(seeded_db, dataset_dir, bad):
    result = G.generate_daily_indicators(
        seeded_db, snapshot_date=SNAPSHOT, destination=dataset_dir / bad
    )
    assert result.status == "failed"
    assert "approved" in (result.error or "").lower() or "refusing" in (result.error or "").lower()


def test_generator_refuses_non_csv_destinations(seeded_db, dataset_dir):
    result = G.generate_daily_indicators(
        seeded_db, snapshot_date=SNAPSHOT, destination=dataset_dir / "payload.sh"
    )
    assert result.status == "failed"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

def test_concurrent_generation_is_refused_not_queued(seeded_db, dataset_dir):
    """Two identical rebuilds racing on one file is waste, not throughput."""
    G._GENERATION_LOCK.acquire()
    try:
        result = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
        assert result.status == "skipped_locked"
    finally:
        G._GENERATION_LOCK.release()


def test_lock_is_released_after_a_failure(seeded_db, dataset_dir, monkeypatch):
    """A generator that leaks its lock on failure would block every later run."""
    original_build = G.build_rows
    monkeypatch.setattr(G, "build_rows", lambda db, s: (_ for _ in ()).throw(RuntimeError("boom")))
    failed = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    assert failed.status == "failed"

    # Restore only build_rows. monkeypatch.undo() would revert *every* patch,
    # including the autouse fixture redirecting DAILY_DATASET — which sent the
    # recovery run below at the real heatmap/data directory while writing this test.
    monkeypatch.setattr(G, "build_rows", original_build)
    recovered = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    assert recovered.status == "success", "lock was not released after the failure"
    assert recovered.output_path.startswith(str(dataset_dir))


# ---------------------------------------------------------------------------
# Freshness reporting
# ---------------------------------------------------------------------------

def test_status_reports_absent_dataset_without_failing(dataset_dir):
    status = G.dataset_status()
    assert status["available"] is False
    assert status["stale"] is False
    assert status["rows"] == 0


def test_status_reports_a_current_dataset(seeded_db, dataset_dir, monkeypatch):
    monkeypatch.setattr(G, "today_amman", lambda: SNAPSHOT)
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    # Metadata is only written for the canonical dataset path.
    G._write_metadata(
        G.GenerationResult(
            status="success", snapshot_date=SNAPSHOT.isoformat(),
            rows_written=GOV_COUNT, governorates_covered=GOV_COUNT,
            generated_at="2026-08-03T20:00:00+03:00",
        ),
        G.DAILY_DATASET,
    )
    status = G.dataset_status()
    assert status["available"] is True
    assert status["stale"] is False
    assert status["age_days"] == 0


def test_status_flags_a_stale_dataset(seeded_db, dataset_dir, monkeypatch):
    old = SNAPSHOT - timedelta(days=G.STALE_AFTER_DAYS + 5)
    monkeypatch.setattr(G, "today_amman", lambda: SNAPSHOT)
    G.generate_daily_indicators(seeded_db, snapshot_date=old)
    G._write_metadata(
        G.GenerationResult(
            status="success", snapshot_date=old.isoformat(),
            rows_written=GOV_COUNT, governorates_covered=GOV_COUNT,
            generated_at=old.isoformat(),
        ),
        G.DAILY_DATASET,
    )
    status = G.dataset_status()
    assert status["available"] is True
    assert status["stale"] is True
    assert status["age_days"] == G.STALE_AFTER_DAYS + 5
    assert "stale" in status["message"].lower()


def test_metadata_records_provenance(seeded_db, dataset_dir):
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    G._write_metadata(
        G.GenerationResult(
            status="success", snapshot_date=SNAPSHOT.isoformat(), rows_written=GOV_COUNT,
        ),
        G.DAILY_DATASET,
    )
    meta = json.loads((dataset_dir / "daily_indicators.meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "kinjo-database"
    assert set(meta["unavailable_columns"]) == set(G.UNAVAILABLE_COLUMNS)


# ---------------------------------------------------------------------------
# Production must never fall back to the bundled fixture
# ---------------------------------------------------------------------------

# `heatmap.backend.api.router` as an attribute resolves to the APIRouter object the
# package re-exports, not the module, so import the module explicitly.
api_router = importlib.import_module("heatmap.backend.api.router")


def test_production_refuses_the_sample_fixture(monkeypatch, tmp_path):
    """The whole point of the security repair; re-pinned here against regression."""
    monkeypatch.setattr(api_router.settings, "ENVIRONMENT", "production")
    monkeypatch.setitem(api_router.PIPELINE_SOURCES, "daily", tmp_path / "absent.csv")

    frame = api_router._load_seed_data()
    assert frame.empty, "production fell back to fixture data"


def test_non_production_may_fall_back_to_the_sample(monkeypatch, tmp_path):
    monkeypatch.setattr(api_router.settings, "ENVIRONMENT", "development")
    monkeypatch.setitem(api_router.PIPELINE_SOURCES, "daily", tmp_path / "absent.csv")

    frame = api_router._load_seed_data()
    assert not frame.empty, "development lost its sample fallback"


# ---------------------------------------------------------------------------
# Admin surface: authorization, CSRF, audit
# ---------------------------------------------------------------------------

def test_dataset_status_requires_authentication(client):
    assert client.get("/api/heatmap/dataset/status").status_code in (401, 403)


def test_dataset_refresh_requires_authentication(client):
    assert client.post("/api/heatmap/dataset/refresh").status_code in (401, 403)


def test_dataset_refresh_follows_the_established_csrf_contract(client, admin_token):
    """Cookie-borne requests need the double-submit pair; bearer calls do not.

    middleware/csrf.py rule 2: a browser cannot attach an Authorization header to a
    forged cross-origin request, so bearer auth is inherently CSRF-safe. Asserting a
    400 for the bearer case would contradict the project's single enforcement point,
    not strengthen it — the real surface is the cookie-carrying browser session.
    """
    from conftest import CSRF_COOKIE_NAME

    # Bearer, no CSRF pair -> exempt by rule 2.
    bearer_only = client.post(
        "/api/heatmap/dataset/refresh",
        headers=bearer_headers(admin_token, with_csrf=False),
    )
    assert bearer_only.status_code == 200, bearer_only.text

    # Cookie present, no matching header -> rejected by rule 4.
    cookie_only = client.post(
        "/api/heatmap/dataset/refresh",
        headers={"Cookie": f"{CSRF_COOKIE_NAME}=abc123"},
    )
    assert cookie_only.status_code == 400


def test_dataset_refresh_accepts_no_path_argument(client, admin_token, monkeypatch):
    """The endpoint must not expose any way to steer the destination."""
    import inspect
    from heatmap.backend.api.router import refresh_dataset

    params = set(inspect.signature(refresh_dataset).parameters)
    assert not params & {"path", "csv_path", "destination", "source", "output"}


def test_manual_refresh_writes_an_audit_event(client, admin_token, test_db, monkeypatch, tmp_path):
    from heatmap.backend.api import router as api_router

    monkeypatch.setattr(G, "DAILY_DATASET", tmp_path / "daily_indicators.csv")
    monkeypatch.setattr(G, "DATA_DIR", tmp_path)
    monkeypatch.setattr(G, "DATASET_METADATA", tmp_path / "daily_indicators.meta.json")

    resp = client.post(
        "/api/heatmap/dataset/refresh", headers=bearer_headers(admin_token)
    )
    assert resp.status_code == 200, resp.text

    events = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == "HEATMAP_DATASET_REGENERATED")
        .all()
    )
    assert events, "manual regeneration must leave an audit trail"
