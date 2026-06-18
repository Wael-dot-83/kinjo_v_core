"""
Test frontend integration (routes and templates)
Uses pytest fixtures to properly isolate test setup
"""
import pytest
from fastapi.testclient import TestClient
from main import app
from dependencies import get_current_user, get_current_user_or_redirect
from models import User, UserRole, UserStatus
from auth import get_password_hash


@pytest.fixture(scope="module")
def test_client():
    """Create a test client and setup database tables"""
    from database import Base, engine
    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)



@pytest.fixture(scope="module", autouse=True)
def mock_auth():
    """Mock authentication for protected routes"""
    async def mock_get_current_user():
        return User(
            id=1, 
            username="testuser",
            email="test@kinjo.sa", 
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            hashed_password=get_password_hash("TestPass123!")
        )
    
    # Set the override
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_current_user_or_redirect] = mock_get_current_user
    
    yield
    
    # Clean up overrides after tests
    app.dependency_overrides.clear()


def test_read_root(test_client):
    response = test_client.get("/", follow_redirects=False)
    # Authenticated users redirect to /dashboard; anonymous visitors get the
    # public homepage (200) — GWS requires a real homepage, not a redirect.
    if response.status_code == 307:
        assert response.headers["location"] == "/dashboard"
    else:
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


def test_read_login_page(test_client):
    response = test_client.get("/login")
    assert response.status_code == 200
    assert "تسجيل الدخول" in response.text
    assert "KinJo" in response.text


def test_static_files(test_client):
    # Verify static mount works by checking the main css file
    response = test_client.get("/static/css/kinjo.css")
    assert response.status_code == 200
    assert "KinJo" in response.text or "Variables" in response.text

    # Verify 404 for non-existent file
    response = test_client.get("/static/nonexistent.css")
    assert response.status_code == 404


def test_dashboard_access(test_client):
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    # Check for dashboard content
    # dashboard/index.html has "لوحة التحكم"
    assert "لوحة التحكم" in response.text or "مرحباً" in response.text


def test_kindergartens_list(test_client):
    response = test_client.get("/kindergartens")
    assert response.status_code == 200
    assert "الروضات" in response.text


def test_enrollment_list(test_client):
    response = test_client.get("/enrollments")
    assert response.status_code == 200
    assert "طلبات التسجيل" in response.text


def test_reports_list(test_client):
    response = test_client.get("/reports")
    assert response.status_code == 200
    assert "التقارير اليومية" in response.text


def test_attendance_page(test_client):
    response = test_client.get("/attendance/daily", follow_redirects=False)
    assert response.status_code == 403

def test_kpi_dashboard(test_client):
    response = test_client.get("/kpi/dashboard")
    assert response.status_code == 200
    assert "مؤشرات الأداء" in response.text
    assert "canvas" in response.text  # Chart.js element


def test_404_template(test_client):
    response = test_client.get("/kindergartens/999999")  # Assuming 999999 doesn't exist
    assert response.status_code == 404
    assert "404" in response.text


def test_help_page_removed(test_client):
    """Help page was removed during the streamlining cleanup; route must 404."""
    response = test_client.get("/help")
    assert response.status_code == 404


def test_privacy_page_exists(test_client):
    """Privacy policy page is required for GWS compliance."""
    response = test_client.get("/privacy")
    assert response.status_code == 200


def test_terms_page_exists(test_client):
    """Terms of use page is required for GWS compliance."""
    response = test_client.get("/terms")
    assert response.status_code == 200


def test_admin_sidebar_hides_classes_link(test_client):
    """Admin sidebar must not contain the /classes nav link (admin gets 403 on that route)."""
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert 'data-i18n="sidebar.classes"' not in response.text


def test_admin_sidebar_hides_daily_reports_link(test_client):
    """Admin sidebar must not contain the /daily-reports nav link (admin gets 403 on that route)."""
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert 'data-i18n="sidebar.daily_reports"' not in response.text


def test_admin_sidebar_shows_admin_links(test_client):
    """Admin sidebar must include admin-specific management links."""
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    html = response.text
    assert "/admin/users" in html
    assert "/admin/analytics" in html
    assert "/audit-logs" in html


def test_parent_sidebar_hides_safety_link():
    """PARENT sidebar must not show the Safety and Incidents nav link."""
    async def mock_parent_user():
        return User(
            id=2,
            username="parentuser",
            email="parent@kinjo.sa",
            role=UserRole.PARENT,
            status=UserStatus.ACTIVE,
            hashed_password=get_password_hash("TestPass123!")
        )

    app.dependency_overrides[get_current_user] = mock_parent_user
    app.dependency_overrides[get_current_user_or_redirect] = mock_parent_user
    client = TestClient(app)
    try:
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert 'data-i18n="sidebar.safety_incidents"' not in response.text
    finally:
        app.dependency_overrides.clear()
