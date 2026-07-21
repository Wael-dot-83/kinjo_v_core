from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "help_center.html"
JS = ROOT / "static" / "js" / "admin_help_center.js"


def test_help_center_template_is_data_driven_and_does_not_force_direction():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "help_meta" in html
    assert "help_coverage" in html
    assert "help_topics" in html
    assert "help_glossary" in html
    assert "help_faqs" in html
    assert 'class="admin-page-container" dir="rtl"' not in html
    assert "data-help-nav-link" in html
    assert "data-help-prev-link" in html
    assert "data-help-next-link" in html
    assert "data-help-coverage-row" in html
    assert "helpResultsCount" in html
    assert "helpNoResults" in html
    assert "helpLiveRegion" in html


def test_help_center_template_does_not_publish_unverified_contact_details():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "support@" not in html
    assert "+962" not in html
    assert "helpdesk@example.org" not in html
    assert "Report inaccurate content" in html or "الإبلاغ عن محتوى غير دقيق" in html


def test_help_center_js_contains_normalization_search_and_history_behaviour():
    js = JS.read_text(encoding="utf-8")
    assert "normalizeArabic" in js
    assert "buildNormalizedIndexMap" in js
    assert "helpClear" in js
    assert "helpResultsCount" in js
    assert "helpNoResults" in js
    assert "history.replaceState" in js
    assert "IntersectionObserver" in js
    assert "updateTopicNavigation" in js
    assert "aria-current" in js
