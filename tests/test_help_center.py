# -*- coding: utf-8 -*-
"""Help Center page and platform terminology contract tests."""
import subprocess
from pathlib import Path

import pytest

from main import app
from dependencies import get_current_user_or_redirect

ROOT = Path(__file__).resolve().parents[1]

HELP_SECTIONS = [
    "نبذة عن وحدة الإدارة",
    "مؤشرات لوحة التحكم",
    "إدارة المستخدمين",
    "إدارة الحضانات",
    "استيراد البيانات",
    "التواصل",
    "التقارير اليومية",
    "الحوادث والسلامة",
    "التحليلات والتقارير",
    "الحوكمة والتصنيف",
    "الأمان والتدقيق",
    "الأسئلة الشائعة",
    "دليل المصطلحات",
    "الدعم",
]


class TestHelpCenter:
    @pytest.fixture(autouse=True)
    def _setup(self, client, admin_user):
        app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
        self.client = client
        yield
        app.dependency_overrides.clear()

    def test_help_center_renders(self):
        res = self.client.get("/admin/help")
        assert res.status_code == 200

    def test_help_center_contains_all_sections(self):
        page = self.client.get("/admin/help").text
        for section in HELP_SECTIONS:
            assert section in page, f"Help section missing: {section}"

    def test_help_center_has_at_least_20_faqs(self):
        page = self.client.get("/admin/help").text
        assert page.count('class="accordion-item faq-item"') >= 20

    def test_help_center_is_complete_in_english_and_direction_is_inherited(self):
        page = self.client.get("/admin/help?lang=en").text
        assert "Admin Help Center" in page
        assert "Dashboard metrics" in page
        assert "Users Logged In Today" in page
        assert "Daily Reports Analytics" in page
        assert "Security and audit" in page
        assert '<div class="admin-page-container" dir="rtl">' not in page

    def test_help_center_matches_real_workflows(self):
        page = self.client.get("/admin/help?lang=en").text
        assert "protected direct reset" in page
        assert "not a ticket-reply system" in page
        assert 'href="/reports/analytics"' in page
        assert 'href="/admin/audit-logs"' in page
        assert "never be deleted" not in page.lower()

    def test_help_center_linked_from_nav(self):
        page = self.client.get("/admin/dashboard").text
        assert '/admin/help' in page


def test_legacy_kindergarten_term_absent_from_ui_sources():
    """The term رياض الأطفال was replaced platform-wide by الحضانات.

    It must not reappear in any UI-facing source (templates, static, i18n,
    root services). Institution proper names inside datasets are exempt.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL, check=True,
    ).stdout.splitlines()
    offenders = []
    self_path = Path(__file__).resolve()
    for rel in tracked:
        if not (rel.startswith(("templates/", "static/")) or rel.endswith(".py")):
            continue
        if rel.startswith(("static/vendor/", "docs/", "GWS/")):
            continue
        path = ROOT / rel
        if path.resolve() == self_path:
            # This test's own source contains the banned string as a literal
            # to check against — excluding anything else would silently
            # narrow coverage, so only this file is skipped.
            continue
        if path.suffix.lower() not in {".py", ".html", ".js", ".json", ".css"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "رياض الأطفال" in text or "رياض أطفال" in text:
            offenders.append(rel)
    assert not offenders, f"Legacy term found in: {offenders}"
