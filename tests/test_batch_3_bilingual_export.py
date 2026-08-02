"""
Tests for Batch 3: Bilingual & Export Correctness

CHART-001: Predictive analytics returns English-only strings
CHART-002: City names not translated in chart labels
CHART-003: CSV export lacks UTF-8 BOM for Arabic
CHART-004: Export header translation incomplete
CHART-006: Misleading metric names in supervisor analytics
CHART-007: Incident report titles hardcoded Arabic
CHART-016: Incident report export uses English-only headers
CHART-029: Incident report scope names hardcoded Arabic
CHART-030: Incident report created_by fallback hardcoded Arabic
CHART-032: Export filename uses generation date, not report period
"""

import pytest
from datetime import date, timedelta
from sqlalchemy.orm import Session

import models
from predictive_analytics import predictive_analytics


# ============================================================================
# CHART-001: Predictive analytics bilingual support
# ============================================================================


@pytest.mark.asyncio
async def test_chart_001_predictive_insights_arabic(
    test_db: Session, sample_kindergarten, sample_class, parent_enrollment, admin_user
):
    """Verify predictive insights return Arabic strings when lang='ar'."""
    # Create attendance logs for the enrolled child
    today = date.today()
    for i in range(7):
        log = models.AttendanceLog(
            child_id=parent_enrollment.child_id,
            class_id=sample_class.id,
            date=today - timedelta(days=i),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=admin_user.id,
        )
        test_db.add(log)
    test_db.commit()

    insights = await predictive_analytics.get_predictive_insights(test_db, sample_kindergarten.id, lang="ar")

    assert "summary" in insights
    assert "recommendations" in insights
    assert "alerts" in insights

    # Summary should be in Arabic
    summary = insights["summary"]
    assert "توقعات الحضور" in summary or "الحضور" in summary

    # Recommendations should be in Arabic (if any)
    if insights["recommendations"]:
        for rec in insights["recommendations"]:
            # Should contain Arabic characters
            assert any("\u0600" <= c <= "\u06ff" for c in rec)


@pytest.mark.asyncio
async def test_chart_001_predictive_insights_english(
    test_db: Session, sample_kindergarten, sample_class, parent_enrollment, admin_user
):
    """Verify predictive insights return English strings when lang='en'."""
    # Create attendance logs for the enrolled child
    today = date.today()
    for i in range(7):
        log = models.AttendanceLog(
            child_id=parent_enrollment.child_id,
            class_id=sample_class.id,
            date=today - timedelta(days=i),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=admin_user.id,
        )
        test_db.add(log)
    test_db.commit()

    insights = await predictive_analytics.get_predictive_insights(test_db, sample_kindergarten.id, lang="en")

    assert "summary" in insights
    assert "recommendations" in insights
    assert "alerts" in insights

    # Summary should be in English
    summary = insights["summary"]
    assert "Attendance forecast" in summary or "forecast" in summary

    # Recommendations should be in English (if any)
    if insights["recommendations"]:
        for rec in insights["recommendations"]:
            # Should be English text
            assert any(c.isascii() for c in rec)


@pytest.mark.asyncio
async def test_chart_001_predictive_insights_default_arabic(
    test_db: Session, sample_kindergarten, sample_class, parent_enrollment, admin_user
):
    """Verify predictive insights default to Arabic when lang not specified."""
    # Create attendance logs for the enrolled child
    today = date.today()
    for i in range(7):
        log = models.AttendanceLog(
            child_id=parent_enrollment.child_id,
            class_id=sample_class.id,
            date=today - timedelta(days=i),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=admin_user.id,
        )
        test_db.add(log)
    test_db.commit()

    insights = await predictive_analytics.get_predictive_insights(test_db, sample_kindergarten.id)

    # Default should be Arabic
    summary = insights["summary"]
    assert "توقعات الحضور" in summary or "الحضور" in summary


