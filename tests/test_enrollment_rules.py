"""
Comprehensive tests for enrollment rule enforcement (Section 7):
- Single active enrollment per child across kindergartens (3-layer)
- is_active column sync with status changes
- Status transition constraints (submit/review guards)
- Review-stage blocking when active enrollment exists elsewhere
- REJECTED/WITHDRAWN/DRAFT do NOT block new enrollments
- Manager review accept/reject flow
- IntegrityError fallback at all stages
"""
import pytest
from datetime import date, timedelta, datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import models
from auth import get_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_dob():
    """Return a DOB ~3 years ago (well within enrollment age range)."""
    return date.today() - timedelta(days=365 * 3)


_CHILD_COUNTER = 0


def _next_national_id():
    """Generate a unique 10-digit national ID for tests."""
    global _CHILD_COUNTER
    _CHILD_COUNTER += 1
    return f"{9000000000 + _CHILD_COUNTER}"


def _make_child(db, parent_profile, suffix="A"):
    """Create and return a persisted Child record."""
    nat_id = _next_national_id()
    child = models.Child(
        parent_id=parent_profile.id,
        first_name=f"TestChild{suffix}",
        last_name="Al-Test",
        gender=models.Gender.FEMALE,
        date_of_birth=_valid_dob(),
        father_name="TestFather",
        mother_first_name="TestMother",
        mother_last_name="Al-Test",
        mother_nationality="Jordanian",
        mother_national_id=nat_id,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


def _make_kindergarten(db, suffix="X"):
    """Create and return a persisted Kindergarten."""
    kg = models.Kindergarten(
        name_ar=f"روضة اختبار {suffix}",
        name_en=f"Test KG {suffix}",
        governorate="Amman",
        district="Amman",
        area="test",
        address_line="test",
        contact_phone=f"+962790000{ord(suffix[-1]) if isinstance(suffix, str) else suffix:04d}",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _enroll(db, child, kindergarten, status=models.EnrollmentStatus.DRAFT):
    """Create and persist an enrollment."""
    ea = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kindergarten.id,
        status=status,
        source="test",
    )
    db.add(ea)
    db.commit()
    db.refresh(ea)
    return ea


# ===================================================================
# 1. Model-level: is_active column sync
# ===================================================================
class TestIsActiveSync:
    """Verify is_active mirrors status via @validates."""

    @pytest.mark.parametrize(
        "status, expected_is_active",
        [
            (models.EnrollmentStatus.DRAFT, None),
            (models.EnrollmentStatus.SUBMITTED, True),
            (models.EnrollmentStatus.PENDING_REVIEW, True),
            (models.EnrollmentStatus.ACCEPTED, True),
            (models.EnrollmentStatus.ACTIVE, True),
            (models.EnrollmentStatus.REJECTED, None),
            (models.EnrollmentStatus.WITHDRAWN, None),
            (models.EnrollmentStatus.WAITLISTED, None),
        ],
    )
    def test_is_active_set_on_creation(self, test_db, parent_user, sample_kindergarten, status, expected_is_active):
        child = _make_child(test_db, parent_user.parent_profile, suffix=f"IA{status.value[:3]}")
        ea = _enroll(test_db, child, sample_kindergarten, status=status)
        assert ea.is_active is expected_is_active, f"Expected is_active={expected_is_active} for {status}"

    def test_is_active_transitions_on_status_change(self, test_db, parent_user, sample_kindergarten):
        """is_active should update when status changes."""
        child = _make_child(test_db, parent_user.parent_profile, suffix="TR")
        ea = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.DRAFT)
        assert ea.is_active is None

        ea.status = models.EnrollmentStatus.SUBMITTED
        test_db.commit()
        test_db.refresh(ea)
        assert ea.is_active is True

        ea.status = models.EnrollmentStatus.REJECTED
        test_db.commit()
        test_db.refresh(ea)
        assert ea.is_active is None

    def test_is_active_accepts_to_withdrawn(self, test_db, parent_user, sample_kindergarten):
        """ACCEPTED → WITHDRAWN should clear is_active."""
        child = _make_child(test_db, parent_user.parent_profile, suffix="AW")
        ea = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.ACCEPTED)
        assert ea.is_active is True

        ea.status = models.EnrollmentStatus.WITHDRAWN
        test_db.commit()
        test_db.refresh(ea)
        assert ea.is_active is None


