"""Submission trend chart: endpoint shape, bucketing, and frontend wiring."""

from datetime import timedelta
from pathlib import Path

import daily_reports_organization_api as api
import models

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "daily_reports_organization.html"
JS = ROOT / "static" / "js" / "admin_daily_reports_organization.js"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _js() -> str:
    return JS.read_text(encoding="utf-8")


# --- backend ----------------------------------------------------------------

def test_every_report_status_lands_in_exactly_one_bucket():
    """A status missing from the map would be silently dropped from the chart
    while still being counted in the table."""
    mapped = [s for statuses in api._TREND_BUCKETS.values() for s in statuses]
    assert len(mapped) == len(set(mapped)), "a status appears in two buckets"
    assert set(mapped) == set(models.DailyReportStatus)


def test_periods_cover_the_documented_windows():
    assert api._PERIOD_DAYS == {"week": 7, "month": 30, "quarter": 90}


def test_route_is_registered_under_the_existing_namespace():
    paths = {r.path for r in api.router.routes}
    assert "/daily-reports/trends" in paths


def test_endpoint_requires_an_admin():
    route = next(r for r in api.router.routes if r.path == "/daily-reports/trends")
    names = [d.call.__name__ for d in route.dependant.dependencies if getattr(d, "call", None)]
    assert any("admin" in n for n in names), names


def test_window_uses_the_jordan_date_not_utc():
    """A report filed at 01:00 Amman belongs to that day; date.today() on a UTC
    host would place it on the previous one."""
    source = (ROOT / "daily_reports_organization_api.py").read_text(encoding="utf-8")
    body = source.split("def submission_trends", 1)[1]
    # Strip comments: the code documents the rejected call by name.
    code = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("#")
    )
    assert "_today()" in code
    assert "date.today()" not in code


def test_trend_vocabulary_is_not_the_per_child_one():
    """"received" on this page means a parent opened the report, which the
    trend query cannot know -- reusing the word would contradict the table."""
    assert "received" not in api._TREND_BUCKETS
    assert set(api._TREND_BUCKETS) == {"sent", "pending", "incomplete"}


def test_trends_endpoint_returns_a_dense_series(client, admin_token):
    resp = client.get(
        "/api/daily-reports/trends?period=week",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Every day in the window appears, including quiet ones: a chart that skips
    # empty days hides exactly the gaps this page exists to surface.
    assert len(body["labels"]) == 7
    for bucket in ("sent", "pending", "incomplete"):
        assert len(body["series"][bucket]) == 7
    assert set(body["totals"]) >= {"total", "average", "best_day"}


def test_invalid_period_is_rejected(client, admin_token):
    resp = client.get(
        "/api/daily-reports/trends?period=decade",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


def test_trends_require_authentication(client):
    assert client.get("/api/daily-reports/trends").status_code in (401, 403)


# --- frontend ---------------------------------------------------------------

def test_section_and_canvas_exist():
    html = _html()
    assert 'id="trendsSection"' in html
    assert 'id="submissionTrendChart"' in html
    assert 'role="img"' in html


def test_controls_are_bilingual_and_stateful():
    html = _html()
    assert "Week" in html and "أسبوع" in html
    assert "Quarter" in html and "ربع سنة" in html
    assert 'aria-pressed' in html


def test_chartjs_is_loaded_from_the_vendored_copy():
    """The blueprint referenced chart.min.js; the vendored file is chart.umd.min.js."""
    html = _html()
    assert "/static/vendor/chartjs/chart.umd.min.js" in html
    assert (ROOT / "static" / "vendor" / "chartjs" / "chart.umd.min.js").exists()


def test_frontend_calls_the_real_route():
    assert "/api/daily-reports/trends?" in _js()


def test_summary_restates_the_chart_in_words():
    """A canvas is opaque to assistive tech."""
    html = _html()
    assert 'id="trendSummary"' in html
    assert 'aria-live="polite"' in html.split('id="trendSummary"', 1)[1][:200]
    assert "function renderTrendSummary" in _js()


def test_chart_failure_cannot_disturb_the_list():
    js = _js()
    body = js.split("async function refreshTrendChart", 1)[1].split("\n  function ", 1)[0]
    assert "catch" in body
    assert "showTrendError" in body


def test_missing_chart_library_degrades_quietly():
    body = _js().split("function renderTrendChart", 1)[1].split("\n  async function ", 1)[0]
    assert "window.Chart" in body
    assert "return;" in body


def test_chart_is_stacked_and_rtl_aware():
    body = _js().split("function renderTrendChart", 1)[1].split("\n  async function ", 1)[0]
    assert "stacked: true" in body
    assert 'document.documentElement.dir === "rtl"' in body


def test_chart_respects_reduced_motion():
    body = _js().split("function renderTrendChart", 1)[1].split("\n  async function ", 1)[0]
    assert "prefers-reduced-motion" in body


def test_asset_version_bumped():
    import re
    match = re.search(r"admin_daily_reports_organization\.js\?v=([0-9.]+)", _html())
    assert match and float(match.group(1)) >= 1.4
