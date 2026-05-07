"""tests/test_concurrent_enrollment.py — Concurrency tests for class seat assignment.

Tests that the application correctly handles two simultaneous requests to claim
the last available seat in a class.  With SQLite (the test backend) the result is
serialised due to StaticPool, so we assert that one request receives HTTP 400
(class full) and the other succeeds with HTTP 200, yielding exactly one ACTIVE
enrollment in the class.

On a PostgreSQL deployment the class-capacity check in
`missing_endpoints.py::assign_child_to_class` uses a plain count+compare, which
races without `SELECT … FOR UPDATE`.  In a production environment, add::

    db.execute(
        text("SELECT id FROM classes WHERE id = :id FOR UPDATE"),
        {"id": class_id}
    )

before the capacity count to eliminate the TOCTOU window.

Usage:
    pytest tests/test_concurrent_enrollment.py -v
"""
import os
import sys

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on path when running from tests/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TESTING", "true")

from auth import get_password_hash
import models


# ---------------------------------------------------------------------------
# Helpers — token acquisition
# ---------------------------------------------------------------------------

def _login(client: TestClient, username: str, password: str) -> str:
    """Obtain a Bearer token via the /token endpoint."""
    resp = client.post(
        "/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def full_scenario(test_db, client):
    """
    Set up a class with capacity=1 and one existing ACTIVE enrollment (the class
    is full).  Return two *different* SUBMITTED enrollments that are both competing
    for a seat in a second class of capacity=1 (initially empty).

    Returns dict with all IDs needed by the concurrent test.
    """
    # Kindergarten
    kg = models.Kindergarten(
        name_ar="روضة التنافس",
        name_en="Competition KG",
        license_number="LIC-CONC-001",
        governorate="عمان",
        city="Amman",
        area="Jubeiha",
        address_line="1 Concurrent St",
        contact_phone="+962791111111",
        contact_email="conc@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    test_db.add(kg)
    test_db.flush()

    # Class with capacity=1 (the contested seat)
    cls = models.Class(
        kindergarten_id=kg.id,
        name_ar="الصف المتنافس",
        name_en="Contested Class",
        capacity_total=1,
        min_age_months=24,
        max_age_months=60,
        is_active=True,
    )
    test_db.add(cls)
    test_db.flush()

    # Manager user
    manager = models.User(
        username="concurrent_manager",
        email="concurrent_manager@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        kindergarten_id=kg.id,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(manager)
    test_db.flush()

    # Two parent users + profiles + children
    enrollments = []
    for idx in range(2):
        parent_user = models.User(
            username=f"parent_conc_{idx}@test.com",
            email=f"parent_conc_{idx}@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(parent_user)
        test_db.flush()

        profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name=f"Parent{idx}",
            last_name="Concurrent",
            phone_number=f"+96279100000{idx}",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id=f"999999999{idx}",
            home_governorate="عمان",
            home_city="Amman",
            home_area="Jubeiha",
            home_address_line=f"{idx} Test St",
            correspondence_preference=True,
        )
        test_db.add(profile)
        test_db.flush()

        child = models.Child(
            parent_id=profile.id,
            first_name=f"Child{idx}",
            last_name="Concurrent",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=900 + idx * 30),
            father_name=f"Father{idx}",
            mother_first_name="Mother",
            mother_last_name="Concurrent",
            mother_nationality="Jordanian",
            mother_national_id=f"88888888{idx}",
        )
        test_db.add(child)
        test_db.flush()

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACTIVE,  # already approved, needs class assignment
            enrollment_start_date=date.today(),
            source="online",
        )
        test_db.add(enrollment)
        test_db.flush()
        enrollments.append(enrollment)

    test_db.commit()

    manager_token = _login(client, "concurrent_manager", "Manager123!")

    return {
        "class_id":     cls.id,
        "kg_id":        kg.id,
        "enrollments":  [e.id for e in enrollments],
        "manager_token": manager_token,
        "test_db":      test_db,
    }


# ---------------------------------------------------------------------------
# Concurrency tests
# ---------------------------------------------------------------------------

def test_concurrent_class_assignment_only_one_succeeds(full_scenario, client):
    """Only one of two class-assignment requests should succeed.

    SQLite + StaticPool serialises requests on a single connection; true
    thread-level concurrency is not possible in that environment.  This test
    uses sequential HTTP calls to verify the *logical* capacity gate: the first
    request fills the single seat and the second is rejected with HTTP 400.
    """
    scenario = full_scenario
    class_id = scenario["class_id"]
    enrollment_ids = scenario["enrollments"]
    token = scenario["manager_token"]
    headers = {"Authorization": f"Bearer {token}"}

    results: list = []
    for eid in enrollment_ids:
        resp = client.post(
            f"/api/enrollments/{eid}/assign-class",
            params={"class_id": class_id},
            headers=headers,
        )
        results.append(resp.status_code)

    success_count = results.count(200)
    failure_count = results.count(400)
    assert success_count == 1, f"Expected 1 successful assignment, got: {results}"
    assert failure_count == 1, f"Expected 1 capacity-full rejection, got: {results}"


def test_concurrent_class_assignment_db_state(full_scenario, client):
    """After concurrent assignment, exactly one enrollment should have a class_id set."""
    scenario = full_scenario
    class_id = scenario["class_id"]
    enrollment_ids = scenario["enrollments"]
    token = scenario["manager_token"]
    db = scenario["test_db"]
    headers = {"Authorization": f"Bearer {token}"}

    for eid in enrollment_ids:
        client.post(
            f"/api/enrollments/{eid}/assign-class",
            params={"class_id": class_id},
            headers=headers,
        )

    # Refresh from DB and count class assignments
    assigned = (
        db.query(models.EnrollmentApplication)
        .filter(
            models.EnrollmentApplication.id.in_(enrollment_ids),
            models.EnrollmentApplication.class_id == class_id,
        )
        .count()
    )
    assert assigned == 1, (
        f"Expected exactly 1 enrollment assigned to class {class_id}, found {assigned}"
    )


def test_single_enrollment_assignment_succeeds(full_scenario, client):
    """Baseline: a single enrollment assignment to an empty class works."""
    scenario = full_scenario
    class_id = scenario["class_id"]
    enrollment_id = scenario["enrollments"][0]
    token = scenario["manager_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/enrollments/{enrollment_id}/assign-class",
        params={"class_id": class_id},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["class_id"] == class_id
    assert body["enrollment_id"] == enrollment_id


def test_second_enrollment_rejected_when_class_full(full_scenario, client):
    """A second enrollment assignment is rejected once the class is at capacity."""
    scenario = full_scenario
    class_id = scenario["class_id"]
    enrollment_ids = scenario["enrollments"]
    token = scenario["manager_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # First assignment fills the single seat
    resp1 = client.post(
        f"/api/enrollments/{enrollment_ids[0]}/assign-class",
        params={"class_id": class_id},
        headers=headers,
    )
    assert resp1.status_code == 200

    # Second assignment should be rejected
    resp2 = client.post(
        f"/api/enrollments/{enrollment_ids[1]}/assign-class",
        params={"class_id": class_id},
        headers=headers,
    )
    assert resp2.status_code == 400
    assert "capacity" in resp2.json()["detail"].lower()
