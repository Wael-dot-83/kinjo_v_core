"""tests/test_concurrent_enrollment_postgres.py — Concurrent row-lock capacity enforcement test.

Priority order for the database backend:
  1. POSTGRES_TEST_DATABASE_URL env var (externally-provided PostgreSQL)
  2. testcontainers auto-provisioned PostgreSQL via Docker
  3. SQLite WAL-mode file DB (always available — tests logical enforcement, not PG row locks)

The PostgreSQL path is the gold standard: it catches regressions where `.with_for_update()`
is removed, because PostgreSQL's MVCC allows two concurrent transactions to see the same
stale row; the FOR UPDATE lock prevents that. SQLite serialises all writes anyway (WAL mode
does not truly parallelise writes) so the capacity gate is enforced regardless of whether
the lock is in place — the SQLite path tests the application-level logic, not the lock.

To run against real PostgreSQL:
    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/kinjo_test \\
        pytest tests/test_concurrent_enrollment_postgres.py -v

Or with a local Docker PostgreSQL (auto-provisioned):
    pytest tests/test_concurrent_enrollment_postgres.py -v  # Docker must be running
"""
import os
import tempfile
import threading
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

PG_URL = os.environ.get("POSTGRES_TEST_DATABASE_URL")
_BACKEND: str = "unknown"
_SESSION_FACTORY = None


def _try_testcontainers():
    """Return a PostgreSQL URL from testcontainers, or None if Docker unavailable."""
    try:
        from testcontainers.postgres import PostgresContainer
        container = PostgresContainer("postgres:16-alpine")
        container.start()
        return container, container.get_connection_url().replace("psycopg2", "psycopg2")
    except Exception:
        return None, None