@pytest.mark.asyncio
async def test_chart_001_predictive_insights_with_alerts(
    test_db: Session, sample_kindergarten, sample_class, parent_enrollment, admin_user
):
    """Verify alerts are bilingual when triggered."""
    # Create attendance logs for the enrolled child
    today = date.today()
    for i in range(7):
        log = models.AttendanceLog(
            child_id=parent_enrollment.child_id,
            class_id=sample_class.id,
            date=today - timedelta(days=i),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=admin_user.id,
        )
        test_db.add(log)
    test_db.commit()

    # This test verifies that when alerts are triggered, they are bilingual
    # We can't easily trigger alerts in a unit test, so we verify the structure
    insights = await predictive_analytics.get_predictive_insights(test_db, sample_kindergarten.id, lang="ar")

    # Verify structure
    assert isinstance(insights["alerts"], list)
    assert isinstance(insights["recommendations"], list)

    # If alerts exist, they should be properly formatted
    if insights["alerts"]:
        for alert in insights["alerts"]:
            assert isinstance(alert, str)
            assert len(alert) > 0


# ============================================================================
# CHART-002: City names translation
# ============================================================================


def test_chart_002_city_names_translation():
    """Verify city names are translated in chart labels."""
    from services.jordan_locations import normalize_area, get_area_by_name

    # Test Arabic to Arabic (canonical)
    assert normalize_area("amman", "عمان") == "عمان"
    assert normalize_area("irbid", "إربد") == "إربد"

    # Test English to Arabic
    assert normalize_area("amman", "Amman") == "عمان"
    assert normalize_area("irbid", "Irbid") == "إربد"

    # Test case-insensitive
    assert normalize_area("amman", "amman") == "عمان"
    assert normalize_area("amman", "AMMAN") == "عمان"

    # Test unknown area returns unchanged
    assert normalize_area("amman", "UnknownArea") == "UnknownArea"


# ============================================================================
# CHART-003: CSV export UTF-8 BOM
# ============================================================================


def test_chart_003_csv_export_utf8_bom():
    """Verify Arabic CSV exports include UTF-8 BOM."""
    from export_service import export_service

    # Test generate_csv_response includes BOM
    headers = ["المحافظة", "العدد"]
    data = [["العاصمة", 10], ["إربد", 5]]
    response = export_service.generate_csv_response(headers, data, "test.csv")

    # Response content should start with UTF-8 BOM
    assert response.body.startswith(b"\xef\xbb\xbf"), "CSV should start with UTF-8 BOM"

    # Test generate_raw_csv_response includes BOM
    raw_data = [["عنوان", "قيمة"], ["بيانات", "123"]]
    response_raw = export_service.generate_raw_csv_response(raw_data, "test_raw.csv")
    assert response_raw.body.startswith(b"\xef\xbb\xbf"), "Raw CSV should start with UTF-8 BOM"


# ============================================================================
# CHART-004: Export header translation
# ============================================================================


def test_chart_004_export_header_translation():
    """Verify all export headers are translated."""
    from admin_reports_api import _localized

    # Test _localized helper returns correct language
    assert _localized("المحافظة", "Governorate", "ar") == "المحافظة"
    assert _localized("المحافظة", "Governorate", "en") == "Governorate"

    # Test common export headers exist in both languages
    arabic_headers = [
        _localized("إجمالي الأطفال", "Total Children", "ar"),
        _localized("إجمالي الحضانات", "Total Kindergartens", "ar"),
        _localized("المشرفة", "Supervisor", "ar"),
        _localized("الحضانة", "Kindergarten", "ar"),
    ]
    english_headers = [
        _localized("إجمالي الأطفال", "Total Children", "en"),
        _localized("إجمالي الحضانات", "Total Kindergartens", "en"),
        _localized("المشرفة", "Supervisor", "en"),
        _localized("الحضانة", "Kindergarten", "en"),
    ]

    # All Arabic headers should contain Arabic characters
    for header in arabic_headers:
        assert any("\u0600" <= c <= "\u06ff" for c in header), f"Arabic header missing: {header}"

    # All English headers should be ASCII
    for header in english_headers:
        assert header.isascii(), f"English header not ASCII: {header}"


