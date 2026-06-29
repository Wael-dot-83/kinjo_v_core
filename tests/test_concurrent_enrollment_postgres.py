"""tests/test_concurrent_enrollment_postgres.py — Real PostgreSQL row-lock concurrency test.

`tests/test_concurrent_enrollment.py` runs against SQLite + StaticPool, which serialises
every request onto a single connection. That test would still pass even if
`.with_for_update()` were deleted from `api/classes.py::assign_child_to_class` and
`api/enrollment.py::review_enrollment`, because SQLite never lets the two requests
actually overlap. It proves the *logical* capacity gate, not the *row-lock* fix.

This test opens two independent connections to a real PostgreSQL database and runs two
genuinely concurrent transactions (separate threads, separate Sessions, synchronised with
a `threading.Barrier` so both reach `.with_for_update()` at roughly the same instant)
against the actual production function `assign_child_to_class`. If `.with_for_update()`
is removed, this test becomes flaky/fails (both transactions can read the same stale
`enrolled_count` and both can succeed, double-booking the seat) — that is the point: a
SQLite-only suite cannot detect that regression, this test can.

Per project policy, SQLite test results are never accepted as proof of PostgreSQL
row-lock behavior — this file is the actual proof, gated behind a real PostgreSQL
instance.

SKIPPED unless POSTGRES_TEST_DATABASE_URL is set. No PostgreSQL server is available in
this sandboxed dev environment (no `psql`/`pg_isready` on PATH; the `db` host in
.env.example's DATABASE_URL is a Docker Compose service name that isn't running here),
so this test could not be executed as part of this audit — it is scaffolded and ready to
run wherever a real PostgreSQL instance is reachable (CI, staging, or a local `docker run
postgres`).

Usage:
    # 1. Point this at a throwaway PostgreSQL database with the app's schema migrated:
    #      alembic -x sqlalchemy.url=postgresql+psycopg2://user:pass@localhost:5432/kinjo_pg_test upgrade head
    # 2. Run:
    POSTGRES_TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/kinjo_pg_test \\
        pytest tests/test_concurrent_enrollment_postgres.py -v
"""
import os
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PG_URL = os.environ.get("POSTGRES_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason=(
        "POSTGRES_TEST_DATABASE_URL not set - no PostgreSQL server is available in this "
        "sandboxed environment to validate real row-level locking. Set this env var to a "
        "real, migrated PostgreSQL database to run this test (see module docstring)."
    ),
)


@pytest.fixture()
def pg_sessionmaker():
    engine = create_engine(PG_URL, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    yield Session
    engine.dispose()


@pytest.fixture()
def seeded_scenario(pg_sessionmaker):
    """Mirror tests/test_concurrent_enrollment.py's full_scenario, against real PostgreSQL.

    Capadistrict=1 class, one manager, two parents/children each with a SUBMITTED->ACCEPTED
    enrollment competing for the single seat. Rows are committed (visible to other
    connections/threads) then cleaned up in teardown.
    """
    from datetime import date, timedelta
    import models
    from auth import get_password_hash

    db = pg_sessionmaker()
    suffix = os.urandom(4).hex()

    kg = models.Kindergarten(
        name_ar="روضة التنافس PG",
        name_en=f"PG Competition KG {suffix}",
        license_number=f"LIC-PG-{suffix}",
        governorate="عمان",
        district="Amman",
        area="Jubeiha",
        address_line="1 Concurrent St",
        contact_phone="+962791111111",
        contact_email=f"conc_pg_{suffix}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.flush()

    cls = models.Class(
        kindergarten_id=kg.id,
        name_ar="الصف المتنافس PG",
        name_en="Contested Class PG",
        class_code=f"CONC-PG-{suffix}",
        age_group="AGE_2_4",
        capacity_total=1,
        min_age_months=24,
        max_age_months=60,
        is_active=True,
    )
    db.add(cls)
    db.flush()

    manager = models.User(
        username=f"concurrent_manager_pg_{suffix}",
        email=f"concurrent_manager_pg_{suffix}@test.com",
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
            username=f"parent_conc_pg_{suffix}_{idx}",
            email=f"parent_conc_pg_{suffix}_{idx}@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        db.add(parent_user)
        db.flush()

        profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name=f"Parent{idx}",
            last_name="ConcurrentPG",
            phone_number=f"+96279200000{idx}",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id=f"77777777{idx}{suffix[:2]}",
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
            last_name="ConcurrentPG",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=900 + idx * 30),
            father_name=f"Father{idx}",
            mother_first_name="Mother",
            mother_last_name="ConcurrentPG",
            mother_nationality="Jordanian",
            mother_national_id=f"6666666{idx}{suffix[:2]}",
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

    scenario = {
        "class_id": cls.id,
        "kindergarten_id": kg.id,
        "manager_id": manager.id,
        "enrollment_ids": enrollment_ids,
    }

    yield scenario

    # Teardown: best-effort cleanup, isolated by the random suffix above.
    db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.id.in_(enrollment_ids)
    ).delete(synchronize_session=False)
    db.query(models.Child).filter(models.Child.last_name == "ConcurrentPG").delete(synchronize_session=False)
    db.query(models.ParentProfile).filter(models.ParentProfile.last_name == "ConcurrentPG").delete(synchronize_session=False)
    db.query(models.User).filter(models.User.username.like(f"%_pg_{suffix}%")).delete(synchronize_session=False)
    db.query(models.Class).filter(models.Class.id == cls.id).delete(synchronize_session=False)
    db.query(models.Kindergarten).filter(models.Kindergarten.id == kg.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_concurrent_assign_class_only_one_succeeds_on_real_postgres(pg_sessionmaker, seeded_scenario):
    """Two real threads, two real PostgreSQL connections, racing for the same seat.

    Calls the actual `api/classes.py::assign_child_to_class` function directly (not via
    HTTP) so this exercises the real `.with_for_update()` code path under genuine
    concurrency. Exactly one of the two threads must succeed.
    """
    from fastapi import HTTPException
    import models
    from api.classes import assign_child_to_class

    class_id = seeded_scenario["class_id"]
    enrollment_ids = seeded_scenario["enrollment_ids"]
    manager_id = seeded_scenario["manager_id"]

    barrier = threading.Barrier(2)
    results = {}
    lock = threading.Lock()

    def worker(idx, enrollment_id):
        db = pg_sessionmaker()
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
            with lock:
                results[idx] = status_code
        finally:
            db.close()

    threads = [
        threading.Thread(target=worker, args=(idx, eid))
        for idx, eid in enumerate(enrollment_ids)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, f"Both threads must complete, got: {results}"
    status_codes = list(results.values())
    assert status_codes.count(200) == 1, (
        f"Expected exactly 1 successful assignment under real PostgreSQL row locking, "
        f"got: {status_codes}. If this fails intermittently, suspect .with_for_update() "
        f"was removed or weakened on the Class row query in api/classes.py."
    )
    assert status_codes.count(400) == 1, f"Expected exactly 1 capacity-full rejection, got: {status_codes}"

    verify_db = pg_sessionmaker()
    try:
        assigned = (
            verify_db.query(models.EnrollmentApplication)
            .filter(
                models.EnrollmentApplication.id.in_(enrollment_ids),
                models.EnrollmentApplication.class_id == class_id,
            )
            .count()
        )
        assert assigned == 1, f"Expected exactly 1 enrollment assigned to class {class_id}, found {assigned}"
    finally:
        verify_db.close()
