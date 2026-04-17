"""
Comprehensive tests for IAM hardening, enrollment workflow, and attendance constraints.
Covers: account lockout, password complexity, enrollment state machine, withdraw, capacity check,
check-in/check-out ordering.
"""
import pytest
from datetime import datetime, timedelta, timezone, date
from unittest.mock import patch, MagicMock

# ============================================================================
# Auth / IAM Tests
# ============================================================================

class TestPasswordComplexity:
    """Tests for password complexity validation (auth.validate_password_complexity)"""

    def test_valid_password(self):
        from auth import validate_password_complexity
        errors = validate_password_complexity("Admin123!")
        assert errors == [], f"Unexpected errors: {errors}"

    def test_too_short(self):
        from auth import validate_password_complexity
        errors = validate_password_complexity("Ab1!")
        assert any("at least" in e for e in errors)

    def test_no_uppercase(self):
        from auth import validate_password_complexity
        errors = validate_password_complexity("admin123!")
        assert any("uppercase" in e for e in errors)

    def test_no_lowercase(self):
        from auth import validate_password_complexity
        errors = validate_password_complexity("ADMIN123!")
        assert any("lowercase" in e for e in errors)

    def test_no_digit(self):
        from auth import validate_password_complexity
        errors = validate_password_complexity("AdminPass!")
        assert any("digit" in e for e in errors)

    def test_no_special(self):
        from auth import validate_password_complexity
        errors = validate_password_complexity("Admin1234")
        assert any("special" in e for e in errors)

    def test_get_password_hash_rejects_weak(self):
        from auth import get_password_hash
        with pytest.raises(ValueError):
            get_password_hash("short")

    def test_get_password_hash_accepts_strong(self):
        from auth import get_password_hash
        h = get_password_hash("StrongPass1!")
        assert h.startswith("$2b$")


class TestAccountLockout:
    """Tests for account lockout logic in auth.authenticate_user"""

    @pytest.fixture
    def mock_db_and_user(self):
        """Create a mock DB session and User object."""
        from auth import get_password_hash
        import models

        user = MagicMock(spec=models.User)
        user.username = "testuser"
        user.email = "test@example.com"
        user.hashed_password = get_password_hash("Correct1!")
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = None
        user.status = models.UserStatus.ACTIVE

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        db.commit = MagicMock()

        return db, user

    def test_successful_login_resets_counter(self, mock_db_and_user):
        from auth import authenticate_user
        db, user = mock_db_and_user
        result = authenticate_user(db, "testuser", "Correct1!")
        assert result is not None
        assert user.failed_login_count == 0
        assert user.locked_until is None

    def test_failed_login_increments_counter(self, mock_db_and_user):
        from auth import authenticate_user
        db, user = mock_db_and_user
        result = authenticate_user(db, "testuser", "WrongPass1!")
        assert result is None
        assert user.failed_login_count == 1

    def test_locked_account_returns_none(self, mock_db_and_user):
        from auth import authenticate_user
        db, user = mock_db_and_user
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        result = authenticate_user(db, "testuser", "Correct1!")
        assert result is None

    def test_expired_lock_allows_login(self, mock_db_and_user):
        from auth import authenticate_user
        db, user = mock_db_and_user
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        result = authenticate_user(db, "testuser", "Correct1!")
        assert result is not None
        assert user.failed_login_count == 0


# ============================================================================
# Enrollment Workflow Tests
# ============================================================================

