"""Regression tests for the /api/enrollments tab-badge contract.

templates/enrollment/list.html drives its status tab badges (All / Pending /
Accepted / Rejected / Waitlist) from a ``status_counts`` object keyed by the
UPPERCASE EnrollmentStatus enum value. Those counts must:

* be present on the list response,
* be keyed by the uppercase enum value (the client looks up
  ``status_counts.PENDING_REVIEW`` etc.),
* reflect every status regardless of the active ``status`` filter (so each tab
  shows its true total, not the filtered total).

Before the fix the response had no per-status counts, so the four non-"All"
badges were permanently 0.
"""

from datetime import date

import models
from main import app
from dependencies import get_current_user


def _seed_two_enrollments(test_db, kindergarten_id, statuses):
    """Create a parent → child → enrollment chain per status in the given KG."""
    parent_user = models.User(
        username="sc_parent",
        email="sc_parent@test.com",
        hashed_password="x",
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(parent_user)
    test_db.commit()
    test_db.refresh(parent_user)
    profile = models.ParentProfile(
        user_id=parent_user.id,
        first_name="SC",
        last_name="Parent",
        phone_number="+962799000099",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        national_id="SCPARENT099",
        home_governorate="Amman",
        home_district="Amman",
        home_area="Test",
        home_address_line="Test",
    )
    test_db.add(profile)
    test_db.commit()
    test_db.refresh(profile)
    for i, st in enumerate(statuses):
        child = models.Child(
            parent_id=profile.id,
            first_name=f"SCChild{i}",
            last_name="Test",
            gender=models.Gender.MALE,
            date_of_birth=date(2024, 3, 1),
            father_name="Father SC",
            mother_first_name="Mother",
            mother_last_name="SC",
            mother_nationality="Jordanian",
            mother_national_id=f"SCM{i}099",
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)
        test_db.add(
            models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=kindergarten_id,
                status=st,
            )
        )
    test_db.commit()


def test_list_returns_status_counts_keyed_uppercase(client, test_db, manager_user):
    _seed_two_enrollments(
        test_db,
        manager_user.kindergarten_id,
        [models.EnrollmentStatus.PENDING_REVIEW, models.EnrollmentStatus.ACTIVE],
    )
    app.dependency_overrides[get_current_user] = lambda: manager_user
    try:
        resp = client.get("/api/enrollments")
        assert resp.status_code == 200
        body = resp.json()
        assert "status_counts" in body
        counts = body["status_counts"]
        # keyed by the UPPERCASE enum value the front-end looks up
        assert counts.get("PENDING_REVIEW") == 1
        assert counts.get("ACTIVE") == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_status_counts_unaffected_by_status_filter(client, test_db, manager_user):
    _seed_two_enrollments(
        test_db,
        manager_user.kindergarten_id,
        [models.EnrollmentStatus.PENDING_REVIEW, models.EnrollmentStatus.ACTIVE],
    )
    app.dependency_overrides[get_current_user] = lambda: manager_user
    try:
        resp = client.get("/api/enrollments?status=active")
        assert resp.status_code == 200
        body = resp.json()
        # the list is filtered ...
        assert [e["status"] for e in body["enrollments"]] == ["ACTIVE"]
        # ... but the badges still reflect every status
        assert body["status_counts"].get("PENDING_REVIEW") == 1
        assert body["status_counts"].get("ACTIVE") == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)
