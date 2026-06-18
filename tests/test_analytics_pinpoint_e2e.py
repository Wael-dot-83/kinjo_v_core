"""
Advanced Pinpoint Validation Suite for Admin Analytics
=====================================================
Validates frontend-backend contract, DOM visibility, RTL CSS rendering,
Bootstrap utility consistency, and runtime JS behavior.
"""
import json
import os
import re
import shutil
import subprocess
import pytest
from datetime import date, timedelta
from main import app
from dependencies import get_current_user_or_redirect, get_current_user


class TestAnalyticsDOMVisibility:
    """
    Pinpoint tests verifying that every live widget ID in the analytics
    dashboard is inside the VISIBLE .analytics-dashboard container and
    NOT trapped inside #pageHelpContent (which is display:none).
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user):
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.client = client
        self.page = client.get("/admin/analytics").text
        yield
        app.dependency_overrides.clear()

    def test_pagehelpcontent_is_closed_before_analytics_dashboard(self):
        help_pos = self.page.index('id="pageHelpContent"')
        dash_pos = self.page.index('class="analytics-dashboard"')
        assert help_pos < dash_pos

    def test_no_live_widget_inside_hidden_help_container(self):
        help_start = self.page.index('id="pageHelpContent"')
        dash_start = self.page.index('class="analytics-dashboard"')
        help_section = self.page[help_start:dash_start]
        live_ids = [
            "attendanceForecast", "incidentForecast", "enrollmentForecast",
            "attendanceForecastBand", "incidentForecastBand", "enrollmentForecastBand",
            "modelMeta", "anomalyList", "anomalyCount", "riskHeatmap",
            "alertList", "alertBanner", "dataQualityScore", "dataQualityStatus",
            "targetList", "benchmarkList", "recommendationList",
        ]
        for wid in live_ids:
            assert wid not in help_section, f"#{wid} leaked into hidden #pageHelpContent"

    def test_kpi_card_ids_in_visible_dashboard(self):
        visible = self.page[self.page.index('class="analytics-dashboard"'):]
        for kid in ["totalKg", "totalChildren", "avgAttendance", "incidentRate",
                    "enrollmentRate", "kpiKgGrowth", "attendanceTrendIndicator", "incidentTrend"]:
            assert f'id="{kid}"' in visible, f"KPI #{kid} missing from visible dashboard"

    def test_chart_canvas_ids_present_and_visible(self):
        visible = self.page[self.page.index('class="analytics-dashboard"'):]
        assert 'id="trendChart"' in visible
        assert 'id="governancePieChart"' in visible

    def test_error_state_markup_exists(self):
        visible = self.page[self.page.index('class="analytics-dashboard"'):]
        assert 'id="trendChartError"' in visible
        assert "analytics-error-state" in visible

    def test_no_hardcoded_mock_risk_entry(self):
        assert "Al-Amal Kindergarten" not in self.page
        assert "92% Risk" not in self.page
        assert "92% خطر" not in self.page

    def test_skeleton_loaders_present_for_initial_state(self):
        assert "skeleton-text" in self.page
        visible = self.page[self.page.index('class="analytics-dashboard"'):]
        assert "skeleton-row" in visible or "skeleton-text" in visible


class TestAnalyticsRTLStructure:
    """Verify RTL-aware markup in the rendered analytics page."""

    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user):
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.page = client.get("/admin/analytics").text
        yield
        app.dependency_overrides.clear()

    def test_rtl_css_rules_present(self):
        assert 'html[dir="rtl"]' in self.page

    def test_direction_aware_btn_group_rules(self):
        assert '.btn-group .btn:first-child' in self.page or 'btn-group' in self.page

    def test_page_renders_in_arabic_by_default(self):
        assert 'lang="ar"' in self.page or 'لوحة التحليلات' in self.page


class TestAnalyticsAPIContract:
    """
    Validates that /api/analytics/dashboard-data returns data matching the
    frontend's expected structure. Tests edge cases: boundary dates, empty data.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user, sample_kindergarten):
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.client = client
        self.admin_user = admin_user
        yield
        app.dependency_overrides.clear()

    def _dashboard_resp(self, days=30):
        today = date.today()
        start = today - timedelta(days=days)
        return self.client.get(
            f"/api/analytics/dashboard-data?period_start={start}&period_end={today}"
        )

    def test_dashboard_data_has_required_top_level_keys(self):
        resp = self._dashboard_resp()
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        for key in ["network_summary", "governorate_breakdown",
                     "attendance_trend", "incident_trend",
                     "risk_radar", "governance_distribution"]:
            assert key in data, f"Missing top-level key: {key}"

    def test_network_summary_schema(self):
        resp = self._dashboard_resp()
        assert resp.status_code == 200
        ns = resp.json()["network_summary"]
        field_types = {
            "total_kindergartens": int,
            "total_children": int,
            "attendance_rate": (int, float),
            "incident_rate": (int, float),
            "enrollment_rate": (int, float),
        }
        for field, expected in field_types.items():
            assert field in ns, f"network_summary missing: {field}"
            assert isinstance(ns[field], expected), f"{field} type: {type(ns[field])}"

    def test_network_summary_previous_period_deltas_schema(self):
        resp = self._dashboard_resp()
        assert resp.status_code == 200
        ns = resp.json()["network_summary"]
        assert isinstance(ns["previous_period"], dict)
        assert isinstance(ns["deltas"], dict)
        for metric in ["total_kindergartens", "attendance_rate", "incident_rate"]:
            delta = ns["deltas"][metric]
            for field in [
                "current_value",
                "previous_value",
                "delta_absolute",
                "delta_percent",
                "direction",
                "source",
            ]:
                assert field in delta, f"delta {metric} missing {field}"
            assert delta["direction"] in {"up", "down", "neutral"}
            if delta["source"] == "unavailable":
                assert delta["direction"] == "neutral"
                assert delta["previous_value"] is None
                assert delta["delta_absolute"] is None
                assert delta["delta_percent"] is None

    def test_governorate_breakdown_is_list(self):
        resp = self._dashboard_resp()
        assert resp.status_code == 200
        breakdown = resp.json()["governorate_breakdown"]
        assert isinstance(breakdown, list)
        if breakdown:
            row = breakdown[0]
            for field in ["governorate", "kindergarten_count", "children_count",
                          "attendance_rate", "incident_rate", "governance_score"]:
                assert field in row, f"GovernorateMetrics missing: {field}"

    def test_admin_governorate_options_endpoint_contract(self):
        resp = self.client.get("/api/admin/options/governorates")
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:200]}"

        data = resp.json()
        assert set(data) == {"governorates"}
        assert isinstance(data["governorates"], list)
        assert data["governorates"], "Expected at least the Amman governorate from sample_kindergarten"

        ids = []
        for row in data["governorates"]:
            assert set(row) == {"id", "name_ar", "name_en"}, row
            assert isinstance(row["id"], str) and row["id"], row
            assert isinstance(row["name_ar"], str) and row["name_ar"], row
            assert isinstance(row["name_en"], str) and row["name_en"], row
            assert row["id"] == row["name_ar"], row
            assert "[object Object]" not in " ".join(map(str, row.values())), row
            ids.append(row["id"])

        assert ids == sorted(ids), ids
        second_resp = self.client.get("/api/admin/options/governorates")
        assert second_resp.status_code == 200
        second_ids = [row["id"] for row in second_resp.json()["governorates"]]
        assert second_ids == ids

        amman = next((row for row in data["governorates"] if row["id"] == "عمان"), None)
        assert amman is not None
        assert amman["name_ar"] == "عمان"
        assert amman["name_en"] == "Amman"

    def test_governance_distribution_schema(self):
        resp = self._dashboard_resp()
        assert resp.status_code == 200
        dist = resp.json()["governance_distribution"]
        for key in ["green", "amber", "red"]:
            assert key in dist, f"governance_distribution missing: {key}"
            assert isinstance(dist[key], int)

    def test_time_series_format(self):
        resp = self._dashboard_resp()
        assert resp.status_code == 200
        for series_key in ["attendance_trend", "incident_trend"]:
            series = resp.json()[series_key]
            assert isinstance(series, list)
            if series:
                assert "date" in series[0]
                assert "value" in series[0]

    def test_invalid_date_range_returns_400(self):
        resp = self.client.get(
            "/api/analytics/dashboard-data?period_start=2025-12-31&period_end=2025-01-01"
        )
        assert resp.status_code == 400

    def test_date_range_exceeding_365_days_returns_400(self):
        today = date.today()
        start = today - timedelta(days=400)
        resp = self.client.get(
            f"/api/analytics/dashboard-data?period_start={start}&period_end={today}"
        )
        assert resp.status_code == 400

    def test_missing_date_params_returns_422(self):
        resp = self.client.get("/api/analytics/dashboard-data")
        assert resp.status_code == 422

    def test_risk_radar_is_list(self):
        resp = self._dashboard_resp()
        assert resp.status_code == 200
        assert isinstance(resp.json()["risk_radar"], list)

    def test_frontend_kpi_id_to_backend_field_mapping(self):
        kpi_map = {
            "totalKg": "total_kindergartens",
            "totalChildren": "total_children",
            "avgAttendance": "attendance_rate",
            "incidentRate": "incident_rate",
            "enrollmentRate": "enrollment_rate",
        }
        resp = self._dashboard_resp()
        assert resp.status_code == 200
        summary = resp.json()["network_summary"]
        for kpi_id, api_field in kpi_map.items():
            assert api_field in summary, \
                f"Frontend KPI #{kpi_id} maps to API field '{api_field}' — missing from response"


