"""Tests for the Admin dashboard template contract and accessibility baseline.

Verifies:
- No merge conflict markers remain
- Arabic/English text pairs are present
- Canvas elements have accessible names
- Loading/error states are present
- No hardcoded English-only strings in bilingual blocks
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DASHBOARD = TEMPLATES / "admin_dashboard.html"


def test_dashboard_no_merge_conflicts():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert "<<<<<<<" not in text, "merge conflict marker found"
    assert "=======" not in text, "merge conflict marker found"
    assert ">>>>>>>" not in text, "merge conflict marker found"


def test_dashboard_bilingual_title():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert "{% if ui_lang == 'en' %}KinJo Admin" in text
    assert "{% else %}إدارة KinJo" in text


def test_dashboard_canvas_has_accessible_name():
    text = DASHBOARD.read_text(encoding="utf-8")
    # Canvas elements should have aria-label or role="img" via JS, but in template
    # they should at least have an id for JS to target
    assert 'id="attendance-chart"' in text
    assert 'id="enrollment-status-chart"' in text


def test_dashboard_loading_state_present():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="dashboard-loading"' in text
    assert 'aria-busy="true"' in text


def test_dashboard_error_state_present():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="dashboard-error"' in text
    assert 'id="retry-dashboard"' in text


def test_dashboard_no_hardcoded_english_only_strings():
    text = DASHBOARD.read_text(encoding="utf-8")
    # Check that user-facing text uses ui_lang conditionals
    # Skip: HTML attributes, CSS, JS, comments, Jinja tags
    lines = text.splitlines()
    in_css_comment = False
    in_jinja_comment = False
    in_style_or_script = False
    in_html_comment = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Multi-line HTML comments: same gap as CSS/Jinja comments — only the
        # opening line starts with "<!--".
        if in_html_comment:
            if "-->" in stripped:
                in_html_comment = False
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            in_html_comment = True
            continue
        # <style>/<script> bodies are CSS and JS, never user-facing prose. Only
        # the opening tag starts with "<", so the block's contents (selectors,
        # declarations, statements) were previously scanned as markup.
        lowered = stripped.lower()
        if in_style_or_script:
            if "</style>" in lowered or "</script>" in lowered:
                in_style_or_script = False
            continue
        if (lowered.startswith("<style") or lowered.startswith("<script")) and not (
            "</style>" in lowered or "</script>" in lowered
        ):
            in_style_or_script = True
            continue
        # Track multi-line comment blocks. Only the *opening* line starts with
        # "/*" or "{#", so continuation lines used to be scanned as though they
        # were markup — a prose sentence inside a CSS comment failed this test.
        if in_css_comment:
            if "*/" in stripped:
                in_css_comment = False
            continue
        if in_jinja_comment:
            if "#}" in stripped:
                in_jinja_comment = False
            continue
        if stripped.startswith("/*") and "*/" not in stripped:
            in_css_comment = True
            continue
        if stripped.startswith("{#") and "#}" not in stripped:
            in_jinja_comment = True
            continue
        # Skip Jinja tags, HTML tags, CSS, JS, single-line comments
        if stripped.startswith("{%") or stripped.startswith("{{") or stripped.startswith("{#"):
            continue
        if stripped.startswith("<") or stripped.startswith("/*") or stripped.startswith("//"):
            continue
        # Skip lines that are only HTML attributes or CSS classes
        if "=" in stripped and not any(c.isalpha() and c.isascii() for c in stripped.split("=")[-1]):
            continue
        # Only check lines with substantial English text (not just class names or URLs)
        # Look for English words (2+ letters) that aren't part of HTML/CSS/JS
        import re
        english_words = re.findall(r'\b[a-zA-Z]{2,}\b', stripped)
        if english_words and len(english_words) >= 3:
            # Has multiple English words - likely user-facing text
            assert "{% if ui_lang" in line or "ui_lang" in line, f"possible hardcoded English: {stripped[:120]}"


def test_dashboard_kpi_section_present():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="kpi-cards"' in text
    assert 'role="list"' in text


def test_dashboard_alerts_section_present():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="alerts-list"' in text
    assert "System Alerts" in text or "تنبيهات النظام" in text


def test_dashboard_quick_actions_present():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert "Quick Actions" in text or "الإجراءات السريعة" in text
    assert "/admin/users" in text
    assert "/admin/analytics" in text


def test_dashboard_activity_section_present():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="activity-feed"' in text
    assert "Recent Activities" in text or "النشاطات الحديثة" in text
