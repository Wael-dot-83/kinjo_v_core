import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOGS_TEMPLATE = ROOT / "templates" / "admin" / "audit_logs.html"
AUDIT_LOGS_JS = ROOT / "static" / "js" / "audit-logs.js"


def test_table_has_caption_and_column_scope():
    """The audit-logs table had no <caption> and no scope="col" on any of
    its 7 <th> elements."""
    html = AUDIT_LOGS_TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 7


def test_no_fictitious_cyberlume_classes():
    """cyberlume-glow-text, cyberlume-card, and cyberlume-table are not
    defined anywhere in the CSS — they rendered as plain unstyled markup."""
    html = AUDIT_LOGS_TEMPLATE.read_text(encoding="utf-8")
    assert "cyberlume" not in html


def test_no_raw_tailwind_utility_classes_on_form_controls():
    """The export modal's format/period <select> elements used a raw
    Tailwind-utility-class string that renders unstyled since Tailwind is
    never loaded on this page; they must use Bootstrap's form-select."""
    html = AUDIT_LOGS_TEMPLATE.read_text(encoding="utf-8")
    assert "bg-surface-container/50" not in html
    assert html.count('id="exportFormat"') == 1
    assert html.count('id="exportPeriod"') == 1
    assert 'class="form-select" id="exportFormat"' in html
    assert 'class="form-select" id="exportPeriod"' in html


def test_pdf_export_option_removed():
    """GET /api/admin/audit-logs/export declares
    format: str = Query("csv", pattern="^(csv|json)$") — pdf always fails
    with a 422, so offering it in the UI is a dead, always-broken option."""
    html = AUDIT_LOGS_TEMPLATE.read_text(encoding="utf-8")
    assert 'value="pdf"' not in html
    assert 'value="csv"' in html
    assert 'value="json"' in html


def test_export_format_endpoint_rejects_pdf():
    import audit_service

    sig = inspect.signature(audit_service.export_audit_logs)
    query = sig.parameters["format"].default
    pattern = next((m.pattern for m in query.metadata if hasattr(m, "pattern")), None)
    assert pattern == "^(csv|json)$"


def test_export_endpoint_accepts_the_visible_exact_date_filter():
    import audit_service

    sig = inspect.signature(audit_service.export_audit_logs)
    assert "date" in sig.parameters
    source = AUDIT_LOGS_JS.read_text(encoding="utf-8")
    assert 'date: document.getElementById("dateFilter").value' in source


def test_action_badge_classifier_covers_real_taxonomy_patterns():
    """getActionBadgeClass previously only matched CREATE/UPDATE/DELETE/
    LOGIN/LOGOUT/VIEW - none of which are real AuditAction values except
    LOGOUT. It must pattern-match the real ~100-constant taxonomy's naming
    conventions (e.g. USER_CREATED, LOGIN_FAILED, BACKUP_DELETED)."""
    js = AUDIT_LOGS_JS.read_text(encoding="utf-8")
    assert "getActionBadgeClass" in js
    for token in ["DENIED", "FAILED", "DELETED", "CREATED", "UPDATED", "HTTP_"]:
        assert token in js


def test_html_divs_are_balanced_in_content_block():
    """Both card sections had unbalanced <div> nesting: an inner wrapper
    div (position-relative) was opened but never closed before its parent
    card closed, corrupting the DOM structure for everything after it."""
    html = AUDIT_LOGS_TEMPLATE.read_text(encoding="utf-8")
    content = html.split("{% block content %}")[1].split("{% endblock %}")[0]
    opens = content.count("<div")
    closes = content.count("</div>")
    assert opens == closes, f"unbalanced <div> tags in content block: {opens} opens vs {closes} closes"