class TestAnalyticsEdgeCases:
    """Test frontend resilience to edge-case API responses."""

    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user, sample_kindergarten):
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.client = client
        yield
        app.dependency_overrides.clear()

    def test_dashboard_data_returns_valid_structure_with_minimal_data(self):
        today = date.today()
        start = today - timedelta(days=30)
        resp = self.client.get(
            f"/api/analytics/dashboard-data?period_start={start}&period_end={today}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["governorate_breakdown"], list)
        assert isinstance(data["risk_radar"], list)


class TestHelpModalIntegration:
    """Verify the admin help modal is wired into the shared admin shell."""

    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user):
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.client = client
        yield
        app.dependency_overrides.clear()

    def test_help_modal_component_file_exists(self):
        assert os.path.exists("templates/components/help_modal.html")

    def test_help_modal_rendered_exactly_once(self):
        resp = self.client.get("/admin/analytics")
        assert resp.text.count('id="helpExpressModal"') == 1

    def test_admin_header_has_help_button_targeting_help_modal(self):
        resp = self.client.get("/admin/analytics")
        assert 'data-bs-target="#helpExpressModal"' in resp.text
        assert "bi bi-question-circle" in resp.text

    def test_help_modal_is_included_before_extra_scripts(self):
        resp = self.client.get("/admin/analytics")
        modal_pos = resp.text.index('id="helpExpressModal"')
        extra_scripts_pos = resp.text.index("tablesort@5.3.0")
        assert modal_pos < extra_scripts_pos

    def test_pagehelpcontent_has_data_help_title(self):
        resp = self.client.get("/admin/analytics")
        assert 'data-help-title=' in resp.text

    def test_dashboard_submenu_no_stale_system_health_link(self):
        resp = self.client.get("/admin/analytics")
        assert "System Health" not in resp.text
        assert "صحة النظام" not in resp.text

    def test_admin_analytics_nav_link_is_not_duplicated(self):
        resp = self.client.get("/admin/analytics")
        assert resp.text.count('href="/admin/analytics"') == 1