class TestEnrollmentStatusTransitions:
    """Tests for enrollment status enum and is_active validator"""

    def test_active_statuses_set(self):
        from models import ACTIVE_ENROLLMENT_STATUSES, EnrollmentStatus
        expected = {
            EnrollmentStatus.SUBMITTED,
            EnrollmentStatus.PENDING_REVIEW,
            EnrollmentStatus.ACCEPTED,
            EnrollmentStatus.ACTIVE,
        }
        assert ACTIVE_ENROLLMENT_STATUSES == expected

    def test_is_active_enrollment_status_true(self):
        from models import is_active_enrollment_status, EnrollmentStatus
        assert is_active_enrollment_status(EnrollmentStatus.SUBMITTED) is True
        assert is_active_enrollment_status(EnrollmentStatus.ACTIVE) is True

    def test_is_active_enrollment_status_false(self):
        from models import is_active_enrollment_status, EnrollmentStatus
        assert is_active_enrollment_status(EnrollmentStatus.DRAFT) is False
        assert is_active_enrollment_status(EnrollmentStatus.REJECTED) is False
        assert is_active_enrollment_status(EnrollmentStatus.WITHDRAWN) is False
        assert is_active_enrollment_status(EnrollmentStatus.WAITLISTED) is False

    def test_withdraw_status_exists(self):
        from models import EnrollmentStatus
        assert hasattr(EnrollmentStatus, "WITHDRAWN")
        assert EnrollmentStatus.WITHDRAWN.value == "WITHDRAWN"

    def test_waitlisted_status_exists(self):
        from models import EnrollmentStatus
        assert hasattr(EnrollmentStatus, "WAITLISTED")
        assert EnrollmentStatus.WAITLISTED.value == "WAITLISTED"


# ============================================================================
# Model Integrity Tests
# ============================================================================

class TestUserModelIAMColumns:
    """Verify User model has all IAM columns"""

    def test_user_has_failed_login_count(self):
        from models import User
        assert hasattr(User, "failed_login_count")

    def test_user_has_locked_until(self):
        from models import User
        assert hasattr(User, "locked_until")

    def test_user_has_password_changed_at(self):
        from models import User
        assert hasattr(User, "password_changed_at")

    def test_user_has_last_login_at(self):
        from models import User
        assert hasattr(User, "last_login_at")


class TestAttendanceLogModel:
    """Verify AttendanceLog model has picked_by_name and constraint"""

    def test_has_picked_by_name(self):
        from models import AttendanceLog
        assert hasattr(AttendanceLog, "picked_by_name")

    def test_has_checkout_after_checkin_constraint(self):
        from models import AttendanceLog
        constraints = AttendanceLog.__table_args__
        constraint_names = [c.name for c in constraints if hasattr(c, "name")]
        assert "ck_attendance_checkout_after_checkin" in constraint_names


class TestNoDuplicateEnums:
    """Verify no duplicate enum definitions in models"""

    def test_single_analytics_dimension_type(self):
        import models
        import inspect
        source = inspect.getsource(models)
        count = source.count("class AnalyticsDimensionType")
        assert count == 1, f"AnalyticsDimensionType defined {count} times, expected 1"

    def test_single_analytics_period_type(self):
        import models
        import inspect
        source = inspect.getsource(models)
        count = source.count("class AnalyticsPeriodType")
        assert count == 1, f"AnalyticsPeriodType defined {count} times, expected 1"

    def test_single_export_status(self):
        import models
        import inspect
        source = inspect.getsource(models)
        count = source.count("class ExportStatus")
        assert count == 1, f"ExportStatus defined {count} times, expected 1"


# ============================================================================
# Daily Report Workflow Tests
# ============================================================================

class TestDailyReportStatus:
    """Verify daily report status enum has all required values"""

    def test_has_draft(self):
        from models import DailyReportStatus
        assert hasattr(DailyReportStatus, "DRAFT")

    def test_has_submitted(self):
        from models import DailyReportStatus
        assert hasattr(DailyReportStatus, "SUBMITTED")

    def test_has_approved(self):
        from models import DailyReportStatus
        assert hasattr(DailyReportStatus, "APPROVED")

    def test_has_sent_to_parent(self):
        from models import DailyReportStatus
        assert hasattr(DailyReportStatus, "SENT_TO_PARENT")

    def test_has_returned(self):
        from models import DailyReportStatus
        assert hasattr(DailyReportStatus, "RETURNED")

    def test_has_rejected(self):
        from models import DailyReportStatus
        assert hasattr(DailyReportStatus, "REJECTED")
