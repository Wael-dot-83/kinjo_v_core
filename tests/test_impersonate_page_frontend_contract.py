from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "impersonate.html"
ROUTER = ROOT / "routers" / "admin_impersonation.py"


def test_dead_breadcrumb_block_removed():
    """admin_base.html declares no {% block breadcrumb %} placeholder
    (only title/extra_head/page_header/content/extra_scripts exist), so
    this page's breadcrumb markup was silently discarded by Jinja on
    every render -- the 5th confirmed occurrence of this bug class across
    the USWDS/WCAG audit series."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_audit_query_uses_auditaction_constants_not_raw_strings():
    """impersonation_audit() filtered AuditLog.action against raw string
    literals ["IMPERSONATION_START", "IMPERSONATION_END"] instead of the
    AuditAction enum-like constants already imported and used elsewhere in
    this same file -- functionally identical today (the constants are
    plain strings with matching values) but a maintenance foot-gun per
    CLAUDE.md's "use AuditAction constants -- never raw action strings"
    convention."""
    content = ROUTER.read_text(encoding="utf-8")
    assert '["IMPERSONATION_START", "IMPERSONATION_END"]' not in content
    assert "[AuditAction.IMPERSONATION_START, AuditAction.IMPERSONATION_END]" in content