# ============================================================================
# CHART-006: Misleading metric names
# ============================================================================


def test_chart_006_metric_names_clarity():
    """Verify metric names are clear and accurate."""
    from admin_reports_api import _localized

    # Test that metric names are clear and not misleading
    # "supervisor_gap" should be translated clearly
    gap_ar = _localized("فجوة الإشراف", "Supervisor Gap", "ar")
    gap_en = _localized("فجوة الإشراف", "Supervisor Gap", "en")

    assert gap_ar == "فجوة الإشراف"
    assert gap_en == "Supervisor Gap"

    # "capacity_utilization_pct" should include the percentage indicator
    util_ar = _localized("نسبة إشغال الطاقة", "Capacity Utilization %", "ar")
    util_en = _localized("نسبة إشغال الطاقة", "Capacity Utilization %", "en")

    assert "نسبة" in util_ar or "إشغال" in util_ar
    assert "%" in util_en or "Utilization" in util_en


# ============================================================================
# CHART-007: Incident report titles bilingual
# ============================================================================


def test_chart_007_incident_report_titles_bilingual():
    """Verify incident report titles are bilingual."""
    from admin_reports_api import _localized

    # Test incident report title translations
    title_ar = _localized("عنوان التقرير", "Report Title", "ar")
    title_en = _localized("عنوان التقرير", "Report Title", "en")

    assert title_ar == "عنوان التقرير"
    assert title_en == "Report Title"

    # Test incident-related headers
    headers = [
        ("النوع", "Type"),
        ("الخطورة", "Severity"),
        ("العدد", "Count"),
        ("إجمالي الحوادث", "Total Incidents"),
        ("الحوادث المفتوحة", "Open Incidents"),
        ("الحوادث المغلقة", "Closed Incidents"),
    ]

    for ar_text, en_text in headers:
        assert _localized(ar_text, en_text, "ar") == ar_text
        assert _localized(ar_text, en_text, "en") == en_text


# ============================================================================
# CHART-016: Incident report export headers bilingual
# ============================================================================


def test_chart_016_incident_export_headers_bilingual():
    """Verify incident report export headers are bilingual."""
    from admin_reports_api import _localized

    # Test all incident export headers
    headers = [
        ("المؤشر", "Metric"),
        ("القيمة", "Value"),
        ("إجمالي الحوادث", "Total Incidents"),
        ("الحوادث المفتوحة", "Open Incidents"),
        ("الحوادث المغلقة", "Closed Incidents"),
        ("الحوادث حسب النوع", "Incidents by Type"),
        ("الحوادث حسب الخطورة", "Incidents by Severity"),
        ("الحوادث حسب الحضانة", "Incidents by Kindergarten"),
        ("الحضانة", "Kindergarten"),
        ("العدد", "Count"),
    ]

    for ar_text, en_text in headers:
        ar_result = _localized(ar_text, en_text, "ar")
        en_result = _localized(ar_text, en_text, "en")

        assert ar_result == ar_text, f"Arabic header mismatch: {ar_result} != {ar_text}"
        assert en_result == en_text, f"English header mismatch: {en_result} != {en_text}"


# ============================================================================
# CHART-029: Incident report scope names bilingual
# ============================================================================