class TestAnalyticsTrendDeltaIntegrity:
    """Verify trend indicators use backend previous-period deltas."""

    def test_forbidden_console_and_mock_trend_text_absent(self):
        with open("static/js/admin_analytics.js", "r", encoding="utf-8") as f:
            js = f.read()
        assert not re.search(r"console\.(log|info|debug|warn)", js)
        assert "mock" not in js.lower()
        assert "fake trend" not in js.lower()

    def test_governorate_option_normalizer_exists_and_is_used(self):
        with open("static/js/admin_analytics.js", "r", encoding="utf-8") as f:
            js = f.read()
        assert "function normalizeGovernorateOption(option, locale)" in js
        assert "normalizeGovernorateOption(g, locale)" in js
        assert "name_ar" in js and "name_en" in js

    def test_update_trend_indicators_uses_summary_deltas(self):
        with open("static/js/admin_analytics.js", "r", encoding="utf-8") as f:
            js = f.read()
        assert "summary?.deltas?.attendance_rate" in js
        assert "summary?.deltas?.incident_rate" in js
        assert "summary?.deltas?.total_kindergartens" in js
        assert "Math.max(totalKg" not in js


class TestAdminAnalyticsGovernorateNormalizer:
    """Verify the admin analytics governorate option normalizer contract."""

    @staticmethod
    def _normalizer_source():
        with open("static/js/admin_analytics.js", "r", encoding="utf-8") as f:
            js = f.read()

        match = re.search(
            r"function normalizeGovernorateOption\(option, locale\) \{"
            r"(?P<body>[\s\S]*?)"
            r"\n\}\n\nfunction adminAnalyticsLiteral",
            js,
        )
        assert match, "normalizeGovernorateOption not found in static/js/admin_analytics.js"
        return f"function normalizeGovernorateOption(option, locale) {{{match.group('body')}\n}}"

    @staticmethod
    def _run_normalizer(option, locale="en-US"):
        if shutil.which("node") is None:
            pytest.skip("node is required to execute admin_analytics.js normalizer")

        source = TestAdminAnalyticsGovernorateNormalizer._normalizer_source()
        script = f"""
const normalizeGovernorateOption = {source};
const result = normalizeGovernorateOption({json.dumps(option)}, {json.dumps(locale)});
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            encoding="utf-8",
            check=True,
            timeout=10,
        )
        return json.loads(completed.stdout)

    def test_normalizes_supported_and_fallback_shapes_without_object_labels(self):
        cases = [
            ({"id": "amman", "name_ar": "عمان", "name_en": "Amman"}, "en-US", {"value": "amman", "label": "Amman"}),
            ({"value": "zarqa", "label": "الزرقاء"}, "ar-JO", {"value": "zarqa", "label": "الزرقاء"}),
            ({"value": "aqaba", "name": "العقبة"}, "ar-JO", {"value": "aqaba", "label": "العقبة"}),
            ("Ma'an", "en-US", {"value": "Ma'an", "label": "Ma'an"}),
            (None, "en-US", {"value": "", "label": ""}),
            ({"nested": {"text": "عمان"}}, "en-US", {"value": "", "label": ""}),
        ]

        for option, locale, expected in cases:
            result = self._run_normalizer(option, locale)
            serialized = json.dumps(result, ensure_ascii=False)
            assert result == expected, f"{option!r} normalized to {result!r}"
            assert "[object Object]" not in serialized, serialized


class TestBootstrapUtilityConsistency:
    """
    Validate that Bootstrap 5.3 utility classes used on the analytics page
    are consistent with admin design conventions and no custom/unresolved
    classes remain.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user):
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.client = client
        self.page = client.get("/admin/analytics").text
        yield
        app.dependency_overrides.clear()

    def test_no_badge_soft_classes_on_analytics(self):
        visible = self.page[self.page.index('class="analytics-dashboard"'):]
        assert "badge-soft" not in visible, \
            "badge-soft classes are unstyled on admin pages — use bg-*-subtle instead"

    def test_bg_subtle_classes_used_correctly(self):
        assert "bg-warning-subtle" in self.page
        assert "bg-success-subtle" in self.page

    def test_bootstrap_responsive_classes_present(self):
        for pattern in [r'col-md-\d+', r'col-lg-\d+']:
            assert re.search(pattern, self.page), f"Missing responsive class: {pattern}"

    def test_card_shadow_classes_consistent(self):
        dashboard = self.page[self.page.index('class="analytics-dashboard"'):]
        top_cards = re.findall(r'<div class="card h-100 [^"]*"', dashboard)
        for div in top_cards:
            assert "shadow-sm" in div, f"Top-level card '{div}' missing shadow-sm"

    def test_btn_classes_are_bootstrap_standard(self):
        dashboard = self.page[self.page.index('class="analytics-dashboard"'):]
        buttons = re.findall(r'<button[^>]*class="([^"]*)"', dashboard)
        for btn_class in buttons:
            is_btn = "btn " in btn_class or btn_class.startswith("btn-")
            if btn_class in ("btn-close",):
                continue
            assert is_btn, f"Button '{btn_class}' not using Bootstrap btn base"


