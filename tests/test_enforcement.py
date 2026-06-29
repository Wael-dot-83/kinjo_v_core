"""
Enforcement tests — verify that Jordanian regulatory compliance rules
are enforced by the API and validators.

Tests cover:
  1. Password policy enforcement (registration)
  2. Jordanian identity validation (national_id vs passport)
  3. Phone number validation
  4. Governorate validation
  5. Enrollment rejection mandatory reason
  6. Enrollment review audit trail
  7. Attendance check-in audit trail
  8. Attendance check-out audit trail
  9. Daily report 4:00 PM deadline enforcement
  10. Child age boundary enforcement
"""
import pytest
import secrets
from datetime import date, datetime, timedelta, time
from unittest.mock import patch

import models
from auth import get_password_hash
from validators import (
    validate_password_policy,
    validate_identity_by_nationality,
    validate_jordan_phone,
    validate_jordan_governorate,
    validate_child_age_strict,
    ValidationError,
)


# ──────────────────────────────────────────────────────────────────
# Helper: build valid parent registration payload
# ──────────────────────────────────────────────────────────────────

def _valid_parent_payload(overrides=None):
    data = {
        "first_name": "أحمد",
        "last_name": "الصالح",
        "phone_number": "+962791234567",
        "gender": "male",
        "nationality": "Jordanian",
        "national_id": "1234567890",
        "home_governorate": "Amman",
        "home_district": "Amman",
        "home_area": "Abdoun",
        "home_address_line": "123 Main St",
        "email": f"parent_{secrets.token_hex(4)}@test.com",
        "password": "Str0ng!Pass",
    }
    if overrides:
        data.update(overrides)
    return data


# ══════════════════════════════════════════════════════════════════
# 1. Password Policy (validator-level)
# ══════════════════════════════════════════════════════════════════

class TestPasswordPolicy:
    def test_weak_password_too_short(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_password_policy("Ab1!")
        assert "8" in exc_info.value.message  # mentions minimum length

    def test_no_uppercase(self):
        with pytest.raises(ValidationError):
            validate_password_policy("abcdefg1!")

    def test_no_lowercase(self):
        with pytest.raises(ValidationError):
            validate_password_policy("ABCDEFG1!")

    def test_no_digit(self):
        with pytest.raises(ValidationError):
            validate_password_policy("Abcdefgh!")

    def test_no_special_char(self):
        with pytest.raises(ValidationError):
            validate_password_policy("Abcdefg1")

    def test_valid_password_accepted(self):
        # Should not raise
        validate_password_policy("Str0ng!Pass")


# ══════════════════════════════════════════════════════════════════
# 2. Identity Validation (validator-level)
# ══════════════════════════════════════════════════════════════════

class TestIdentityValidation:
    def test_jordanian_without_national_id_rejected(self):
        with pytest.raises(ValidationError):
            validate_identity_by_nationality("Jordanian", None, None)

    def test_jordanian_with_national_id_accepted(self):
        validate_identity_by_nationality("Jordanian", "1234567890", None)

    def test_non_jordanian_without_passport_rejected(self):
        with pytest.raises(ValidationError):
            validate_identity_by_nationality("Syrian", None, None)

    def test_non_jordanian_with_passport_accepted(self):
        validate_identity_by_nationality("Syrian", None, "P123456")


# ══════════════════════════════════════════════════════════════════
# 3. Phone Validation
# ══════════════════════════════════════════════════════════════════

class TestPhoneValidation:
    def test_valid_jordanian_phone(self):
        assert validate_jordan_phone("+962791234567") is True

    def test_invalid_phone(self):
        assert validate_jordan_phone("1234567890") is False


# ══════════════════════════════════════════════════════════════════
# 4. Governorate Validation
# ══════════════════════════════════════════════════════════════════

class TestGovernorateValidation:
    def test_valid_governorate(self):
        result = validate_jordan_governorate("Amman")
        assert result in ("عمان", "Amman")  # Canonical name

    def test_invalid_governorate(self):
        with pytest.raises(ValidationError):
            validate_jordan_governorate("Narnia")


# ══════════════════════════════════════════════════════════════════
# 5. Parent Registration API — Password Rejected
# ══════════════════════════════════════════════════════════════════

class TestParentRegistrationEnforcement:
    def test_register_weak_password_rejected(self, client):
        payload = _valid_parent_payload({"password": "weak"})
        resp = client.post("/api/register/parent", json=payload)
        assert resp.status_code in (400, 422)

    def test_register_valid_password_accepted(self, client):
        payload = _valid_parent_payload()
        resp = client.post("/api/register/parent", json=payload)
        assert resp.status_code == 201

    def test_register_jordanian_no_id_rejected(self, client):
        payload = _valid_parent_payload({
            "nationality": "Jordanian",
            "national_id": None,
        })
        resp = client.post("/api/register/parent", json=payload)
        assert resp.status_code in (400, 422)

    def test_register_non_jordanian_with_passport_accepted(self, client):
        payload = _valid_parent_payload({
            "nationality": "Egyptian",
            "national_id": None,
            "passport_number": "EGP123456",
        })
        resp = client.post("/api/register/parent", json=payload)
        assert resp.status_code == 201

    def test_register_invalid_governorate_rejected(self, client):
        payload = _valid_parent_payload({"home_governorate": "InvalidCity"})
        resp = client.post("/api/register/parent", json=payload)
        assert resp.status_code in (400, 422)

    def test_register_creates_audit_trail(self, client, test_db):
        payload = _valid_parent_payload()
        resp = client.post("/api/register/parent", json=payload)
        assert resp.status_code == 201

        audit = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "REGISTER"
        ).first()
        assert audit is not None


