"""Help Center page and platform terminology contract tests."""

import re
import subprocess
from pathlib import Path
from html import escape

import pytest

from config import settings
from dependencies import get_current_user_or_redirect
from help_center_manifest import HELP_CENTER_GLOSSARY, HELP_CENTER_TOPICS
from main import app


ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE = ROOT / "templates" / "admin_base.html"
HELP_TEMPLATE = ROOT / "templates" / "admin" / "help_center.html"
HELP_JS = ROOT / "static" / "js" / "admin_help_center.js"


def _render_help(client, lang: str | None = None) -> str:
    url = "/admin/help"
    if lang:
        url += f"?lang={lang}"
    return client.get(url).text


def _sidebar_routes() -> set[str]:
    html = ADMIN_BASE.read_text(encoding="utf-8")
    sidebar = html[html.index('id="admin-sidebar"') : html.index("</aside>", html.index('id="admin-sidebar"'))]
    return set(re.findall(r'"href":\s*"([^"]+)"', sidebar))


class TestHelpCenter:
    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user):
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.client = client
        yield
        app.dependency_overrides.clear()

    def test_help_center_renders_for_admins_only(self):
        assert self.client.get("/admin/help").status_code == 200
        app.dependency_overrides[get_current_user_or_redirect] = lambda: type("User", (), {"role": type("Role", (), {"value": "PARENT"})()})()
        try:
            response = self.client.get("/admin/help", follow_redirects=False)
        finally:
            app.dependency_overrides.clear()
        assert response.status_code in {302, 307}

    def test_help_center_coverage_matches_admin_navigation(self):
        help_routes = {topic["route"] for topic in HELP_CENTER_TOPICS}
        assert help_routes == _sidebar_routes()
        page = _render_help(self.client)
        for topic in HELP_CENTER_TOPICS:
            assert f'id="{topic["id"]}"' in page
            assert topic["title"]["ar"] in page

    def test_help_center_english_and_arabic_topic_coverage_match(self):
        english = _render_help(self.client, "en")
        arabic = _render_help(self.client, "ar")
        for topic in HELP_CENTER_TOPICS:
            assert escape(topic["title"]["en"]) in english
            assert topic["title"]["ar"] in arabic
        assert english.count('class="help-topic card p-4 mb-4"') == len(HELP_CENTER_TOPICS) + 2
        assert arabic.count('class="help-topic card p-4 mb-4"') == len(HELP_CENTER_TOPICS) + 2
        assert 'class="admin-page-container" dir="rtl"' not in english

    def test_help_center_support_details_render_conditionally(self, monkeypatch):
        monkeypatch.setattr(settings, "SUPPORT_CONTACT_EMAIL", "helpdesk@example.org")
        monkeypatch.setattr(settings, "SUPPORT_CONTACT_PHONE", "+962700000000")
        page = _render_help(self.client, "en")
        assert "helpdesk@example.org" in page
        assert "+962700000000" in page

        monkeypatch.setattr(settings, "SUPPORT_CONTACT_EMAIL", "")
        monkeypatch.setattr(settings, "SUPPORT_CONTACT_PHONE", "")
        page = _render_help(self.client, "en")
        assert "helpdesk@example.org" not in page
        assert "+962700000000" not in page

    def test_help_center_matches_daily_report_and_metrics_contract(self):
        topics = {topic["id"]: topic for topic in HELP_CENTER_TOPICS}
        daily = topics["daily-report-organization"]["search_terms"]
        compose = topics["compose-message"]["search_terms"]
        observability = topics["observability"]["search_terms"]
        kpi = topics["network-kpis"]["search_terms"]
        assert "does not create send schedules" in daily
        assert "recalculates recipients" in compose
        assert "p95 latency" in observability
        assert "cache-hit rate" in observability
        assert "numerator" in kpi
        assert "denominator" in kpi

    def test_help_center_has_balanced_markup_and_no_mojibake(self):
        page = _render_help(self.client, "en")
        assert page.count("<div") == page.count("</div>")
        assert "Admin Help Center" in page
        assert "Ã" not in page
        assert "â€”" not in page


def test_help_center_glossary_contains_required_terms():
    terms = {item["term"]["en"] for item in HELP_CENTER_GLOSSARY}
    required = {
        "Scope", "Coverage", "Freshness", "Reference ID", "Numerator", "Denominator",
        "Measurement period", "Data quality", "Insufficient data", "Benchmark",
        "Percentile", "Classification", "Forecast", "Anomaly", "Risk score",
        "Severity", "SLA", "Attendance rate", "Capacity utilization",
        "Governance score", "Draft", "Sent", "Approved", "Sent to Parent",
        "Rejected", "Returned", "Active", "Frozen", "Deleted",
    }
    assert required.issubset(terms)


def test_help_center_js_contains_search_and_accessibility_behaviors():
    js = HELP_JS.read_text(encoding="utf-8")
    assert "normalizeArabic" in js
    assert "aria-live" not in js  # live region is rendered in HTML, not JS
    assert "helpClear" in js
    assert "helpResultsCount" in js
    assert "helpNoResults" in js
    assert "history.replaceState" in js
    assert "IntersectionObserver" in js
    assert 'replace(/[\\u0622\\u0623\\u0625\\u0671]/g, "ا")' in js
    assert 'setAttribute("aria-current", "page")' in js


def test_legacy_kindergarten_term_absent_from_ui_sources():
    """The term رياض الأطفال was replaced platform-wide by الحضانات."""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL, check=True,
    ).stdout.splitlines()
    offenders = []
    unreadable = []
    self_path = Path(__file__).resolve()
    for rel in tracked:
        if not (rel.startswith(("templates/", "static/")) or rel.endswith(".py")):
            continue
        if rel.startswith(("static/vendor/", "docs/", "GWS/")):
            continue
        path = ROOT / rel
        if path.resolve() == self_path:
            continue
        if path.suffix.lower() not in {".py", ".html", ".js", ".json", ".css"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
            unreadable.append(rel)
        except OSError:
            unreadable.append(rel)
            continue
        if "رياض الأطفال" in text or "رياض أطفال" in text:
            offenders.append(rel)
    assert not offenders, f"Legacy term found in: {offenders}"
    assert not unreadable, (
        f"these files could not be read as UTF-8, so the scan above could not "
        f"vouch for them: {unreadable}"
    )
