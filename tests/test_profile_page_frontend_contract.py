from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "profile.html"


def test_kinjo_lang_is_set():
    """window.KINJO_LANG was read (const LANG = window.KINJO_LANG || 'ar')
    but never assigned anywhere on this page or in admin_base.html, so
    LANG always fell back to 'ar' regardless of the admin's actual
    language, producing Arabic toasts/aria-labels for English-mode
    admins."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'window.KINJO_LANG = "{{ ui_lang }}"' in html


def test_dead_breadcrumb_block_removed():
    """admin_base.html declares no {% block breadcrumb %} placeholder
    (only title/extra_head/page_header/content/extra_scripts exist), so
    this page's breadcrumb markup was silently discarded by Jinja on
    every render -- dead code, removed rather than left orphaned."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_misleading_impersonation_toggle_removed():
    """The "Allow Impersonation" toggle only wrote to localStorage
    (per-browser, not per-account) with zero backend effect -- a control
    that visually implied a real security capability but did nothing. No
    real per-user impersonation-opt-out field exists anywhere in the
    schema."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "qs-impersonation" not in html


def test_no_duplicate_banner_landmark():
    """The profile-hero div had an explicit role="banner" nested inside
    <main>, which already sits below admin_base.html's <header> (an
    implicit banner landmark) -- a second explicit banner produced a
    duplicate/invalid landmark for assistive tech."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'role="banner"' not in html


def test_activity_table_has_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.count('scope="col"') == 4


def test_password_toggle_buttons_have_distinguishing_labels():
    """All three show/hide password buttons shared the identical
    aria-label="Show/hide password", including the JS that dynamically
    updates it on click -- a screen-reader user tabbing through got three
    indistinguishable button announcements."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "Show/hide current password" in html
    assert "Show/hide new password" in html
    assert "Show/hide confirm password" in html
    assert "PW_FIELD_LABEL" in html


def test_html_divs_are_balanced_in_content_block():
    html = TEMPLATE.read_text(encoding="utf-8")
    content = html.split("{% block content %}")[1].split("{% endblock %}")[0]
    opens = content.count("<div")
    closes = content.count("</div>")
    assert opens == closes, f"unbalanced <div> tags: {opens} opens vs {closes} closes"
