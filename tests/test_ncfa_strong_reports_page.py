"""Contract tests for the NCFA strong-alignment reporting hub."""

from dependencies import get_current_user_or_redirect
from main import app


def test_ncfa_page_contains_strong_alignment_hub(client, admin_user):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
    try:
        response = client.get("/admin/agency-reports/ncfa")
        assert response.status_code == 200
        html = response.text
        assert 'id="ncfa-strong-reports"' in html
        assert "توافق قوي" in html
        assert "مركز تقارير الطفولة المبكرة والحضانات" in html
        assert "ncfa_strong_reports.css" in html
        assert "ncfa_strong_reports.js" in html
        assert 'id="ncfa-report-bundles"' in html
        assert 'id="ncfa-report-result"' in html
    finally:
        app.dependency_overrides.clear()


def test_non_ncfa_agency_page_does_not_load_ncfa_hub(client, admin_user):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
    try:
        response = client.get("/admin/agency-reports/mosd")
        assert response.status_code == 200
        html = response.text
        assert 'id="ncfa-strong-reports"' not in html
        assert "ncfa_strong_reports.css" not in html
        assert "ncfa_strong_reports.js" not in html
    finally:
        app.dependency_overrides.clear()