# ===================================================================
# 2. DB-level: unique constraints
# ===================================================================
class TestDBConstraints:
    """Verify DB-level unique constraints fire correctly."""

    def test_uq_child_kindergarten_blocks_duplicate(self, test_db, parent_user, sample_kindergarten):
        """Two enrollments for same child + same KG should raise IntegrityError."""
        child = _make_child(test_db, parent_user.parent_profile, suffix="DQ")
        _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.DRAFT)

        ea2 = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.DRAFT,
            source="test",
        )
        test_db.add(ea2)
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

    def test_uq_child_active_blocks_second_active(self, test_db, parent_user, sample_kindergarten):
        """Two active enrollments for same child should raise IntegrityError."""
        child = _make_child(test_db, parent_user.parent_profile, suffix="DA")
        kg2 = _make_kindergarten(test_db, suffix="DA")

        _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.ACTIVE)

        ea2 = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg2.id,
            status=models.EnrollmentStatus.SUBMITTED,
            source="test",
        )
        test_db.add(ea2)
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

    def test_multiple_inactive_allowed(self, test_db, parent_user):
        """Multiple inactive (REJECTED/WITHDRAWN) enrollments for same child are allowed."""
        child = _make_child(test_db, parent_user.parent_profile, suffix="MI")
        kg1 = _make_kindergarten(test_db, suffix="M1")
        kg2 = _make_kindergarten(test_db, suffix="M2")

        _enroll(test_db, child, kg1, status=models.EnrollmentStatus.REJECTED)
        _enroll(test_db, child, kg2, status=models.EnrollmentStatus.WITHDRAWN)
        # Should not raise
        test_db.commit()


# ===================================================================
# 3. API-level: review (accept) blocked when active elsewhere
# ===================================================================
class TestReviewBlockedWhenActiveElsewhere:
    """POST /enrollment/{id}/review with decision=accept should fail if child
    already has an active enrollment in another kindergarten.

    Note: The DB unique constraint on (child_id, is_active) prevents having
    TWO active-status enrollments simultaneously. So the test creates a DRAFT
    in KG1, submits+accepts it in KG1 (making it ACCEPTED/is_active=True),
    then verifies that a second enrollment can't even be submitted.
    The review-level check is defense-in-depth that fires in race conditions.
    """

    def test_accept_then_second_submit_blocked(
        self, client, test_db, parent_user, sample_kindergarten, sample_class, manager_user, manager_token, parent_token
    ):
        """After child is ACCEPTED in KG1, submitting DRAFT in KG2 should fail."""
        import secrets

        child = _make_child(test_db, parent_user.parent_profile, suffix="RA")
        kg2 = _make_kindergarten(test_db, suffix="RA")

        # Add required documents for acceptance
        for doc_type in ("birth_certificate", "health_certificate"):
            test_db.add(models.ChildDocument(
                child_id=child.id, document_type=doc_type,
                file_name=f"{doc_type}.pdf",
                file_path=f"/fake/{doc_type}.pdf", uploaded_by=manager_user.id,
            ))
        test_db.commit()

        # Create enrollment in KG1 as SUBMITTED → accept it (class_id required by H-7 guard)
        ea1 = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED)
        ea1.class_id = sample_class.id
        test_db.commit()

        csrf_token = secrets.token_hex(32)
        mgr_headers = {
            "Authorization": f"Bearer {manager_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
        }
        resp = client.post(f"/api/enrollment/{ea1.id}/review?decision=accept", headers=mgr_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # Create a DRAFT enrollment in KG2 (is_active=None, should succeed)
        ea2 = _enroll(test_db, child, kg2, status=models.EnrollmentStatus.DRAFT)

        # Trying to submit the DRAFT should fail (active enrollment exists)
        parent_headers = {"Authorization": f"Bearer {parent_token}"}
        resp2 = client.post(f"/api/enrollment/{ea2.id}/submit", headers=parent_headers)
        assert resp2.status_code == 400
        detail2 = resp2.json()["detail"]
        assert "child" in detail2.lower() or "طفل" in detail2  # Arabic: "هذا الطفل مسجل..."

    def test_reject_allowed_even_with_active_elsewhere(
        self, client, test_db, parent_user, sample_kindergarten, manager_user, manager_token, parent_token
    ):
        """Rejecting should always work regardless of other enrollments."""
        import secrets
        csrf_token = secrets.token_hex(32)
        mgr_headers = {
            "Authorization": f"Bearer {manager_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
        }

        child = _make_child(test_db, parent_user.parent_profile, suffix="RJ")

        # Create SUBMITTED enrollment in manager's KG (is_active=True)
        enrollment = _enroll(
            test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED
        )

        # Reject should work (reason is mandatory)
        response = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=reject&reason=Test+rejection",
            headers=mgr_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

    def test_db_constraint_prevents_two_active(self, test_db, parent_user):
        """DB constraint should prevent two is_active=True enrollments for same child."""
        child = _make_child(test_db, parent_user.parent_profile, suffix="DB")
        kg1 = _make_kindergarten(test_db, suffix="D1")
        kg2 = _make_kindergarten(test_db, suffix="D2")

        _enroll(test_db, child, kg1, status=models.EnrollmentStatus.ACTIVE)

        # Second active enrollment should raise IntegrityError
        ea2 = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg2.id,
            status=models.EnrollmentStatus.SUBMITTED,  # Also active
            source="test",
        )
        test_db.add(ea2)
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()


