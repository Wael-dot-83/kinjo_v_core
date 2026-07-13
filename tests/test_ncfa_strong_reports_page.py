"""Contract tests for the NCFA strong-alignment reporting hub."""

from pathlib import Path

from dependencies import get_current_user_or_redirect
from main import app

NCFA_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "ncfa_strong_reports.js"


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


def test_ncfa_js_reframes_participation_metric_not_data_quality():
    """The reporting-participation bundle must not surface the backend's
    'data quality score' label to users — it is a participation indicator."""
    js = NCFA_JS.read_text(encoding="utf-8")
    # data_quality_score is relabelled in BOTH languages inside the hub.
    assert "data_quality_score" in js
    assert "نسبة المشاركة في الإبلاغ" in js
    assert "Reporting participation rate" in js
    # The Arabic 'data quality score' label must not be a user-facing string here.
    assert "مؤشر جودة البيانات" not in js


def test_ncfa_js_localizes_labels_and_raw_enum_categories():
    """KPI labels, units, chart titles and raw enum categories are localised
    for both languages rather than leaking Arabic-only text or raw enums."""
    js = NCFA_JS.read_text(encoding="utf-8")
    # English KPI labels exist (backend returns Arabic-only).
    for english_label in ("Occupancy rate", "Attendance rate", "Recorded children"):
        assert english_label in js
    # Raw enum values are mapped to human-readable bilingual labels.
    for raw_enum, english in (("PENDING_REVIEW", "Pending review"), ("CRITICAL", "Critical")):
        assert raw_enum in js
        assert english in js
    # Category/label localisation is actually wired into rendering.
    assert "localizeCategory(item.label)" in js
    assert "pickLocale(KPI_LABELS, kpi.code)" in js
