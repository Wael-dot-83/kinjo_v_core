from main import app
from dependencies import get_current_user_or_redirect


def test_admin_daily_reports_page_uses_organization_template(client, admin_user):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
    try:
        response = client.get("/daily-reports")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "admin_daily_reports_organization.js" in response.text


def test_non_admin_daily_reports_page_keeps_existing_template(client, supervisor_user):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: supervisor_user
    try:
        response = client.get("/daily-reports")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "admin_daily_reports_organization.js" not in response.text