class TestAdminCrossPageConsistency:
    """Verify key admin pages share the same Bootstrap class conventions."""

    def test_all_admin_pages_extend_admin_base(self):
        for tmpl in ["admin/analytics/dashboard.html",
                      "admin/analytics/reports.html",
                      "admin_dashboard.html"]:
            path = os.path.join("templates", tmpl)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    assert '{% extends "admin_base.html" %}' in f.read(), \
                        f"{tmpl} does not extend admin_base.html"

    def test_analytics_pages_load_admin_analytics_js(self):
        for tmpl in ["templates/admin/analytics/dashboard.html",
                      "templates/admin/analytics/reports.html"]:
            if os.path.exists(tmpl):
                with open(tmpl, "r", encoding="utf-8") as f:
                    assert "admin_analytics.js" in f.read(), \
                        f"{tmpl} does not load admin_analytics.js"


class TestAnalyticsContractSchemathesis:
    """
    Lightweight inline schemathesis-style contract testing.
    Validates response shapes and value ranges.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user, sample_kindergarten):
        app.dependency_overrides[get_current_user] = lambda: admin_user
        self.client = client
        yield
        app.dependency_overrides.clear()

    def _resp(self):
        today = date.today()
        start = today - timedelta(days=30)
        resp = self.client.get(
            f"/api/analytics/dashboard-data?period_start={start}&period_end={today}"
        )
        assert resp.status_code == 200
        return resp.json()

    def test_consolidated_response_shape(self):
        data = self._resp()
        assert set(data.keys()) >= {
            "network_summary", "governorate_breakdown", "attendance_trend",
            "incident_trend", "risk_radar", "governance_distribution"
        }
        ns = data["network_summary"]
        assert isinstance(ns["total_kindergartens"], int)
        assert isinstance(ns["total_children"], int)
        assert isinstance(ns["attendance_rate"], (int, float))
        assert isinstance(ns["incident_rate"], (int, float))
        assert isinstance(ns["enrollment_rate"], (int, float))
        gd = data["governance_distribution"]
        for k in ["green", "amber", "red"]:
            assert isinstance(gd[k], int)

    def test_governorate_breakdown_values_in_valid_ranges(self):
        data = self._resp()
        for row in data["governorate_breakdown"]:
            assert 0 <= row["attendance_rate"] <= 100, \
                f"attendance_rate out of range for {row['governorate']}"
            assert 0 <= row["governance_score"] <= 100, \
                f"governance_score out of range for {row['governorate']}"


PLAYWRIGHT_E2E_SPEC = """
Playwright E2E Test Specifications for /admin/analytics
=======================================================
Execute when Playwright is installed in CI.