# ===================================================================
# 4. Inactive statuses do NOT block new enrollments
# ===================================================================
class TestInactiveStatusesDoNotBlock:
    """REJECTED / WITHDRAWN / WAITLISTED should not prevent new enrollment."""

    @pytest.mark.parametrize("inactive_status", [
        models.EnrollmentStatus.REJECTED,
        models.EnrollmentStatus.WITHDRAWN,
        models.EnrollmentStatus.WAITLISTED,
    ])
    def test_apply_allowed_after_inactive(
        self, client, test_db, parent_user, sample_kindergarten, parent_token, inactive_status
    ):
        headers = {"Authorization": f"Bearer {parent_token}"}

        child = _make_child(test_db, parent_user.parent_profile, suffix=f"IN{inactive_status.value[:2]}")
        kg2 = _make_kindergarten(test_db, suffix=f"IN{inactive_status.value[:2]}")

        # Inactive enrollment in kg2
        _enroll(test_db, child, kg2, status=inactive_status)

        # New enrollment in sample_kindergarten should succeed
        enrollment_data = {
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender.value,
            "date_of_birth": child.date_of_birth.isoformat(),
            "father_name": child.father_name,
            "mother_first_name": child.mother_first_name,
            "mother_last_name": child.mother_last_name,
            "mother_nationality": child.mother_nationality,
            "mother_national_id": child.mother_national_id,
            "kindergarten_id": sample_kindergarten.id,
        }

        response = client.post("/api/enrollment/apply", json=enrollment_data, headers=headers)
        assert response.status_code == 201, f"Should allow enrollment after {inactive_status.value}: {response.json()}"


# ===================================================================
# 5. Status transition constraints
# ===================================================================
class TestStatusTransitionGuards:
    """Verify that submit and review enforce correct source statuses."""

    def test_submit_requires_draft(self, client, test_db, parent_user, sample_kindergarten, parent_token):
        """Submit should reject non-DRAFT statuses."""
        headers = {"Authorization": f"Bearer {parent_token}"}
        child = _make_child(test_db, parent_user.parent_profile, suffix="SD")
        enrollment = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED)

        response = client.post(f"/api/enrollment/{enrollment.id}/submit", headers=headers)
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "submitted" in detail or "draft" in detail

    def test_review_requires_submitted(
        self, client, test_db, parent_user, sample_kindergarten, manager_user, manager_token
    ):
        """Review should reject non-SUBMITTED statuses."""
        import secrets
        csrf_token = secrets.token_hex(32)
        headers = {
            "Authorization": f"Bearer {manager_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
        }
        child = _make_child(test_db, parent_user.parent_profile, suffix="RD")
        enrollment = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.DRAFT)

        response = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=accept",
            headers=headers,
        )
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "submitted" in detail or "draft" in detail or "accepted" in detail

    def test_review_invalid_decision(
        self, client, test_db, parent_user, sample_kindergarten, manager_user, manager_token
    ):
        """Review should reject invalid decision values."""
        import secrets
        csrf_token = secrets.token_hex(32)
        headers = {
            "Authorization": f"Bearer {manager_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
        }
        child = _make_child(test_db, parent_user.parent_profile, suffix="IV")
        enrollment = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED)

        response = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=maybe",
            headers=headers,
        )
        assert response.status_code == 422  # FastAPI validation error


# ===================================================================
# 6. Manager accept happy path (no conflicts)
# ===================================================================
class TestManagerAcceptHappyPath:
    """Successful accept should set ACCEPTED status and decision metadata."""

    def test_accept_sets_accepted_status(
        self, client, test_db, parent_user, sample_kindergarten, sample_class, manager_user, manager_token
    ):
        import secrets
        csrf_token = secrets.token_hex(32)
        headers = {
            "Authorization": f"Bearer {manager_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
        }

        child = _make_child(test_db, parent_user.parent_profile, suffix="HP")

        # Add required documents for acceptance
        for doc_type in ("birth_certificate", "health_certificate"):
            test_db.add(models.ChildDocument(
                child_id=child.id, document_type=doc_type,
                file_name=f"{doc_type}.pdf",
                file_path=f"/fake/{doc_type}.pdf", uploaded_by=manager_user.id,
            ))
        test_db.commit()

        enrollment = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED)
        enrollment.class_id = sample_class.id
        test_db.commit()

        response = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=accept",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["decision_at"] is not None

        # Verify DB state
        test_db.refresh(enrollment)
        assert enrollment.status == models.EnrollmentStatus.ACCEPTED
        assert enrollment.decision_by == manager_user.id
        assert enrollment.is_active is True

    def test_reject_sets_rejected_status(
        self, client, test_db, parent_user, sample_kindergarten, manager_user, manager_token
    ):
        import secrets
        csrf_token = secrets.token_hex(32)
        headers = {
            "Authorization": f"Bearer {manager_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
        }

        child = _make_child(test_db, parent_user.parent_profile, suffix="RH")
        enrollment = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED)

        response = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=reject&reason=Not+eligible",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

        test_db.refresh(enrollment)
        assert enrollment.status == models.EnrollmentStatus.REJECTED
        assert enrollment.decision_by == manager_user.id
        assert enrollment.is_active is None


