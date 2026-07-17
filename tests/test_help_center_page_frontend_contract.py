from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "help_center.html"


def test_dead_breadcrumb_block_removed():
    """admin_base.html declares no {% block breadcrumb %} placeholder
    (only title/extra_head/page_header/content/extra_scripts exist), so
    this page's breadcrumb markup was silently discarded by Jinja on
    every render -- the 4th confirmed occurrence of this bug class in the
    USWDS/WCAG audit series. Removed as dead, unreachable code."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_glossary_table_has_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 2


def test_html_divs_are_balanced_in_content_block():
    html = TEMPLATE.read_text(encoding="utf-8")
    content = html.split("{% block content %}")[1].split("{% endblock %}")[0]
    opens = content.count("<div")
    closes = content.count("</div>")
    assert opens == closes, f"unbalanced <div> tags: {opens} opens vs {closes} closes"


def test_help_center_is_bilingual_and_does_not_force_direction():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% if ui_lang == 'en' %}" in html
    assert 'class="admin-page-container" dir="rtl"' not in html
    assert "Admin Help Center" in html
    assert "مركز مساعدة المسؤول" in html


def test_help_center_does_not_publish_unverified_contact_details():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "support@" not in html
    assert "+962" not in html