# ══════════════════════════════════════════════════════════════════
# 6. Enrollment Review — Mandatory Rejection Reason
# ══════════════════════════════════════════════════════════════════

class TestEnrollmentReviewEnforcement:
    @pytest.fixture
    def pending_enrollment(self, test_db, sample_child, sample_kindergarten, sample_class, manager_user):
        enrollment = models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.SUBMITTED,
        )
        test_db.add(enrollment)
        test_db.flush()
        # Add required documents so acceptance isn't blocked by document check
        for doc_type in ("birth_certificate", "health_certificate"):
            doc = models.ChildDocument(
                child_id=sample_child.id,
                document_type=doc_type,
                file_name=f"{doc_type}.pdf",
                file_path=f"/fake/{doc_type}.pdf",
                uploaded_by=manager_user.id,
            )
            test_db.add(doc)
        test_db.commit()
        test_db.refresh(enrollment)
        return enrollment

    def test_reject_without_reason_fails(
        self, client, auth_headers_manager, pending_enrollment
    ):
        resp = client.post(
            f"/api/enrollment/{pending_enrollment.id}/review?decision=reject",
            headers=auth_headers_manager,
        )
        assert resp.status_code == 400
        assert "Rejection reason is required" in resp.json().get("detail", "")

    def test_reject_with_reason_succeeds(
        self, client, auth_headers_manager, pending_enrollment
    ):
        resp = client.post(
            f"/api/enrollment/{pending_enrollment.id}/review?decision=reject&reason=عمر+الطفل+غير+مناسب",
            headers=auth_headers_manager,
        )
        assert resp.status_code == 200

    def test_accept_creates_audit_trail(
        self, client, auth_headers_manager, pending_enrollment, test_db
    ):
        resp = client.post(
            f"/api/enrollment/{pending_enrollment.id}/review?decision=accept",
            headers=auth_headers_manager,
        )
        assert resp.status_code == 200

        audit = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "ACCEPT"
        ).first()
        assert audit is not None


# ══════════════════════════════════════════════════════════════════
# 7 & 8. Attendance Audit Trails
# ══════════════════════════════════════════════════════════════════

class TestAttendanceAudit:
    @pytest.fixture
    def _setup_attendance(
        self, test_db, supervisor_user, sample_child,
        sample_kindergarten, sample_class
    ):
        """Give the supervisor a profile + active enrollment for the child."""
        # Supervisor profile
        sup_profile = test_db.query(models.SupervisorProfile).filter(
            models.SupervisorProfile.user_id == supervisor_user.id
        ).first()
        if not sup_profile:
            sup_profile = models.SupervisorProfile(
                user_id=supervisor_user.id,
                kindergarten_id=sample_kindergarten.id,
            )
            test_db.add(sup_profile)
            test_db.commit()
            test_db.refresh(sup_profile)

        # Assign supervisor to class
        existing = test_db.query(models.SupervisorAssignment).filter(
            models.SupervisorAssignment.supervisor_id == supervisor_user.id,
            models.SupervisorAssignment.class_id == sample_class.id,
        ).first()
        if not existing:
            assignment = models.SupervisorAssignment(
                supervisor_id=supervisor_user.id,
                class_id=sample_class.id,
                start_date=date.today(),
            )
            test_db.add(assignment)
            test_db.commit()

        # Active enrollment
        enrollment = test_db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == sample_child.id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        ).first()
        if not enrollment:
            enrollment = models.EnrollmentApplication(
                child_id=sample_child.id,
                kindergarten_id=sample_kindergarten.id,
                class_id=sample_class.id,
                status=models.EnrollmentStatus.ACTIVE,
            )
            test_db.add(enrollment)
            test_db.commit()
            test_db.refresh(enrollment)
        return enrollment

    def test_check_in_creates_audit(
        self, client, auth_headers_supervisor, sample_child,
        test_db, _setup_attendance
    ):
        resp = client.post(
            f"/api/attendance/check-in?child_id={sample_child.id}&method=manual",
            headers=auth_headers_supervisor,
        )
        assert resp.status_code == 200

        audit = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "ATTENDANCE_CHECK_IN"
        ).first()
        assert audit is not None

    def test_check_out_creates_audit(
        self, client, auth_headers_supervisor, sample_child,
        test_db, _setup_attendance
    ):
        # First check in
        client.post(
            f"/api/attendance/check-in?child_id={sample_child.id}&method=manual",
            headers=auth_headers_supervisor,
        )
        # Then check out
        resp = client.post(
            f"/api/attendance/check-out?child_id={sample_child.id}",
            headers=auth_headers_supervisor,
        )
        assert resp.status_code == 200

        audit = test_db.query(models.AuditLog).filter(
            models.AuditLog.action == "ATTENDANCE_CHECK_OUT"
        ).first()
        assert audit is not None


# ══════════════════════════════════════════════════════════════════
# 9. Child Age Boundary Enforcement
# ══════════════════════════════════════════════════════════════════

class TestChildAgeBoundary:
    def test_child_too_young_rejected(self):
        """Child under 1 day old (born today) should be rejected."""
        dob = date.today()  # 0 days old — born today, not yet 1 day
        with pytest.raises(ValidationError):
            validate_child_age_strict(dob)

    def test_child_too_old_rejected(self):
        """Child over 56 months should be rejected."""
        dob = date.today() - timedelta(days=57 * 30)  # ~57 months
        with pytest.raises(ValidationError):
            validate_child_age_strict(dob)

    def test_child_in_range_accepted(self):
        """Child of 3 years old should be accepted."""
        dob = date.today() - timedelta(days=365 * 3)
        validate_child_age_strict(dob)
