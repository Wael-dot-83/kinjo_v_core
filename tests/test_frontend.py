"""
Unit tests for Frontend Routes
"""
import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse, RedirectResponse
from main import app
from auth import get_password_hash
import models
from database import get_db
from dependencies import get_current_user_optional, get_current_user, get_current_user_or_redirect


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
        home_city="Amman",
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

    def test_index_redirect_unauthenticated(self, client):
        """Test index page redirects unauthenticated users to login"""
        app.dependency_overrides[get_current_user_optional] = lambda: None

        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307  # Redirect
        assert "/login" in response.headers.get("location", "")

        app.dependency_overrides.clear()

    def test_login_page(self, client):
        """Test login page renders"""
        response = client.get("/login")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert b"login" in response.content.lower()

    def test_register_page(self, client):
        """Test register page renders"""
        response = client.get("/register")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert b"register" in response.content.lower()

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
        assert 'id="validationStatusIndicator"' in page
        assert 'role="button"' in page
        assert 'aria-live="polite"' in page
        assert 'data-chart-type="line"' in page
        assert 'data-chart-type="bar"' in page
        assert "window.dashboardDateRange" in page
        assert "function setDateRange(range)" in page

        app.dependency_overrides.clear()

    def test_dashboard_parent(self, client, parent_user):
        """Test dashboard for parent user"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: parent_user

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        app.dependency_overrides.clear()

    def test_dashboard_manager_arabic_sections(self, client, manager_user):
        """Manager dashboard should render manager-focused Arabic sections."""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_user

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        page = response.text
        assert 'id="managerSummaryClasses"' in page
        assert 'id="managerSummaryPendingReports"' in page
        assert 'id="managerSummarySupervisors"' in page
        assert 'id="managerSummaryParents"' in page
        assert "إدارة التقارير اليومية" in page
        assert "إدارة الحسابات" in page
        assert "function showCreateUserModal(role)" in page

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
            city="Amman",
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
            city="Amman",
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
            governorate="Amman", city="Amman", area="Test",
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
            home_governorate="Amman", home_city="Amman",
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
        """Test attendance history page is blocked for admin"""
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user

        response = client.get("/attendance/history")
        assert response.status_code == 403

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
        assert "\u062c\u0645\u064a\u0639 \u0627\u0644\u0631\u0648\u0636\u0627\u062a" in page
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
            city="Amman",
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
            home_city="Amman",
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

    def test_contact_page(self, client):
        """Test contact page"""
        response = client.get("/contact")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_privacy_page(self, client):
        """Test privacy policy page"""
        response = client.get("/privacy")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_terms_page(self, client):
        """Test terms of service page"""
        response = client.get("/terms")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_help_page(self, client):
        """Test help center page"""
        response = client.get("/help")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

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
        assert "/api/admin/kindergartens/import" in response.text
        assert "/api/admin/kindergartens/imported" in response.text

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
