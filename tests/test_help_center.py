# -*- coding: utf-8 -*-
"""Help Center page and platform terminology contract tests."""
import subprocess
from pathlib import Path

import pytest

from main import app
from dependencies import get_current_user_or_redirect

ROOT = Path(__file__).resolve().parents[1]

HELP_SECTIONS = [
    "نبذة عن النظام",
    "البدء السريع",
    "إدارة الحضانات",
    "إدارة الأطفال",
    "إدارة الطلبات",
    "الحوكمة والامتثال",
    "التحليلات والتقارير",
    "الأسئلة الشائعة",
    "دليل المصطلحات",
    "التواصل والدعم",
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
        encoding="utf-8",
    ).stdout.splitlines()
    offenders = []
    for rel in tracked:
        if not (rel.startswith(("templates/", "static/")) or rel.endswith(".py")):
            continue
        if rel.startswith(("static/vendor/", "docs/", "GWS/")):
            continue
        path = ROOT / rel
        if path.suffix.lower() not in {".py", ".html", ".js", ".json", ".css"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "رياض الأطفال" in text or "رياض أطفال" in text:
            offenders.append(rel)
    assert not offenders, f"Legacy term found in: {offenders}"