def _detect_backend():
    global _BACKEND, _SESSION_FACTORY, _CONTAINER
    _CONTAINER = None
    if PG_URL:
        _BACKEND = "postgres-env"
        engine = create_engine(PG_URL, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        _SESSION_FACTORY = sessionmaker(bind=engine)
        return

    container, url = _try_testcontainers()
    if url:
        _CONTAINER = container
        _BACKEND = "postgres-docker"
        engine = create_engine(url, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        _SESSION_FACTORY = sessionmaker(bind=engine)
        return

    # SQLite WAL fallback — tests logical capacity enforcement
    _BACKEND = "sqlite-wal"
    _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmp.close()
    engine = create_engine(
        f"sqlite:///{_tmp.name}",
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")

    Base.metadata.create_all(engine)
    _SESSION_FACTORY = sessionmaker(bind=engine)


_detect_backend()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_sessionmaker():
    yield _SESSION_FACTORY
    if _CONTAINER is not None:
        _CONTAINER.stop()


@pytest.fixture()
def seeded_scenario(db_sessionmaker):
    """Seed: 1-seat class, 1 manager, 2 parents each with a competing ACTIVE enrollment."""
    from datetime import date, timedelta
    from auth import get_password_hash

    db = db_sessionmaker()
    suffix = os.urandom(4).hex()

    kg = models.Kindergarten(
        name_ar="روضة التنافس",
        name_en=f"Concurrency Test KG {suffix}",
        license_number=f"LIC-CONC-{suffix}",
        governorate="عمان",
        district="Amman",
        area="Jubeiha",
        address_line="1 Concurrent St",
        contact_phone="+962791111111",
        contact_email=f"conc_{suffix}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.flush()

    cls = models.Class(
        kindergarten_id=kg.id,
        name_ar="الصف المتنافس",
        name_en=f"Contested Class {suffix}",
        class_code=f"CONC-{suffix}",
        age_group="AGE_2_4",
        capacity_total=1,
        min_age_months=24,
        max_age_months=60,
        is_active=True,
    )
    db.add(cls)
    db.flush()

    manager = models.User(
        username=f"mgr_conc_{suffix}",
        email=f"mgr_conc_{suffix}@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        kindergarten_id=kg.id,
        status=models.UserStatus.ACTIVE,
    )
    db.add(manager)
    db.flush()

    enrollment_ids = []
    for idx in range(2):
        parent_user = models.User(
            username=f"parent_conc_{suffix}_{idx}",
            email=f"parent_conc_{suffix}_{idx}@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        db.add(parent_user)
        db.flush()

        profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name=f"Parent{idx}",
            last_name="Concurrent",
            phone_number=f"+96279200{idx:04d}",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id=f"9999{idx:06d}{suffix[:2]}",
            home_governorate="عمان",
            home_district="Amman",
            home_area="Jubeiha",
            home_address_line=f"{idx} Test St",
            correspondence_preference=True,
        )
        db.add(profile)
        db.flush()

        child = models.Child(
            parent_id=profile.id,
            first_name=f"Child{idx}",
            last_name="Concurrent",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - __import__("datetime").timedelta(days=900 + idx * 30),
            father_name=f"Father{idx}",
            mother_first_name="Mother",
            mother_last_name="Concurrent",
            mother_nationality="Jordanian",
            mother_national_id=f"8888{idx:06d}{suffix[:2]}",
        )
        db.add(child)
        db.flush()

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACTIVE,
            enrollment_start_date=date.today(),
            source="online",
        )
        db.add(enrollment)
        db.flush()
        enrollment_ids.append(enrollment.id)

    db.commit()

    yield {
        "class_id": cls.id,
        "kindergarten_id": kg.id,
        "manager_id": manager.id,
        "enrollment_ids": enrollment_ids,
    }

    # Teardown
    for eid in enrollment_ids:
        db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.id == eid
        ).delete(synchronize_session=False)
    db.query(models.Child).filter(models.Child.last_name == "Concurrent").delete(synchronize_session=False)
    db.query(models.ParentProfile).filter(models.ParentProfile.last_name == "Concurrent").delete(synchronize_session=False)
    db.query(models.User).filter(models.User.username.like(f"%_conc_{suffix}%")).delete(synchronize_session=False)
    db.query(models.Class).filter(models.Class.id == cls.id).delete(synchronize_session=False)
    db.query(models.Kindergarten).filter(models.Kindergarten.id == kg.id).delete(synchronize_session=False)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_concurrent_assign_class_only_one_succeeds(db_sessionmaker, seeded_scenario):
    """Two threads race for the single seat — exactly one must win.

    Backend used: {_BACKEND!r}.
    PostgreSQL: validated via SELECT ... FOR UPDATE row lock.
    SQLite WAL: validated via application-level capacity check (serialised writes).
    Both backends must produce: 1 success (200) and 1 rejection (409 or 400).
    """
    from fastapi import HTTPException
    from api.classes import assign_child_to_class

    class_id = seeded_scenario["class_id"]
    enrollment_ids = seeded_scenario["enrollment_ids"]
    manager_id = seeded_scenario["manager_id"]

    barrier = threading.Barrier(2)
    results = {}
    lock = threading.Lock()

    def worker(idx, enrollment_id):
        db = db_sessionmaker()
        try:
            manager = db.query(models.User).filter(models.User.id == manager_id).first()
            barrier.wait(timeout=10)
            try:
                assign_child_to_class(
                    enrollment_id=enrollment_id,
                    class_id=class_id,
                    current_user=manager,
                    db=db,
                )
                status_code = 200
            except HTTPException as exc:
                status_code = exc.status_code
        finally:
            db.close()
        with lock:
            results[idx] = status_code

    threads = [
        threading.Thread(target=worker, args=(i, eid))
        for i, eid in enumerate(enrollment_ids)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, f"Both threads must complete; got {results}"
    status_codes = list(results.values())
    assert status_codes.count(200) == 1, (
        f"Exactly 1 assignment must succeed under concurrent access "
        f"(backend={_BACKEND!r}), got: {status_codes}"
    )
    error_codes = [c for c in status_codes if c != 200]
    assert all(c in (400, 409) for c in error_codes), (
        f"Rejection must be 400 or 409, got: {error_codes}"
    )

    # Verify DB state
    verify_db = db_sessionmaker()
    try:
        assigned = (
            verify_db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.id.in_(enrollment_ids),
                models.EnrollmentApplication.class_id == class_id,
            )
            .count()
        )
        assert assigned == 1, (
            f"Exactly 1 enrollment must be assigned to class {class_id}, found {assigned}"
        )
    finally:
        verify_db.close()
