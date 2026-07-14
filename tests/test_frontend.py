"""
Unit tests for Frontend Routes
"""
import re
import pytest
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse, RedirectResponse
from main import app
from auth import get_password_hash
import models
from database import get_db
from dependencies import get_current_user_optional, get_current_user, get_current_user_or_redirect


def test_admin_user_edit_page_hides_other_admin(client, test_db, admin_user):
    other_admin = models.User(
        username="frontend_other_admin",
        email="frontend-other-admin@example.com",
        hashed_password=get_password_hash("SecurePass123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(other_admin)
    test_db.commit()
    test_db.refresh(other_admin)
    app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
    try:
        response = client.get(f"/admin/users/{other_admin.id}/edit")
        assert response.status_code == 404
        assert other_admin.email not in response.text
    finally:
        app.dependency_overrides.clear()


def test_manager_user_edit_page_hides_cross_tenant_user(client, test_db, manager_user):
    other_kg = models.Kindergarten(
        name_ar="حضانه نطاق آخر",
        name_en="Other Scope KG",
        governorate="Amman",
        district="Amman",
        area="Test",
        address_line="Test",
        contact_phone="+962790009999",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(other_kg)
    test_db.flush()
    other_user = models.User(
        username="frontend_cross_tenant",
        email="frontend-cross-tenant@example.com",
        hashed_password=get_password_hash("SecurePass123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=other_kg.id,
    )
    test_db.add(other_user)
    test_db.commit()
    app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
    try:
        response = client.get(f"/admin/users/{other_user.id}/edit")
        assert response.status_code == 404
        assert other_user.email not in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path",
    [
        "/admin/kindergartens/999999999",
        "/admin/kindergartens/999999999/edit",
    ],
)
def test_missing_admin_kindergarten_pages_return_404(client, admin_user, path):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
    try:
        response = client.get(path)
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


"""
Unit tests for Frontend Routes
"""
import pytest
from datetime import date
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse, RedirectResponse
from main import app
from auth import get_password_hash
import models
from database import get_db
from dependencies import get_current_user_optional, get_current_user, get_current_user_or_redirect


@pytest.fixture
def manager_user(test_db, sample_kindergarten):
    """
    Create a manager user for testing
    """
    user = models.User(
        username="testmanager",
        email="manager@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=sample_kindergarten.id
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def supervisor_user(test_db, sample_kindergarten):
    """
    Create a supervisor user for testing
    """
    user = models.User(
        username="testsupervisor",
        email="supervisor@test.com",
        hashed_password=get_password_hash("Supervisor123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=sample_kindergarten.id
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def parent_user(test_db, sample_kindergarten):
    """
    Create a parent user for testing
    """
    user = models.User(
        username="testparent",
        email="parent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Create parent profile
    parent_profile = models.ParentProfile(
        user_id=user.id,
        first_name="Test",
        last_name="Parent",
        phone_number="+962791234567",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        national_id="123456789",
        home_governorate="Amman",
        home_district="Amman",
        home_area="Abdoun",
        home_address_line="123 Main St",
        correspondence_preference=True  # Boolean field, not enum
    )
    test_db.add(parent_profile)
    test_db.commit()
    test_db.refresh(parent_profile)

    return user


@pytest.fixture
def supervisor_user(test_db, sample_kindergarten):
    """
    Create a supervisor user for testing
    """
    user = models.User(
        username="supervisor@test.com",
        email="supervisor@test.com",
        hashed_password=get_password_hash("Supervisor123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=sample_kindergarten.id
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user
    """
    Create a parent user for testing
    """
    user = models.User(
        username="testparent",
        email="parent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestFrontendRoutes:
    """Test frontend HTML routes"""

    def test_index_redirect_authenticated(self, client, admin_user):
        """Test index page redirects authenticated users to dashboard"""
        # Mock authenticated user
        app.dependency_overrides[get_current_user_optional] = lambda: admin_user

        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307  # Redirect
        assert "/dashboard" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    def test_index_renders_public_homepage_unauthenticated(self, client):
        """Anonymous visitors get a real public homepage (GWS requirement),
        not a redirect to login — Round 3."""
        app.dependency_overrides[get_current_user_optional] = lambda: None

        response = client.get("/", follow_redirects=False)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "/register" in response.text
        assert "/login" in response.text

        app.dependency_overrides.clear()

    def test_login_page(self, client):
        """Test login page renders"""
        response = client.get("/login")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert b"login" in response.content.lower()

    def test_login_page_expired_banner_server_rendered(self, client):
        """/login?expired=true renders the session-expired banner visible
        server-side (no d-none) so it works without JavaScript, with the
        warmer 'session ended for your security' copy."""
        import re

        response = client.get("/login?expired=true")
        assert response.status_code == 200
        text = response.text
        norm = re.sub(r"\s+", " ", text)
        # Banner is NOT hidden when the session expired
        assert "auth-alert-warning d-none" not in text
        # Warmer bilingual copy is present (Arabic is the primary UI language)
        assert "حفاظاً على أمان حسابك" in norm

    def test_login_page_no_expired_banner_by_default(self, client):
        """A normal /login visit keeps the expired banner hidden (d-none)."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "auth-alert-warning d-none" in response.text

    def test_login_page_remember_me_label_matches_behavior(self, client):
        """remember_me extends the session lifetime server-side, so the label
        must read 'Keep me signed in' (إبقائي مسجّل الدخول) — never the
        ambiguous 'تذكّرني' — and must warn about shared devices."""
        import re

        response = client.get("/login")
        text = response.text
        norm = re.sub(r"\s+", " ", text)
        assert "إبقائي مسجّل" in norm
        assert "تذكّرني" not in text
        assert "جهاز عام أو مشترك" in norm

    def test_login_page_has_forgot_password_link(self, client):
        """The forgot-password recovery link is present and points at the
        reachable /forgot-password route."""
        response = client.get("/login")
        assert 'href="/forgot-password"' in response.text

    def test_login_language_toggle_preserves_expired_state(self, client):
        """The no-JS language switch must carry the session-expired context and a
        redirect target across the language change (mandate §17), and must not
        leak that state onto a normal login page."""
        response = client.get("/login?expired=true&redirect=%2Fdashboard")
        text = response.text
        assert "?lang=en&expired=true" in text
        # redirect is carried too (Jinja's urlencode may or may not encode the
        # leading slash depending on version — accept either form)
        assert ("redirect=%2Fdashboard" in text) or ("redirect=/dashboard" in text)
        # A normal visit keeps the toggle href clean
        clean = client.get("/login").text
        assert 'href="?lang=en"' in clean
        assert "expired=true" not in clean

    def test_login_form_has_accessible_name(self, client):
        """The login form is programmatically named by the page heading (§7)."""
        text = client.get("/login").text
        assert 'aria-labelledby="authHeading"' in text
        assert 'id="authHeading"' in text

    def test_register_page(self, client):
        """Test register page renders"""
        response = client.get("/register")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert b"register" in response.content.lower()

    def test_mfa_setup_page(self, client):
        """MFA setup page renders without authentication"""
        response = client.get("/mfa/setup")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_forgot_password_page(self, client):
        """Forgot password page renders without authentication"""
        response = client.get("/forgot-password")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_reset_password_page(self, client):
        """Reset password page renders with optional token"""
        response = client.get("/reset-password?token=abc123")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_favicon(self, client):
        """Test favicon endpoint"""
        response = client.get("/favicon.ico")
        assert response.status_code == 204  # No content

    def test_change_password_page(self, client, admin_user):
        """Test change password page for authenticated user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/change-password")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_dashboard_admin(self, client, admin_user):
        """Test dashboard for admin user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert b"dashboard" in response.content.lower()
        page = response.text
        # Admin dashboard theme indicators (extends admin_base.html)
        assert 'id="admin-dashboard"' in page
        assert 'data-ui-state="loading"' in page
        assert 'id="dashboard-loading"' in page
        assert 'aria-busy="true"' in page
        assert 'id="kpi-cards"' in page
        assert 'id="dashboard-content"' in page
        assert 'id="refresh-dashboard"' in page
        assert '/static/js/admin_dashboard.js' in page
        # Admin profile display — header avatar (initials-based, no PNG)
        assert 'header-user-details' in page
        assert 'header-user-avatar' in page

        app.dependency_overrides.clear()

    def test_dashboard_parent(self, client, parent_user):
        """Test dashboard for parent user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_dashboard_manager_arabic_sections(self, client, manager_user):
        """Manager dashboard renders the operational, own-KG Arabic page
        (manager/dashboard.html — replaced the global-stats index page)."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        # Operational stat cards
        assert 'id="statReportsPending"' in page
        assert 'id="statAbsencePending"' in page
        assert 'id="statEnrollmentPending"' in page
        assert 'id="statSupervisors"' in page
        # Arabic section headings
        assert "لوحة تحكم المدير" in page
        assert "بانتظار إجراءاتك اليوم" in page
        assert "تنبيهات تشغيلية" in page
        # National/global totals must NOT appear on a manager page
        assert "إجمالي الحضانات" not in page
        assert "إجمالي المستخدمين" not in page

        app.dependency_overrides.clear()

    def test_manager_benchmarking_page_manager(self, client, manager_user):
        """Manager benchmarking page renders for manager with Arabic content."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/manager/benchmarking")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        assert "managerBenchmarkRoot" in page
        assert "managerBenchmarkLoadBtn" in page

        app.dependency_overrides.clear()

    def test_manager_benchmarking_page_supervisor_redirect(self, client, supervisor_user):
        """Non-manager users should be redirected away from manager benchmarking page."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user

        response = client.get("/manager/benchmarking", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_manager_absence_requests_page_manager(self, client, manager_user):
        """Manager absence requests page renders with manager workflow UI."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/manager/absence-requests")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        assert "requestsTable" in page
        assert "decisionModal" in page

        app.dependency_overrides.clear()

    def test_manager_absence_requests_page_supervisor_redirect(self, client, supervisor_user):
        """Supervisor should not access manager absence requests page."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user

        response = client.get("/manager/absence-requests", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_supervisor_dashboard(self, client, supervisor_user):
        """Test dedicated supervisor dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user

        response = client.get("/supervisor/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        assert 'id="taskCount"' in page
        assert 'id="attendanceGrid"' in page

        app.dependency_overrides.clear()

    def test_supervisor_dashboard_manager_redirect(self, client, manager_user):
        """Manager cannot access dedicated supervisor dashboard route."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/supervisor/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_supervisor_performance_page_supervisor(self, client, supervisor_user):
        """Supervisor performance page renders for supervisor."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user

        response = client.get("/supervisor/performance")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "supervisorPerformanceRoot" in response.text

        app.dependency_overrides.clear()

    def test_supervisor_performance_page_manager_redirect(self, client, manager_user):
        """Manager cannot access supervisor performance page."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/supervisor/performance", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_supervisor_observations_page_supervisor(self, client, supervisor_user):
        """Supervisor observations page renders for supervisor."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user

        response = client.get("/supervisor/observations")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        assert "observationForm" in page
        assert "observationsList" in page

        app.dependency_overrides.clear()

    def test_supervisor_observations_page_parent_redirect(self, client, parent_user):
        """Parent cannot access supervisor observations page."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/supervisor/observations", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_parent_dashboard(self, client, parent_user):
        """Test dedicated parent dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/parent/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_parent_profile_page(self, client, parent_user):
        """Parent profile page renders for parent user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/parent/profile")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_parent_children_page(self, client, parent_user):
        """Parent children page renders for parent user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/parent/children")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_parent_enrollments_page(self, client, parent_user):
        """Parent enrollments page renders for parent user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/parent/enrollments")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_parent_attendance_page(self, client, parent_user):
        """Parent attendance page renders for parent user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/parent/attendance")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_kindergartens_admin(self, client, admin_user, test_db):
        """Test list kindergartens for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/kindergartens")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_kindergartens_manager(self, client, manager_user, test_db):
        """Test list kindergartens for manager (shows only their kindergarten)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/kindergartens")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_kindergarten_page_admin(self, client, admin_user):
        """Test create kindergarten page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/kindergartens/create")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_kindergarten_page_manager_denied(self, client, manager_user):
        """Test create kindergarten page access denied for manager"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/kindergartens/create")
        assert response.status_code == 403

        app.dependency_overrides.clear()

    def test_view_kindergarten_admin(self, client, admin_user, test_db):
        """Test view kindergarten for admin"""
        # Create a test kindergarten
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Abdoun",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get(f"/kindergartens/{kg.id}")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_view_kindergarten_not_found(self, client, admin_user):
        """Test view non-existent kindergarten"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/kindergartens/99999")
        assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_edit_kindergarten_page_admin(self, client, admin_user, test_db):
        """Test edit kindergarten page for admin"""
        # Create a test kindergarten
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Abdoun",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get(f"/kindergartens/{kg.id}/edit")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_enrollments(self, client, admin_user):
        """Test list enrollments page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/enrollments")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_enrollments_supervisor_denied(self, client, supervisor_user):
        """Test list enrollments access denied for supervisor"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user

        response = client.get("/enrollments")
        assert response.status_code == 403

        app.dependency_overrides.clear()

    def test_create_enrollment_page_admin(self, client, admin_user, test_db):
        """Test create enrollment page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/enrollments/create")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_enrollment_page_manager(self, client, manager_user, test_db):
        """Test create enrollment page for manager"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/enrollments/create")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_view_enrollment(self, client, admin_user, test_db):
        """Test view enrollment page"""
        # Create real test data
        kg = models.Kindergarten(
            name_ar="Test KG", name_en="Test KG",
            governorate="Amman", district="Amman", area="Test",
            address_line="Test", contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        parent_profile = models.ParentProfile(
            user_id=admin_user.id,
            first_name="Test", last_name="Parent",
            phone_number="+962791234567",
            gender=models.Gender.MALE, nationality="Jordanian",
            home_governorate="Amman", home_district="Amman",
            home_area="Test", home_address_line="Test"
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test", last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Test Father",
            mother_first_name="Test", mother_last_name="Mother",
            mother_nationality="Jordanian"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.PENDING_REVIEW
        )
        test_db.add(enrollment)
        test_db.commit()
        test_db.refresh(enrollment)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get(f"/enrollments/{enrollment.id}")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_attendance_history(self, client, admin_user, sample_kindergarten):
        """Test attendance history page is accessible for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/attendance/history")
        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_list_reports(self, client, admin_user):
        """Test list reports page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/reports")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_report_page(self, client, admin_user):
        """Test create report page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/reports/create")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_view_report(self, client, admin_user):
        """Test view report page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/reports/123")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_kpi_dashboard_page(self, client, admin_user):
        """Test KPI dashboard page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/kpi/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        assert 'id="kpiDashboardRoot"' in page
        assert 'aria-live="polite"' in page
        assert 'id="granularitySelect"' in page
        assert 'id="filterStatus"' in page
        assert 'id="filterError"' in page
        assert "\u062c\u0645\u064a\u0639 \u0627\u0644\u062d\u0636\u0627\u0646\u0627\u062a" in page
        assert page.count("function renderRankingList(") == 1
        assert page.count("function escapeHtml(") == 1
        assert page.count("requestWithAuth(") >= 1
        assert page.count("function createTrendChart(") == 1
        assert "noDataOverlay" in page
        assert page.count("function renderStudentDistribution(") == 1
        assert "/ws/dashboard?token=" in page

        app.dependency_overrides.clear()

    def test_communication_dashboard(self, client, admin_user):
        """Test communication dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/communication")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_messages(self, client, admin_user):
        """Test list messages page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/communication/messages")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_events(self, client, admin_user):
        """Test list events page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/communication/events")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_surveys(self, client, admin_user):
        """Test list surveys page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/communication/surveys")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_tasks(self, client, admin_user):
        """Test list tasks page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/tasks")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_curriculum_page_manager_redirect(self, client, manager_user):
        """Curriculum page redirects manager to dashboard (placeholder route)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/curriculum", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/dashboard" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    def test_curriculum_page_supervisor_403(self, client, supervisor_user):
        """Curriculum page returns 403 for supervisors"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user

        response = client.get("/curriculum")
        assert response.status_code == 403

        app.dependency_overrides.clear()

    def test_safety_dashboard(self, client, admin_user):
        """Test safety dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/safety")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_incident_page(self, client, admin_user):
        """Test create incident page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/safety/incidents/new")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_attendance_main_redirect(self, client, admin_user):
        """Test attendance main page redirects admin away from daily page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/attendance", follow_redirects=False)
        assert response.status_code == 307  # Redirect
        assert "/dashboard" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    def test_attendance_daily_admin(self, client, admin_user, test_db):
        """Test attendance daily page is blocked for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/attendance/daily", follow_redirects=False)
        assert response.status_code == 403

        app.dependency_overrides.clear()

    def test_attendance_daily_manager(self, client, manager_user, test_db):
        """Test attendance daily page for manager"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/attendance/daily")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_attendance_check_in_manager(self, client, manager_user, test_db):
        """Test attendance check-in page for manager"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/attendance/check-in")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_daily_reports_list_redirect(self, client, admin_user):
        """Test daily-reports list page renders"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/daily-reports")
        assert response.status_code == 200  # Renders list page
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_daily_report_redirect(self, client, admin_user):
        """Test create daily-report page is blocked for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/daily-reports/create")
        assert response.status_code == 403

        app.dependency_overrides.clear()

    def test_new_enrollment_redirect(self, client, admin_user):
        """Test new enrollment redirects to create"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/enrollments/new", follow_redirects=False)
        # RedirectResponse defaults to 307
        assert response.status_code in [301, 302, 307, 308]
        assert "/enrollments/create" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    def test_create_incident_redirect(self, client, admin_user):
        """Test create incident renders form"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/incidents/create")
        assert response.status_code == 200  # Renders form
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_messages_list_redirect(self, client, admin_user):
        """Test messages renders messages page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/messages")
        assert response.status_code == 200  # Renders messages page
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_new_message_page(self, client, admin_user):
        """Test new message page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/messages/new")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_user_profile_redirect(self, client, admin_user):
        """Test profile renders settings page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/profile")
        assert response.status_code == 200  # Renders settings page
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_user_settings(self, client, admin_user):
        """Test user settings page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/settings")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_notifications_list(self, client, admin_user):
        """Test notifications list page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/notifications")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_kpi_main_redirect(self, client, admin_user):
        """Test kpi main redirects to dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/kpi", follow_redirects=False)
        assert response.status_code == 307  # Redirect
        assert "/kpi/dashboard" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    def test_view_class(self, client, admin_user, test_db):
        """Test view class page for admin"""
        # Create a test class
        kg = models.Kindergarten(
            name_ar="Test KG",
            name_en="Test KG",
            governorate="Amman",
            district="Amman",
            area="Abdoun",
            address_line="Test Address",
            contact_phone="+962791234567",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        class_obj = models.Class(
            name_ar="Test Class",
            name_en="Test Class",
            class_code="TEST-001",
            age_group="AGE_2_4",
            kindergarten_id=kg.id,
            capacity_total=30,
            min_age_months=36,
            max_age_months=48
        )
        test_db.add(class_obj)
        test_db.commit()
        test_db.refresh(class_obj)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get(f"/classes/{class_obj.id}")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_view_class_not_found(self, client, admin_user):
        """Test view non-existent class"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/classes/99999")
        assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_list_classes_admin(self, client, admin_user):
        """Test classes list page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/classes")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "إدارة الشعب الصفية" in response.text

        app.dependency_overrides.clear()

    def test_list_classes_manager(self, client, manager_user):
        """Test classes list page for manager"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/classes")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "إدارة الشعب الصفية" in response.text

        app.dependency_overrides.clear()

    def test_view_child(self, client, admin_user, test_db):
        """Test view child page for admin"""
        # Create test data
        parent_profile = models.ParentProfile(
            user_id=admin_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+962791234567",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Abdoun",
            home_address_line="Test Address",
            correspondence_preference=True
        )
        test_db.add(parent_profile)
        test_db.commit()
        test_db.refresh(parent_profile)

        child = models.Child(
            first_name="Test",
            last_name="Child",
            parent_id=parent_profile.id,
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Test Father",
            mother_first_name="Test",
            mother_last_name="Mother",
            mother_nationality="Jordanian"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get(f"/children/{child.id}")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_enroll_child_redirect(self, client, admin_user):
        """Test enroll child redirects to enrollment create"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/enroll", follow_redirects=False)
        assert response.status_code == 307  # Redirect
        assert "/enrollments/create" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    def test_parent_reports(self, client, parent_user):
        """Test parent reports page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/my-reports")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_contact_page_exists(self, client):
        """Contact page is required for GWS compliance (public Contact Us form)."""
        response = client.get("/contact")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_privacy_page_exists(self, client):
        """Privacy policy page is required for GWS compliance."""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_terms_page_exists(self, client):
        """Terms of use page is required for GWS compliance."""
        response = client.get("/terms")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_help_page_removed(self, client):
        """Help page was removed during the streamlining cleanup; route must 404."""
        response = client.get("/help")
        assert response.status_code == 404

    def test_audit_logs_page_admin(self, client, admin_user):
        """Test audit logs page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/audit-logs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_audit_logs_page_non_admin(self, client, manager_user):
        """Test audit logs page access denied for non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/audit-logs", follow_redirects=False)
        assert response.status_code == 307  # Redirect to dashboard

        app.dependency_overrides.clear()

    def test_list_users_page_admin(self, client, admin_user):
        """Test admin users list page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/users")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_list_users_page_manager(self, client, manager_user):
        """Test admin users list page for manager"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/users")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_user_page_admin(self, client, admin_user, test_db):
        """Test create user page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/users/create")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_create_user_page_manager(self, client, manager_user, test_db):
        """Test create user page for manager"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/users/create")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_edit_user_page_admin(self, client, admin_user, test_db):
        """Test edit user page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get(f"/admin/users/{admin_user.id}/edit")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_message_compose_admin(self, client, admin_user):
        """Test admin message compose page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/messages/compose")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_message_compose_non_admin(self, client, manager_user):
        """Test admin message compose access denied for non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/messages/compose", follow_redirects=False)
        assert response.status_code == 307  # Redirect to dashboard

        app.dependency_overrides.clear()

    def test_admin_import_kindergartens_page_admin(self, client, admin_user):
        """Import page should call API-scoped admin endpoints"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/import-kindergartens")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "/api/admin/kindergartens/import-excel" in response.text
        # The page used to also call /api/admin/kindergartens/imported to
        # populate its results table, but that endpoint reads a disjoint
        # CLI-only table (ImportedKindergarten), never the rows this page's
        # own upload actually inserted. Fixed to read inserted_records
        # directly from the import-excel response instead.
        assert "/api/admin/kindergartens/imported" not in response.text

        app.dependency_overrides.clear()

    def test_admin_imported_kindergartens_page_uses_api_prefix(self, client, admin_user):
        """Imported list page should query the API endpoint prefix"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/imported-kindergartens")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "/api/admin/kindergartens/imported" in response.text

        app.dependency_overrides.clear()

    def test_admin_analytics_admin(self, client, admin_user):
        """Test admin analytics page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/analytics")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_analytics_non_admin(self, client, manager_user):
        """Test admin analytics access denied for non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/analytics", follow_redirects=False)
        assert response.status_code == 307  # Redirect to dashboard

        app.dependency_overrides.clear()

    def test_admin_analytics_live_sections_are_visible(self, client, admin_user):
        """Predictions/anomalies/risk-heatmap/targets/benchmarks/recommendations widgets
        must render in the visible dashboard, not be trapped inside the hidden
        #pageHelpContent guide panel (regression: they were previously nested there
        and never displayed, even though admin_analytics.js populates them with
        real API data)."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/analytics")
        assert response.status_code == 200
        page = response.text

        # pageHelpContent has been removed (task: remove "How to use this page" section).
        assert 'id="pageHelpContent"' not in page, (
            "#pageHelpContent must not be present — help section was removed"
        )

        dashboard_start = page.index('class="az-analytics-page"')
        visible_section = page[dashboard_start:]

        live_widget_ids = [
            "attendanceForecast",
            "incidentForecast",
            "enrollmentForecast",
            "modelMeta",
            "anomalyList",
            "anomalyCount",
            "riskHeatmap",
            "alertList",
            "alertBanner",
            "dataQualityScore",
            "dataQualityStatus",
            "targetList",
            "benchmarkList",
            "recommendationList",
        ]
        for widget_id in live_widget_ids:
            assert f'id="{widget_id}"' in visible_section, (
                f"#{widget_id} must be present in the visible dashboard markup"
            )

        app.dependency_overrides.clear()

    def test_admin_analytics_no_hardcoded_fake_risk_entry(self, client, admin_user):
        """The Smart Risk Indicator card must start as a skeleton loader, not a
        baked-in fake kindergarten/risk-score (no mock data in production markup)."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/analytics")
        assert response.status_code == 200
        page = response.text

        assert "Al-Amal Kindergarten" not in page
        assert "حضانة الأمل" not in page
        assert "92% Risk" not in page
        assert "92% خطر" not in page

        app.dependency_overrides.clear()

    def test_admin_reports_admin(self, client, admin_user):
        """Test admin reports page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/analytics/reports")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_analytics_drilldown_admin(self, client, admin_user):
        """Test admin analytics drilldown for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/analytics/drilldown/kindergarten/1")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_governance_reports_admin(self, client, admin_user):
        """Test governance reports page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/governance-reports")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        assert "/static/js/admin_governance.js" in page
        assert "حوكمة التقارير اليومية" in page

        app.dependency_overrides.clear()

    def test_admin_governance_reports_non_admin(self, client, manager_user):
        """Test governance reports access denied for non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/governance-reports", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_admin_incident_report_generate_page_admin(self, client, admin_user):
        """Test incident report generation page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/reports/incidents/generate")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_daily_reports_page_admin(self, client, admin_user):
        """Test daily reports page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/analytics/daily-reports")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_incident_report_detail_page_admin(self, client, admin_user):
        """Test incident report detail page for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/reports/incidents/1")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_messages_list_admin(self, client, admin_user, test_db):
        """Test admin messages list for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/messages")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_import_users_page_admin(self, client, admin_user):
        """Import Users page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/users/import")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_import_users_page_non_admin_redirects(self, client, manager_user):
        """Import Users page must redirect non-admin to dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/users/import", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_admin_import_logs_page_admin(self, client, admin_user):
        """Import Logs page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/import-logs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_import_logs_page_non_admin_redirects(self, client, manager_user):
        """Import Logs page must redirect non-admin to dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/import-logs", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_admin_governance_reminders_page_admin(self, client, admin_user):
        """Governance Reminders page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/governance/reminders")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_governance_reminders_page_non_admin_redirects(self, client, manager_user):
        """Governance Reminders page must redirect non-admin to dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/governance/reminders", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_admin_alerts_page_admin(self, client, admin_user):
        """Alerts page must be accessible by admin and render from admin_base.html"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/alerts")
        assert response.status_code == 200
        ct = response.headers.get("content-type", "")
        assert "text/html" in ct
        assert "admin_alerts.js" in response.text

        app.dependency_overrides.clear()

    def test_admin_alerts_page_non_admin_redirects(self, client, manager_user):
        """Alerts page must redirect non-admin to dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/alerts", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Heat map page
    # ------------------------------------------------------------------

    def test_admin_heatmap_page_admin(self, client, admin_user):
        """Heat map page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/heatmap")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        html = response.text
        assert 'class="heatmap-shell"' in html
        assert 'id="googleMapContainer"' in html
        assert "/static/js/jordan_cesium_map.js" in html

        app.dependency_overrides.clear()

    def test_admin_heatmap_has_professional_loading_state_contract(self):
        """Heat map client keeps an explicit map loading state before Google Maps is ready."""
        template = Path("templates/admin/heatmap.html").read_text(encoding="utf-8")
        script = Path("static/js/jordan_cesium_map.js").read_text(encoding="utf-8")

        assert ".heatmap-shell" in template
        assert ".map-loading-state" in template
        assert "ensureMapLoadingState()" in script
        assert "map-ready" in script

    def test_admin_heatmap_page_non_admin_redirects(self, client, manager_user):
        """Heat map page must redirect non-admin to dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/heatmap", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # /admin root redirect
    # ------------------------------------------------------------------

    def test_admin_root_redirects_to_dashboard(self, client, admin_user):
        """/admin must redirect to /admin/dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin", follow_redirects=False)
        assert response.status_code == 302
        assert "/admin/dashboard" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Non-admin redirects for analytics / reports pages
    # ------------------------------------------------------------------

    def test_admin_reports_non_admin_redirects(self, client, manager_user):
        """Analytics reports page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/analytics/reports", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    def test_admin_analytics_drilldown_non_admin_redirects(self, client, manager_user):
        """Analytics drilldown must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/analytics/drilldown/kindergarten/1", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    def test_admin_daily_reports_non_admin_redirects(self, client, manager_user):
        """Admin analytics daily-reports page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/analytics/daily-reports", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    def test_admin_incident_report_generate_non_admin_redirects(self, client, manager_user):
        """Incident report generation page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/reports/incidents/generate", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    def test_admin_incident_report_detail_non_admin_redirects(self, client, manager_user):
        """Incident report detail page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/reports/incidents/1", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    def test_admin_messages_list_non_admin_redirects(self, client, manager_user):
        """Admin messages list must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/messages", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Audit logs page
    # ------------------------------------------------------------------

    def test_audit_logs_page_admin(self, client, admin_user):
        """Audit logs page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/audit-logs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_audit_logs_page_non_admin_redirects(self, client, manager_user):
        """Audit logs page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/audit-logs", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Incident reports list page
    # ------------------------------------------------------------------

    def test_incidents_list_page_admin(self, client, admin_user):
        """Incident reports list must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/incidents")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_incidents_list_page_non_admin_redirects(self, client, manager_user):
        """Incident reports list must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/incidents", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Contact messages page
    # ------------------------------------------------------------------

    def test_admin_contact_messages_page_admin(self, client, admin_user, test_db):
        """Contact messages page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/contact-messages")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_contact_messages_page_non_admin_redirects(self, client, manager_user):
        """Contact messages page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/contact-messages", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Daily reports organization page (admin via /daily-reports)
    # ------------------------------------------------------------------

    def test_daily_reports_org_page_admin(self, client, admin_user):
        """Admin visiting /daily-reports should get the org template"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/daily-reports")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin Profile page
    # ------------------------------------------------------------------

    def test_admin_profile_page_admin(self, client, admin_user):
        """Admin profile page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/profile")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert admin_user.username in response.text

        app.dependency_overrides.clear()

    def test_admin_profile_page_non_admin_redirects(self, client, manager_user):
        """Admin profile page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/profile", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    def test_admin_profile_days_active_treats_naive_created_at_as_utc(self, client, admin_user):
        """days_active previously treated a naive created_at as already
        being Jordan-local time (created.replace(tzinfo=_JORDAN_TZ)),
        unlike every other timestamp-handling call site in this codebase
        (e.g. admin_endpoints.py's audit-log formatter), which treats a
        naive DB timestamp as UTC and converts to Jordan time -- a 3-hour
        skew that can flip the reported day count near local midnight.

        Fixture: "now" is Jordan midnight; created_at (stored naive, as
        this DB always stores it) sits 1 day 23 hours before that point
        when correctly interpreted as UTC-then-converted (-> 1 full day
        active). The old buggy interpretation adds an extra 3 hours of
        apparent age, pushing the same row to 2 days active -- a real,
        reproducible boundary case, not just an arbitrary date pair."""
        from datetime import datetime, timezone, timedelta
        # The /admin/profile handler now lives in the compat module that
        # frontend.py re-exports; patch datetime there, not on the wrapper.
        import scripts.compat.frontend_orig as frontend_module

        _JORDAN_TZ = timezone(timedelta(hours=3))
        fixed_now_jordan = datetime(2026, 7, 5, 0, 0, 0, tzinfo=_JORDAN_TZ)
        correct_created_jordan = fixed_now_jordan - timedelta(days=1, hours=23)
        created_naive_utc = correct_created_jordan.astimezone(timezone.utc).replace(tzinfo=None)
        admin_user.created_at = created_naive_utc

        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now_jordan if tz is not None else fixed_now_jordan.replace(tzinfo=None)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        original_datetime = frontend_module.datetime
        frontend_module.datetime = _FixedDateTime
        try:
            response = client.get("/admin/profile")
            assert response.status_code == 200
            assert '<div class="profile-stat-value">1</div>' in response.text
            assert '<div class="profile-stat-value">2</div>' not in response.text
        finally:
            frontend_module.datetime = original_datetime
            app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin Settings page
    # ------------------------------------------------------------------

    def test_admin_settings_page_admin(self, client, admin_user):
        """Admin settings page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/settings")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_settings_page_non_admin_redirects(self, client, manager_user):
        """Admin settings page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/settings", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers.get("location") == "/dashboard"

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin Classification page
    # ------------------------------------------------------------------

    def test_admin_classification_page_admin(self, client, admin_user):
        """Classification page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/classification")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        html = response.text
        assert 'id="classificationSummaryCards"' in html
        assert 'id="classificationBandChart"' in html
        assert 'id="classificationScoreChart"' in html
        assert 'id="classificationAspectChart"' in html
        assert "/static/js/admin_classification.js?v=6" in html

        app.dependency_overrides.clear()

    def test_admin_classification_page_non_admin_redirects(self, client, manager_user):
        """Classification page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/classification", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin Impersonate page
    # ------------------------------------------------------------------

    def test_admin_impersonate_page_admin(self, client, admin_user):
        """Impersonate page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/impersonate")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_impersonate_page_non_admin_redirects(self, client, manager_user):
        """Impersonate page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/impersonate", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin Safety Analytics page
    # ------------------------------------------------------------------

    def test_admin_safety_analytics_page_admin(self, client, admin_user):
        """Safety analytics page must be accessible by admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/admin/safety-analytics")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_admin_safety_analytics_page_non_admin_redirects(self, client, manager_user):
        """Safety analytics page must redirect non-admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/admin/safety-analytics", follow_redirects=False)
        assert response.status_code == 307

        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # normalize_ui_language edge cases (lines 27-28)
    # ------------------------------------------------------------------

    def test_language_cookie_en_sets_ltr(self, client, admin_user):
        """?lang=en query param switches to LTR"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/dashboard?lang=en")
        assert response.status_code == 200
        assert 'dir="ltr"' in response.text or "ltr" in response.text
        app.dependency_overrides.clear()

    def test_language_invalid_falls_back_to_ar(self, client, admin_user):
        """Unknown lang value falls back to Arabic"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/dashboard?lang=xyz")
        assert response.status_code == 200
        assert 'dir="rtl"' in response.text or "rtl" in response.text
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # register page when PUBLIC_REGISTRATION_ENABLED=False (line 121)
    # ------------------------------------------------------------------

    def test_register_page_disabled_redirects(self, client):
        """Registration disabled → redirect to login"""
        from unittest.mock import patch
        # The /register handler now lives in the compat module that frontend.py
        # re-exports; patch settings there, not on the wrapper.
        with patch("scripts.compat.frontend_orig.settings") as mock_settings:
            mock_settings.PUBLIC_REGISTRATION_ENABLED = False
            mock_settings.TESTING = False
            mock_settings.CSRF_COOKIE_NAME = "csrftoken"
            response = client.get("/register", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "login" in response.headers.get("location", "")

    # ------------------------------------------------------------------
    # dashboard supervisor branch (line 165)
    # ------------------------------------------------------------------

    def test_dashboard_supervisor(self, client, supervisor_user):
        """Supervisor gets supervisor dashboard template"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Parent route non-parent redirect branches (lines 191, 204, 213, 222, 230)
    # ------------------------------------------------------------------

    def test_parent_dashboard_non_parent_redirects(self, client, admin_user):
        """Non-parent user redirected from /parent/dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/parent/dashboard", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/dashboard" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_parent_profile_non_parent_redirects(self, client, admin_user):
        """Non-parent redirected from /parent/profile"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/parent/profile", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/profile" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_parent_children_non_parent_redirects(self, client, admin_user):
        """Non-parent redirected from /parent/children"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/parent/children", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_parent_enrollments_non_parent_redirects(self, client, admin_user):
        """Non-parent redirected from /parent/enrollments"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/parent/enrollments", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_parent_attendance_non_parent_redirects(self, client, admin_user):
        """Non-parent redirected from /parent/attendance"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/parent/attendance", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Kindergartens — ADMIN filtering + other-role fallback (lines 258-299)
    # ------------------------------------------------------------------

    def test_kindergartens_admin_no_kg_id(self, client, test_db, sample_kindergarten):
        """Admin with no kindergarten_id can still list kindergartens"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: models.User(
            id=9001,
            username="adminkg",
            email="adminkg@test.com",
            hashed_password="x",
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=None
        )
        response = client.get("/kindergartens")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_kindergartens_admin_with_status_filter(self, client, admin_user, test_db, sample_kindergarten):
        """Admin can filter kindergartens by status"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/kindergartens?status=active")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_kindergartens_admin_with_invalid_status(self, client, admin_user, test_db, sample_kindergarten):
        """Invalid status string is ignored gracefully"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/kindergartens?status=INVALID")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_kindergartens_admin_with_governorate_filter(self, client, admin_user, test_db, sample_kindergarten):
        """Admin can filter kindergartens by governorate"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/kindergartens?governorate=Amman")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_kindergartens_admin_with_city_name_filter(self, client, admin_user, test_db, sample_kindergarten):
        """Admin can filter kindergartens by city and name"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/kindergartens?district=Amman&name=test")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_kindergartens_supervisor_role(self, client, supervisor_user, test_db):
        """Supervisor gets empty kindergarten list (other-role branch)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/kindergartens")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Kindergartens — MANAGER wrong-kg 403 / non-admin/manager 403 (lines 339-357)
    # ------------------------------------------------------------------

    def test_view_kindergarten_manager_wrong_kg(self, client, test_db, manager_user, sample_kindergarten):
        """Manager cannot view a kindergarten they don't own"""
        other_kg = models.Kindergarten(
            name_ar="حضانة أخرى",
            name_en="Other KG",
            license_number="OTHER001",
            governorate="Irbid",
            district="Irbid",
            area="Irbid Center",
            address_line="Other Addr",
            contact_phone="+96222000001",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/kindergartens/{other_kg.id}")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_view_kindergarten_supervisor_403(self, client, supervisor_user, test_db, sample_kindergarten):
        """Supervisor cannot view kindergartens (other-role 403)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get(f"/kindergartens/{sample_kindergarten.id}")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_edit_kindergarten_404(self, client, admin_user):
        """Edit kindergarten page returns 404 for missing kg"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/kindergartens/99999/edit")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_edit_kindergarten_manager_wrong_kg_403(self, client, test_db, manager_user, sample_kindergarten):
        """Manager cannot edit a kindergarten they don't own"""
        other_kg = models.Kindergarten(
            name_ar="حضانة أخرى 2",
            name_en="Other KG 2",
            license_number="OTHER002",
            governorate="Zarqa",
            district="Zarqa",
            area="Zarqa Center",
            address_line="Other Addr 2",
            contact_phone="+96222000002",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/kindergartens/{other_kg.id}/edit")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_edit_kindergarten_supervisor_403(self, client, supervisor_user, test_db, sample_kindergarten):
        """Supervisor cannot edit kindergartens"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get(f"/kindergartens/{sample_kindergarten.id}/edit")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Classes — non-MANAGER/ADMIN 403, MANAGER create/edit (lines 369-396)
    # ------------------------------------------------------------------

    def test_classes_list_supervisor_403(self, client, supervisor_user):
        """Supervisor cannot access class list"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/classes")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_create_class_page_manager(self, client, manager_user, test_db, sample_kindergarten):
        """Manager can access create class page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/classes/create")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_create_class_page_admin_403(self, client, admin_user):
        """Admin cannot access create class page (manager-only)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/classes/create")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_edit_class_admin_403(self, client, admin_user):
        """Admin cannot edit classes (manager-only)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/classes/1/edit")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_edit_class_manager_404(self, client, manager_user, test_db, sample_kindergarten):
        """Manager gets 404 for non-existent class"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/classes/99999/edit")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_edit_class_manager_wrong_kg_403(self, client, manager_user, test_db, sample_kindergarten):
        """Manager gets 403 for class in another kindergarten"""
        other_kg = models.Kindergarten(
            name_ar="حضانة ثالثة",
            name_en="Third KG",
            license_number="THIRD001",
            governorate="Amman",
            district="Amman",
            area="Amman Center",
            address_line="Third St",
            contact_phone="+96222000003",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        cls = models.Class(
            name_ar="فصل أ",
            name_en="Class A",
            class_code="CLSA001",
            kindergarten_id=other_kg.id,
            age_group="AGE_2_4",
            capacity_total=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/classes/{cls.id}/edit")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Enrollments — PARENT redirect, SUPERVISOR 403 (lines 413, 423)
    # ------------------------------------------------------------------

    def test_enrollments_list_parent_redirect(self, client, parent_user):
        """Parent redirected from /enrollments to parent enrollments"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/enrollments", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/parent/enrollments" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_enrollment_create_supervisor_403(self, client, supervisor_user):
        """Supervisor cannot access enrollment create page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/enrollments/create")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_enrollment_create_parent(self, client, parent_user, test_db):
        """Parent can access enrollment create page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/enrollments/create")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_enrollment_view_404(self, client, admin_user):
        """Enrollment view returns 404 for missing enrollment"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/enrollments/99999")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance history — PARENT redirect, non-PARENT context (lines 562, 566-605)
    # ------------------------------------------------------------------

    def test_attendance_history_parent_redirects(self, client, parent_user):
        """Parent is redirected from attendance history"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/attendance/history", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/parent/dashboard" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_attendance_history_manager(self, client, manager_user, test_db, sample_kindergarten):
        """Manager can access attendance history"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/attendance/history")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_attendance_history_manager_no_kg_403(self, client, test_db):
        """Manager without kindergarten gets 403 on attendance history"""
        user = models.User(
            id=9002,
            username="mgr_nokg",
            email="mgr_nokg@test.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=None
        )
        app.dependency_overrides[get_current_user_or_redirect] = lambda: user
        response = client.get("/attendance/history")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Reports — PARENT redirect (lines 615, 622)
    # ------------------------------------------------------------------

    def test_reports_list_parent_redirect(self, client, parent_user):
        """Parent is redirected away from /reports"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/reports", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_reports_create_parent_redirect(self, client, parent_user):
        """Parent is redirected away from /reports/create"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/reports/create", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # KPI / Tasks / Safety — PARENT redirects (lines 654, 685, 697)
    # ------------------------------------------------------------------

    def test_kpi_dashboard_parent_redirect(self, client, parent_user):
        """Parent is redirected from KPI dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/kpi/dashboard", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_kpi_dashboard_supervisor_redirect(self, client, supervisor_user):
        """Supervisor is redirected from KPI dashboard because KPI API is admin/manager-only"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/kpi/dashboard", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert response.headers.get("location") == "/dashboard"
        app.dependency_overrides.clear()

    def test_tasks_parent_redirect(self, client, parent_user):
        """Parent is redirected from /tasks"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/tasks", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_safety_parent_redirect(self, client, parent_user):
        """Parent is redirected from /safety"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/safety", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Safety incidents/create — ADMIN redirect, non-staff redirect (lines 706-708)
    # ------------------------------------------------------------------

    def test_create_safety_incident_admin_redirect(self, client, admin_user):
        """Admin is redirected to daily-reports from safety incidents/new"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/safety/incidents/new", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/daily-reports" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_create_safety_incident_parent_redirect(self, client, parent_user):
        """Parent is redirected from safety incidents/new"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/safety/incidents/new", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance main — PARENT redirect (lines 721-723)
    # ------------------------------------------------------------------

    def test_attendance_main_parent_redirect(self, client, parent_user):
        """Parent is redirected from /attendance to absence-requests"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/attendance", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/absence-requests" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance daily — PARENT redirect, MANAGER no-kg 403 (lines 738, 745)
    # ------------------------------------------------------------------

    def test_attendance_daily_parent_redirect(self, client, parent_user):
        """Parent is redirected from /attendance/daily"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/attendance/daily", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/absence-requests" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_attendance_daily_manager_no_kg_403(self, client, test_db):
        """Manager without kindergarten gets 403 on daily attendance"""
        user = models.User(
            id=9003,
            username="mgr_nokg2",
            email="mgr_nokg2@test.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=None
        )
        app.dependency_overrides[get_current_user_or_redirect] = lambda: user
        response = client.get("/attendance/daily")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance check-in — MANAGER no-kg 403 (line 792)
    # ------------------------------------------------------------------

    def test_attendance_check_in_manager_no_kg_403(self, client, test_db):
        """Manager without kindergarten gets 403 on check-in page"""
        user = models.User(
            id=9004,
            username="mgr_nokg3",
            email="mgr_nokg3@test.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=None
        )
        app.dependency_overrides[get_current_user_or_redirect] = lambda: user
        response = client.get("/attendance/check-in")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Daily reports — non-ADMIN gets reports/list, daily-reports/create MANAGER (lines 843, 856)
    # ------------------------------------------------------------------

    def test_daily_reports_manager_gets_review_template(self, client, manager_user):
        """Manager gets the dedicated review template (manager/daily_reports_
        review.html), not the read-only reports/list.html -- the latter's
        manager view only linked to a static, control-free detail page,
        despite a full approve/edit/send-to-parent/delete workflow already
        existing end-to-end in routers/manager.py with no route pointing at
        the template built for it."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/daily-reports")
        assert response.status_code == 200
        assert "مراجعة التقارير اليومية" in response.text
        assert "/api/manager/daily-reports" in response.text
        app.dependency_overrides.clear()

    def test_create_daily_report_manager(self, client, manager_user):
        """Manager can access daily-reports/create"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/daily-reports/create")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Incidents create — non-staff redirect (line 881)
    # ------------------------------------------------------------------

    def test_incidents_create_parent_redirect(self, client, parent_user):
        """Parent is redirected from /incidents/create"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/incidents/create", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Profile — PARENT redirect (line 919)
    # ------------------------------------------------------------------

    def test_profile_parent_redirect(self, client, parent_user):
        """Parent is redirected from /profile to /parent/profile"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/profile", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/parent/profile" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # View class — MANAGER/SUPERVISOR wrong-KG 403 (lines 949-950)
    # ------------------------------------------------------------------

    def test_view_class_manager_wrong_kg_403(self, client, test_db, manager_user, sample_kindergarten):
        """Manager gets 403 for class in another kindergarten"""
        other_kg = models.Kindergarten(
            name_ar="حضانة رابعة",
            name_en="Fourth KG",
            license_number="FOUR001",
            governorate="Amman",
            district="Amman",
            area="Amman West",
            address_line="Four St",
            contact_phone="+96222000004",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(other_kg)
        test_db.commit()
        test_db.refresh(other_kg)
        cls = models.Class(
            name_ar="فصل ب",
            name_en="Class B",
            class_code="CLSB001",
            kindergarten_id=other_kg.id,
            age_group="AGE_2_4",
            capacity_total=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/classes/{cls.id}")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Children list — PARENT redirect / non-parent redirect (lines 957-961)
    # ------------------------------------------------------------------

    def test_children_list_parent_redirect(self, client, parent_user):
        """Parent redirected to /parent/children"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/children", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/parent/children" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_children_list_manager_gets_children_page(self, client, manager_user):
        """Manager now gets the manager/children.html page directly -- it was
        fully built against the already-correctly-scoped GET /api/manager/
        children endpoint, but had no route and managers were redirected to
        the dashboard with no children list page at all."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/children", follow_redirects=False)
        assert response.status_code == 200
        assert "/api/manager/children" in response.text
        app.dependency_overrides.clear()

    def test_manager_supervisors_page_renders(self, client, manager_user):
        """manager/supervisors.html was fully built (assign-class modal,
        stat cards) and its API contract already matched GET /api/manager/
        supervisors exactly, but had no route at all -- not even a redirect,
        just a 404."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/manager/supervisors")
        assert response.status_code == 200
        assert "/api/manager/supervisors" in response.text
        app.dependency_overrides.clear()

    def test_manager_supervisors_page_blocks_non_manager(self, client, admin_user):
        """Non-manager roles are redirected away, matching every other
        /manager/* page's convention."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/manager/supervisors", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/dashboard" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_manager_sidebar_links_to_children_and_supervisors_pages(self, client, manager_user):
        """Both manager/children.html and manager/supervisors.html were
        reachable-by-URL after being wired up, but neither had a sidebar
        entry -- a manager had no way to discover either page without
        already knowing the exact URL."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert 'href="/children"' in response.text
        assert 'href="/manager/supervisors"' in response.text
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # View child — 404, PARENT access control, MANAGER scoped (lines 970-984)
    # ------------------------------------------------------------------

    def test_view_child_404(self, client, admin_user):
        """Returns 404 for non-existent child"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/children/99999")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_view_child_parent_wrong_child_403(self, client, parent_user, test_db):
        """Parent cannot view another parent's child"""
        from auth import get_password_hash as _gph
        other_user = models.User(
            username="other_parent_u",
            email="other_parent_u@test.com",
            hashed_password=_gph("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(other_user)
        test_db.commit()
        test_db.refresh(other_user)
        other_profile = models.ParentProfile(
            user_id=other_user.id,
            first_name="Other",
            last_name="Parent",
            phone_number="+962799000001",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            national_id="999888777",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test",
            home_address_line="Test",
            correspondence_preference=True
        )
        test_db.add(other_profile)
        test_db.commit()
        test_db.refresh(other_profile)
        child = models.Child(
            first_name="Other",
            last_name="Child",
            date_of_birth=date(2024, 1, 1),
            gender=models.Gender.MALE,
            parent_id=other_profile.id,
            father_name="Other Father",
            mother_first_name="Mother",
            mother_last_name="Name",
            mother_nationality="Jordanian",
            mother_national_id="111222333"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get(f"/children/{child.id}")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_view_child_manager_not_enrolled_403(self, client, manager_user, test_db, sample_kindergarten):
        """Manager gets 403 for child not enrolled in their kindergarten"""
        from auth import get_password_hash as _gph
        other_user2 = models.User(
            username="other_parent_u2",
            email="other_parent_u2@test.com",
            hashed_password=_gph("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(other_user2)
        test_db.commit()
        test_db.refresh(other_user2)
        other_profile = models.ParentProfile(
            user_id=other_user2.id,
            first_name="Other2",
            last_name="Parent2",
            phone_number="+962799000002",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            national_id="999888778",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test2",
            home_address_line="Test2",
            correspondence_preference=True
        )
        test_db.add(other_profile)
        test_db.commit()
        test_db.refresh(other_profile)
        child = models.Child(
            first_name="Unenrolled",
            last_name="Child",
            date_of_birth=date(2024, 6, 1),
            gender=models.Gender.MALE,
            parent_id=other_profile.id,
            father_name="Unenrolled Father",
            mother_first_name="Mother2",
            mother_last_name="Name2",
            mother_nationality="Jordanian",
            mother_national_id="111222334"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/children/{child.id}")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # my-reports — non-PARENT redirect, date parse, no parent profile (lines 1003-1018)
    # ------------------------------------------------------------------

    def test_my_reports_admin_redirect(self, client, admin_user):
        """Non-parent is redirected from /my-reports"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/my-reports", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/dashboard" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    def test_my_reports_invalid_date_falls_back(self, client, parent_user, test_db):
        """Invalid date param falls back to today"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/my-reports?date=not-a-date")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_my_reports_no_parent_profile(self, client, test_db):
        """Parent with no profile gets empty list"""
        bare_parent = models.User(
            id=9010,
            username="bareparent",
            email="bareparent@test.com",
            hashed_password="x",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        app.dependency_overrides[get_current_user_or_redirect] = lambda: bare_parent
        response = client.get("/my-reports")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_my_reports_child_id_filter_forbidden(self, client, parent_user, test_db):
        """Parent cannot access reports for another child via child_id filter"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/my-reports?child_id=99999")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_my_reports_valid_parent(self, client, parent_user, test_db):
        """Parent with profile gets reports list (even if empty)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/my-reports")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin user management — non-admin/manager redirect (lines 1097, 1103, 1122)
    # ------------------------------------------------------------------

    def test_admin_users_list_supervisor_redirect(self, client, supervisor_user):
        """Supervisor is redirected from /admin/users"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/admin/users", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_admin_users_create_supervisor_redirect(self, client, supervisor_user):
        """Supervisor is redirected from /admin/users/create"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/admin/users/create", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_admin_users_create_manager(self, client, manager_user, test_db, sample_kindergarten):
        """Manager can access /admin/users/create (scoped to their KG)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/admin/users/create")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_admin_users_edit_supervisor_redirect(self, client, supervisor_user, test_db, admin_user):
        """Supervisor is redirected from user edit page"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get(f"/admin/users/{admin_user.id}/edit", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_admin_users_edit_404(self, client, admin_user):
        """Edit user page returns 404 for non-existent user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/admin/users/99999/edit")
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_admin_users_edit_manager_wrong_kg_redirect(self, client, manager_user, test_db, admin_user):
        """Manager cannot edit user from another kindergarten"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/admin/users/{admin_user.id}/edit", follow_redirects=False)
        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_admin_users_edit_manager_own_kg(self, client, manager_user, test_db, sample_kindergarten):
        """Manager can edit user in their own kindergarten"""
        other_user = models.User(
            username="mgr_staff",
            email="mgr_staff@test.com",
            hashed_password="x",
            role=models.UserRole.SUPERVISOR,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=sample_kindergarten.id
        )
        test_db.add(other_user)
        test_db.commit()
        test_db.refresh(other_user)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/admin/users/{other_user.id}/edit")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin import pages — non-admin redirect (lines 1165, 1177)
    # ------------------------------------------------------------------

    def test_import_kindergartens_non_admin_redirect(self, client, manager_user):
        """Non-admin redirected from import kindergartens"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/admin/import-kindergartens", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    def test_imported_kindergartens_supervisor_redirect(self, client, supervisor_user):
        """Supervisor redirected from imported kindergartens"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/admin/imported-kindergartens", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin dashboard non-admin redirect (lines 1198-1200)
    # ------------------------------------------------------------------

    def test_admin_dashboard_manager_redirect(self, client, manager_user):
        """Manager is redirected from admin dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/admin/dashboard", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/dashboard" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Absence requests — PARENT with children (lines 1357-1370)
    # ------------------------------------------------------------------

    def test_absence_requests_parent_with_children(self, client, parent_user, test_db):
        """Parent can view absence requests page with their children"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/absence-requests")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_absence_requests_non_parent_redirect(self, client, manager_user):
        """Non-parent redirected from /absence-requests"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/absence-requests", follow_redirects=False)
        assert response.status_code in (302, 307)
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Contact messages — search/status filters (lines 1478-1491)
    # ------------------------------------------------------------------

    def test_contact_messages_with_search_and_open_filter(self, client, admin_user, test_db):
        """Admin can filter contact messages by search term and open status"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/admin/contact-messages?q=test&status_filter=open")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_contact_messages_with_resolved_filter(self, client, admin_user, test_db):
        """Admin can filter contact messages by resolved status"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/admin/contact-messages?status_filter=resolved")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin dashboard — admin renders template (line 1200)
    # ------------------------------------------------------------------

    def test_admin_dashboard_admin_renders(self, client, admin_user):
        """Admin can access the admin dashboard"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/admin/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Admin sidebar i18n — every visible label must switch with ui_lang,
    # not stay hardcoded in English (regression guard)
    # ------------------------------------------------------------------

    def test_admin_sidebar_is_arabic_by_default(self, client, admin_user):
        """Default (no ?lang= override) admin sidebar renders in Arabic"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/admin/dashboard")
        assert response.status_code == 200
        page = response.text
        sidebar = page[page.index('id="admin-sidebar"'):page.index("</aside>")]
        sidebar_no_comments = re.sub(r"<!--.*?-->", "", sidebar, flags=re.DOTALL)
        assert "لوحة التحكم" in sidebar
        assert "المستخدمون" in sidebar
        assert "البيانات" in sidebar
        assert "التحليلات والتقارير" in sidebar
        assert "الخريطة الحرارية" in sidebar
        assert "النظام" in sidebar
        assert "انتحال الهوية" not in sidebar
        # None of the old hardcoded English group headers should remain
        # (comments are stripped since the section dividers keep the English
        # name for readability — only visible text must follow ui_lang)
        assert "User Management" not in sidebar_no_comments
        assert "Analytics &amp; Reports" not in sidebar_no_comments
        assert "Governance &amp; Compliance" not in sidebar_no_comments
        assert "Security &amp; Audit" not in sidebar_no_comments
        app.dependency_overrides.clear()

    def test_admin_sidebar_switches_to_english(self, client, admin_user):
        """?lang=en renders the admin sidebar fully in English"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/admin/dashboard?lang=en")
        assert response.status_code == 200
        page = response.text
        sidebar = page[page.index('id="admin-sidebar"'):page.index("</aside>")]
        assert "Dashboard" in sidebar
        assert "Users" in sidebar
        assert "Data Management" in sidebar
        assert "Reports &amp; Analytics" in sidebar
        assert "Heat Map" in sidebar
        assert "System" in sidebar
        assert "Impersonation" not in sidebar
        assert "Jordan Heat Map" not in sidebar
        # No leftover Arabic text should appear when English is selected
        assert "لوحة التحكم" not in sidebar
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Create safety incident — supervisor and manager get form (line 708)
    # ------------------------------------------------------------------

    def test_create_safety_incident_supervisor(self, client, supervisor_user):
        """Supervisor can access safety incidents/new"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/safety/incidents/new")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance main — manager redirects to /attendance/daily (line 723)
    # ------------------------------------------------------------------

    def test_attendance_main_manager_redirect_to_daily(self, client, manager_user):
        """Manager is redirected from /attendance to /attendance/daily"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get("/attendance", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/attendance/daily" in response.headers.get("location", "")
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance daily/check-in — SUPERVISOR with assignments (lines 758-770, 806-818)
    # ------------------------------------------------------------------

    def test_attendance_daily_supervisor_403(self, client, supervisor_user, test_db, sample_kindergarten):
        """Supervisor is blocked from daily attendance (use check-in instead)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/attendance/daily")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    def test_attendance_check_in_supervisor(self, client, supervisor_user, test_db, sample_kindergarten):
        """Supervisor can access check-in page (gets their class assignments)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
        response = client.get("/attendance/check-in")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance history — manager whose KG doesn't exist in DB (line 597)
    # ------------------------------------------------------------------

    def test_attendance_history_manager_kg_missing(self, client, test_db):
        """Manager whose kindergarten_id points to a missing record gets 403"""
        user = models.User(
            id=9020,
            username="mgr_badkg",
            email="mgr_badkg@test.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=99999
        )
        app.dependency_overrides[get_current_user_or_redirect] = lambda: user
        response = client.get("/attendance/history")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Edit class — manager success path (lines 395-396)
    # ------------------------------------------------------------------

    def test_edit_class_manager_own_kg(self, client, manager_user, test_db, sample_kindergarten):
        """Manager can access edit page for a class in their own KG"""
        cls = models.Class(
            name_ar="فصل خاص",
            name_en="Own Class",
            class_code="OWNC001",
            kindergarten_id=sample_kindergarten.id,
            age_group="AGE_2_4",
            capacity_total=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user
        response = client.get(f"/classes/{cls.id}/edit")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Enrollment create — MANAGER with no kindergarten (line 462)
    # ------------------------------------------------------------------

    def test_enrollment_create_manager_no_kg(self, client, test_db):
        """Manager with no kindergarten_id gets empty enrollment form"""
        user = models.User(
            id=9021,
            username="mgr_nokg_enroll",
            email="mgr_nokg_enroll@test.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=None
        )
        app.dependency_overrides[get_current_user_or_redirect] = lambda: user
        response = client.get("/enrollments/create")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # my-reports — valid child filter (lines 1044, 1048-1066)
    # ------------------------------------------------------------------

    def test_my_reports_valid_child_filter_own_child(self, client, parent_user, sample_child, test_db):
        """Parent can filter /my-reports by their own child_id"""
        parent_profile = test_db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == parent_user.id
        ).first()
        if not parent_profile:
            pytest.skip("No parent profile found for parent_user")
        child_qs = test_db.query(models.Child).filter(
            models.Child.parent_id == parent_profile.id
        ).all()
        if not child_qs:
            pytest.skip("No children found for parent_user")
        child_id = child_qs[0].id
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get(f"/my-reports?child_id={child_id}")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_my_reports_invalid_child_id_format(self, client, parent_user, test_db):
        """Non-integer child_id uses -1 as fallback and returns 403"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user
        response = client.get("/my-reports?child_id=notanumber")
        assert response.status_code == 403
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # my-reports — parent with a real child in DB (lines 1044, 1048-1066)
    # ------------------------------------------------------------------

    def test_my_reports_parent_with_child(self, client, test_db):
        """Parent with a child in DB can filter reports by that child_id"""
        from auth import get_password_hash as _gph
        pr_user = models.User(
            username="rpt_parent",
            email="rpt_parent@test.com",
            hashed_password=_gph("Test123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        test_db.add(pr_user)
        test_db.commit()
        test_db.refresh(pr_user)
        profile = models.ParentProfile(
            user_id=pr_user.id,
            first_name="Rpt",
            last_name="Parent",
            phone_number="+962799100001",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="RPT100001",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Test",
            home_address_line="Test",
            correspondence_preference=True
        )
        test_db.add(profile)
        test_db.commit()
        test_db.refresh(profile)
        child = models.Child(
            first_name="Rpt",
            last_name="Child",
            date_of_birth=date(2024, 3, 1),
            gender=models.Gender.MALE,
            parent_id=profile.id,
            father_name="Rpt Father",
            mother_first_name="Rpt",
            mother_last_name="Mother",
            mother_nationality="Jordanian",
            mother_national_id="RPT200001"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        app.dependency_overrides[get_current_user_or_redirect] = lambda: pr_user
        # Valid own child → covers lines 1044 and 1048-1066
        response = client.get(f"/my-reports?child_id={child.id}")
        assert response.status_code == 200
        # No-filter path also exercises 1048-1066
        response2 = client.get("/my-reports")
        assert response2.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Kindergartens — manager with no kindergarten_id (lines 258-259)
    # ------------------------------------------------------------------

    def test_kindergartens_manager_no_kg_id(self, client, test_db):
        """Manager with no kindergarten_id gets empty list"""
        user = models.User(
            id=9030,
            username="mgr_nokg_kgs",
            email="mgr_nokg_kgs@test.com",
            hashed_password="x",
            role=models.UserRole.MANAGER,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=None
        )
        app.dependency_overrides[get_current_user_or_redirect] = lambda: user
        response = client.get("/kindergartens")
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # Attendance check-in — admin gets else branch (line 818)
    # ------------------------------------------------------------------

    def test_attendance_check_in_admin(self, client, admin_user, test_db):
        """Admin accesses check-in page (else branch for non-manager/supervisor)"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        response = client.get("/attendance/check-in")
        assert response.status_code == 200
        app.dependency_overrides.clear()