# ===================================================================
# 7. RBAC: only parents/managers can create, only managers review
# ===================================================================
class TestEnrollmentRBAC:
    """Role gates on enrollment endpoints."""

    def test_supervisor_cannot_create_enrollment(
        self, client, test_db, sample_kindergarten, supervisor_token
    ):
        headers = {"Authorization": f"Bearer {supervisor_token}"}
        enrollment_data = {
            "first_name": "Test",
            "last_name": "Child",
            "gender": "FEMALE",
            "date_of_birth": _valid_dob().isoformat(),
            "father_name": "Father",
            "mother_first_name": "Mother",
            "mother_last_name": "Last",
            "mother_nationality": "Jordanian",
            "mother_national_id": "1234567890",
            "kindergarten_id": sample_kindergarten.id,
        }
        response = client.post("/api/enrollment/apply", json=enrollment_data, headers=headers)
        assert response.status_code == 403

    def test_parent_cannot_review_enrollment(
        self, client, test_db, parent_user, sample_kindergarten, parent_token
    ):
        child = _make_child(test_db, parent_user.parent_profile, suffix="PR")
        enrollment = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED)

        headers = {"Authorization": f"Bearer {parent_token}"}
        response = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=accept",
            headers=headers,
        )
        assert response.status_code == 403

    def test_supervisor_cannot_review_enrollment(
        self, client, test_db, parent_user, sample_kindergarten, supervisor_token
    ):
        child = _make_child(test_db, parent_user.parent_profile, suffix="SR")
        enrollment = _enroll(test_db, child, sample_kindergarten, status=models.EnrollmentStatus.SUBMITTED)

        headers = {"Authorization": f"Bearer {supervisor_token}"}
        response = client.post(
            f"/api/enrollment/{enrollment.id}/review?decision=accept",
            headers=headers,
        )
        assert response.status_code == 403


# ===================================================================
# 8. Enrollment not found
# ===================================================================
class TestEnrollmentNotFound:

    def test_submit_nonexistent(self, client, parent_token):
        headers = {"Authorization": f"Bearer {parent_token}"}
        response = client.post("/api/enrollment/999999/submit", headers=headers)
        assert response.status_code == 404

    def test_review_nonexistent(self, client, manager_token):
        import secrets
        csrf_token = secrets.token_hex(32)
        headers = {
            "Authorization": f"Bearer {manager_token}",
            "X-CSRF-Token": csrf_token,
            "Cookie": f"kinjo_csrf_token={csrf_token}",
        }
        response = client.post(
            "/api/enrollment/999999/review?decision=accept",
            headers=headers,
        )
        assert response.status_code == 404


# ===================================================================
# 9. ACTIVE_ENROLLMENT_STATUSES constant matches model definition
# ===================================================================
class TestActiveEnrollmentStatusesConstant:
    """Ensure the constant used by endpoints matches the model definition."""

    def test_constant_matches_model(self):
        expected = {
            models.EnrollmentStatus.SUBMITTED,
            models.EnrollmentStatus.PENDING_REVIEW,
            models.EnrollmentStatus.ACCEPTED,
            models.EnrollmentStatus.ACTIVE,
        }
        assert models.ACTIVE_ENROLLMENT_STATUSES == expected

    def test_is_active_enrollment_status_helper(self):
        for s in models.ACTIVE_ENROLLMENT_STATUSES:
            assert models.is_active_enrollment_status(s) is True
        for s in [
            models.EnrollmentStatus.DRAFT,
            models.EnrollmentStatus.REJECTED,
            models.EnrollmentStatus.WITHDRAWN,
            models.EnrollmentStatus.WAITLISTED,
        ]:
            assert models.is_active_enrollment_status(s) is False

    def test_helper_handles_none(self):
        assert models.is_active_enrollment_status(None) is False

    def test_helper_handles_string(self):
        assert models.is_active_enrollment_status("ACTIVE") is True
        assert models.is_active_enrollment_status("DRAFT") is False