import { test, expect } from '@playwright/test';

test.describe('Admin Analytics Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/api/dev/auto-login?role=admin');
    await page.goto('/admin/analytics');
    await page.waitForLoadState('networkidle');
  });

  test('KPI cards render with numeric values (not skeleton loaders)', async ({ page }) => {
    for (const id of ['totalKg', 'totalChildren', 'avgAttendance', 'incidentRate']) {
      const el = page.locator(`#${id}`);
      await expect(el).toBeVisible();
      await expect(el).not.toContainText('skeleton');
    }
  });

  test('Governorate table populates with data rows', async ({ page }) => {
    const tbody = page.locator('#governorateTableBody');
    await expect(tbody.locator('tr').first()).toBeVisible({ timeout: 10000 });
    await expect(tbody).not.toContainText('skeleton');
  });

  test('Trend chart canvas renders without JS errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    await expect(page.locator('#trendChart')).toBeVisible();
    await page.waitForTimeout(2000);
    expect(errors.filter(e => !e.includes('401') && !e.includes('AbortError'))).toHaveLength(0);
  });

  test('Error state hidden on successful load', async ({ page }) => {
    await expect(page.locator('#trendChartError')).not.toHaveClass(/show/);
  });

  test('Retry button works after forced API failure', async ({ page }) => {
    await page.route('**/api/analytics/**', route => route.abort());
    await page.reload();
    const retryBtn = page.locator('#trendChartError button');
    await expect(retryBtn).toBeVisible({ timeout: 10000 });
    await page.unroute('**/api/analytics/**');
    await retryBtn.click();
    await expect(page.locator('#trendChartOverlay')).toHaveClass(/d-none/);
  });

  test('RTL layout verified via computed style', async ({ page }) => {
    const dir = await page.getAttribute('html', 'dir');
    if (dir === 'rtl') {
      const textAlign = await page.locator('.analytics-dashboard .card').first()
        .evaluate(el => getComputedStyle(el).textAlign);
      expect(['right', 'start'].includes(textAlign)).toBeTruthy();
    }
  });

  test('Governorate filter changes data', async ({ page }) => {
    const sel = page.locator('#governorateFilter');
    if (await sel.locator('option').count() > 1) {
      await sel.selectOption({ index: 1 });
      await page.waitForTimeout(2000);
      await expect(page.locator('#governorateTableBody tr').first()).toBeVisible();
    }
  });

  test('Export modal opens with all report types', async ({ page }) => {
    await page.locator('[data-bs-target="#exportModal"]').click();
    await expect(page.locator('#exportModal')).toBeVisible();
    await expect(page.locator('#exportModal select option')).toHaveCount(6);
  });

  test('Last-updated timestamp shows after load', async ({ page }) => {
    await expect(page.locator('#analyticsLastUpdated')).not.toContainText('Loading');
  });

  test('No duplicate Chart.js script tags', async ({ page }) => {
    const count = await page.locator('script[src*="chart.js"]').count();
    expect(count).toBeLessThanOrEqual(1);
  });

  test('Forecast cards show values', async ({ page }) => {
    for (const id of ['attendanceForecast', 'incidentForecast', 'enrollmentForecast']) {
      const text = await page.locator(`#${id}`).textContent();
      expect(text.trim()).not.toBe('');
    }
  });
});
"""
