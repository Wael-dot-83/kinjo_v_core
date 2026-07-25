"""Regression contracts for the Admin content plan's functional Batch 2."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_labels_successful_logins_truthfully():
    ar = json.loads((ROOT / "static/i18n/admin_ar.json").read_text(encoding="utf-8"))
    en = json.loads((ROOT / "static/i18n/admin_en.json").read_text(encoding="utf-8"))
    dashboard_js = (ROOT / "static/js/admin_dashboard.js").read_text(encoding="utf-8")
    fallback_js = (ROOT / "static/js/admin_i18n.js").read_text(encoding="utf-8")

    assert ar["dashboard"]["active_users"] == "المستخدمون الذين سجلوا الدخول اليوم"
    assert en["dashboard"]["active_users"] == "Users Logged In Today"
    assert "Users Logged In Today" in dashboard_js
    assert "المستخدمون الذين سجلوا الدخول اليوم" in fallback_js
    assert 'models.AuditLog.action == "LOGIN_SUCCESS"' in (
        ROOT / "admin_endpoints.py"
    ).read_text(encoding="utf-8")


def test_dashboard_daily_report_cards_link_to_real_analytics():
    dashboard_js = (ROOT / "static/js/admin_dashboard.js").read_text(encoding="utf-8")
    assert dashboard_js.count('drilldown: "/reports/analytics"') == 2
    assert 'drilldown: "/admin/analytics/daily-reports"' not in dashboard_js


def test_dashboard_attendance_chart_is_not_labeled_as_user_activity():
    dashboard_js = (ROOT / "static/js/admin_dashboard.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/admin_dashboard.html").read_text(encoding="utf-8")
    assert "attendanceChart" in dashboard_js
    assert "Recorded Attendance" in dashboard_js
    assert "سجلات الحضور" in dashboard_js
    assert 'id="attendance-chart"' in template
    assert "Daily Attendance" in template
    assert 'id="user-activity-chart"' not in template


def test_reminder_page_does_not_render_fabricated_stats_or_send_claim():
    template = (ROOT / "templates/admin/governance_reminders.html").read_text(
        encoding="utf-8"
    )
    assert 'id="statPending"' not in template
    assert 'id="statNonCompliant"' not in template
    assert "Send and track daily-report reminders" not in template
    assert "Track daily-report reminders" in template


def test_dead_incident_clone_is_removed():
    assert not (ROOT / "templates/admin/analytics/daily_reports.html").exists()
    assert not (ROOT / "tests/test_daily_reports_page_frontend_contract.py").exists()