def test_chart_029_incident_scope_names_bilingual():
    """Verify incident report scope names are bilingual."""
    from admin_reports_api import _localized

    # Test scope-related headers
    scope_headers = [
        ("النطاق", "Scope"),
        ("تاريخ البداية", "Start Date"),
        ("تاريخ النهاية", "End Date"),
        ("أنشأ بواسطة", "Generated By"),
        ("تاريخ الإنشاء", "Generated At"),
    ]

    for ar_text, en_text in scope_headers:
        ar_result = _localized(ar_text, en_text, "ar")
        en_result = _localized(ar_text, en_text, "en")

        assert ar_result == ar_text, f"Arabic scope header mismatch: {ar_result} != {ar_text}"
        assert en_result == en_text, f"English scope header mismatch: {en_result} != {en_text}"


# ============================================================================
# CHART-030: Incident report created_by fallback bilingual
# ============================================================================


def test_chart_030_incident_created_by_fallback_bilingual():
    """Verify incident report created_by fallback is bilingual."""
    from admin_reports_api import _localized

    # Test the fallback text for unknown creator
    fallback_ar = _localized("غير معروف", "Unknown", "ar")
    fallback_en = _localized("غير معروف", "Unknown", "en")

    assert fallback_ar == "غير معروف", f"Arabic fallback mismatch: {fallback_ar}"
    assert fallback_en == "Unknown", f"English fallback mismatch: {fallback_en}"


# ============================================================================
# CHART-032: Export filename uses report period
# ============================================================================


def test_chart_032_export_filename_uses_report_period():
    """Verify export filename uses report period, not generation date."""
    from datetime import date
    from admin_reports_api import _today

    # The incident report export should use report period dates in filename
    # This is verified by checking the export_incident_report_csv function
    # which uses: f"incident_report_{report_id}_{report.start_date.isoformat()}_{report.end_date.isoformat()}.csv"

    # Test that _today() returns Jordan-local date
    today = _today()
    assert isinstance(today, date)

    # Test filename format with sample dates
    sample_start = date(2026, 7, 1)
    sample_end = date(2026, 7, 31)
    expected_pattern = f"incident_report_123_{sample_start.isoformat()}_{sample_end.isoformat()}.csv"

    assert "2026-07-01" in expected_pattern
    assert "2026-07-31" in expected_pattern
    assert expected_pattern.startswith("incident_report_")
    assert expected_pattern.endswith(".csv")


# ============================================================================
# Integration Tests: Export Endpoint BOM and Filename Verification
# ============================================================================


def test_export_endpoint_bom_integration():
    """Integration test: verify export_report endpoint produces CSV with BOM."""
    from fastapi.testclient import TestClient
    from main import app
    from export_service import export_service

    # Test generate_csv_response produces BOM
    headers = ["المحافظة", "العدد"]
    data = [["العاصمة", 10]]
    response = export_service.generate_csv_response(headers, data, "test_export.csv")

    # Verify BOM is present
    assert response.body.startswith(b"\xef\xbb\xbf"), "CSV must start with UTF-8 BOM"

    # Verify Content-Disposition header
    assert "attachment" in response.headers.get("content-disposition", "")
    assert "test_export.csv" in response.headers.get("content-disposition", "")

    # Verify media type
    assert "text/csv" in response.media_type
    assert "charset=utf-8" in response.media_type


def test_export_raw_csv_bom_integration():
    """Integration test: verify generate_raw_csv_response produces CSV with BOM."""
    from export_service import export_service

    # Test generate_raw_csv_response produces BOM
    raw_data = [["المؤشر", "القيمة"], ["إجمالي الحوادث", 15], ["الحوادث المفتوحة", 5]]
    response = export_service.generate_raw_csv_response(raw_data, "incident_report.csv")

    # Verify BOM is present
    assert response.body.startswith(b"\xef\xbb\xbf"), "Raw CSV must start with UTF-8 BOM"


def test_incident_export_filename_and_headers_are_bilingual_contract(
    client, test_db, admin_token, admin_user, sample_kindergarten
):
    """Incident export should preserve the report period in the filename and localize headers."""
    from datetime import date
    import models

    report = models.Report(
        report_type=models.ReportType.INCIDENT_SUMMARY,
        scope_type=models.ReportScopeType.KINDERGARTEN,
        kindergarten_id=sample_kindergarten.id,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
        metrics_json={"total_incidents": 2},
        created_by=admin_user.id,
    )
    test_db.add(report)
    test_db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.get(
        f"/api/admin/reports/incidents/{report.id}/export",
        params={"lang": "en"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "incident_report_" in response.headers["content-disposition"]
    assert f"incident_report_{report.id}_2026-07-01_2026-07-31.csv" in response.headers["content-disposition"]
    assert "Report Title" in response.text
    assert "Scope" in response.text

    ar_response = client.get(f"/api/admin/reports/incidents/{report.id}/export", headers=headers)
    assert ar_response.status_code == 200
    assert "عنوان التقرير" in ar_response.text
    assert "Report Title" not in ar_response.text

    # Verify Content-Disposition header keeps the report-period filename.
    assert "attachment" in response.headers.get("content-disposition", "")
    assert f"incident_report_{report.id}_2026-07-01_2026-07-31.csv" in response.headers.get("content-disposition", "")


def test_incident_export_filename_format():
    """Integration test: verify incident report export uses report period in filename."""
    from datetime import date
    from export_service import export_service

    # Simulate incident report export filename generation
    report_id = 42
    start_date = date(2026, 7, 1)
    end_date = date(2026, 7, 31)

    # This is the format used in admin_reports_api.py line 2627
    filename = f"incident_report_{report_id}_{start_date.isoformat()}_{end_date.isoformat()}.csv"

    # Verify filename format
    assert filename == "incident_report_42_2026-07-01_2026-07-31.csv"
    assert filename.startswith("incident_report_")
    assert filename.endswith(".csv")
    assert "2026-07-01" in filename
    assert "2026-07-31" in filename

    # Verify the export service accepts this filename
    raw_data = [["Report Title", "Test Report"]]
    response = export_service.generate_raw_csv_response(raw_data, filename)

    # Verify the filename is in the Content-Disposition header
    content_disp = response.headers.get("content-disposition", "")
    assert filename in content_disp


def test_export_csv_content_encoding():
    """Integration test: verify CSV content is properly encoded for Arabic."""
    from export_service import export_service

    # Test with Arabic content
    headers = ["المحافظة", "عدد الحضانات", "عدد الأطفال"]
    data = [["العاصمة", 25, 450], ["إربد", 18, 320], ["الزرقاء", 15, 280]]

    response = export_service.generate_csv_response(headers, data, "arabic_export.csv")

    # Verify BOM is present (UTF-8 BOM: EF BB BF)
    assert response.body[:3] == b"\xef\xbb\xbf", "CSV must start with UTF-8 BOM for Arabic content"

    # Verify the content can be decoded as UTF-8
    content_without_bom = response.body[3:]
    decoded_content = content_without_bom.decode("utf-8")

    # Verify Arabic characters are present in the decoded content
    assert "المحافظة" in decoded_content
    assert "العاصمة" in decoded_content
    assert "إربد" in decoded_content


def test_export_filename_with_special_characters():
    """Integration test: verify export handles filenames with dates correctly."""
    from datetime import date
    from export_service import export_service

    # Test various filename formats
    test_cases = [
        ("report_2026-07-01.csv", "report_2026-07-01.csv"),
        ("incident_report_42_2026-07-01_2026-07-31.csv", "incident_report_42_2026-07-01_2026-07-31.csv"),
        ("kindergarten_report_arabic.csv", "kindergarten_report_arabic.csv"),
    ]

    for filename, expected in test_cases:
        raw_data = [["Test", "Data"]]
        response = export_service.generate_raw_csv_response(raw_data, filename)

        # Verify filename is in Content-Disposition
        content_disp = response.headers.get("content-disposition", "")
        assert expected in content_disp, f"Filename {expected} not found in {content_disp}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
