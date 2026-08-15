from pathlib import Path

from main import app

ROOT = Path(__file__).resolve().parents[1]


def relative_luminance(hex_color):
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground, background):
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def iter_effective_routes(route, prefix=""):
    included = getattr(route, "original_router", None)
    context = getattr(route, "include_context", None)
    if included is not None and context is not None:
        next_prefix = f"{prefix}{context.prefix or ''}"
        for child in included.routes:
            yield from iter_effective_routes(child, next_prefix)
        return
    path = getattr(route, "path", None)
    if path:
        yield route, f"{prefix}{path}"


def route_pairs():
    pairs = set()
    for route in app.routes:
        for effective_route, path in iter_effective_routes(route):
            methods = getattr(effective_route, "methods", None)
            if not methods:
                continue
            for method in methods - {"HEAD", "OPTIONS"}:
                pairs.add((method, path))
    return pairs


# Macro libraries are not pages and must not extend a layout. The project
# keeps shared macros in templates/components/, and b3b43eb added a
# _components/ directory beside the agency-reports pages that use them.
#
# The discriminator has to be the directory, not "does the file contain
# {% extends %}": a page that forgot to extend also has no extends line, and
# that omission is precisely the defect this test exists to catch, so it
# cannot also be the rule for deciding what to check.
_PARTIAL_DIRS = {"components", "_components"}


def _is_partial(path: Path) -> bool:
    return any(part in _PARTIAL_DIRS for part in path.parts)


def _extends_admin_base(content: str) -> bool:
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return "admin_base.html" in first_line


def _admin_templates():
    return sorted((ROOT / "templates" / "admin").rglob("*.html"))


def test_admin_templates_under_templates_admin_extend_admin_base():
    checked = 0
    for path in _admin_templates():
        if _is_partial(path):
            continue
        content = path.read_text(encoding="utf-8-sig")
        assert _extends_admin_base(content), (
            f"{path.relative_to(ROOT)} does not extend admin_base.html"
        )
        checked += 1
    # Guards against a future refactor that makes the glob or the exemption
    # match everything and leaves this loop asserting over nothing.
    assert checked > 0, "no admin page templates were checked"


def test_admin_partial_directories_contain_only_real_partials():
    """The exemption above is granted by directory name, so the directory must
    not become a place to hide a page that skips the layout check.

    Anything living in a partials directory has to actually be a macro
    library: macros, no layout inheritance, no top-level page markup.
    """
    for path in _admin_templates():
        if not _is_partial(path):
            continue
        content = path.read_text(encoding="utf-8-sig")
        rel = path.relative_to(ROOT)
        assert "{% macro" in content, f"{rel} is in a partials dir but defines no macro"
        assert "{% extends" not in content, f"{rel} is a partial and must not extend a layout"
        lowered = content.lower()
        for tag in ("<html", "<body", "{% block content"):
            assert tag not in lowered, f"{rel} looks like a page, not a partial ({tag})"


def test_extends_check_rejects_a_page_that_forgot_the_layout():
    """Positive/negative control for the rule itself, so relaxing the scope
    above cannot quietly stop catching the original defect."""
    assert _extends_admin_base("{% extends 'admin_base.html' %}")
    assert _extends_admin_base('{% extends "admin/admin_base.html" %}')
    assert not _extends_admin_base("<div>a page that forgot to extend</div>")
    assert not _extends_admin_base("")


def test_partial_detection_only_exempts_partial_directories():
    """A page must not be exempted just because it sits under templates/admin."""
    assert _is_partial(Path("templates/admin/agency_reports/_components/x.html"))
    assert _is_partial(Path("templates/components/date-range-filter.html"))
    assert not _is_partial(Path("templates/admin/governance_reports.html"))
    assert not _is_partial(Path("templates/admin/agency_reports/report.html"))


def test_audit_log_admin_api_aliases_are_registered():
    routes = route_pairs()
    for path in ("/api/audit-logs", "/api/audit-logs/export"):
        assert ("GET", path) in routes
    for path in ("/api/admin/audit-logs", "/api/admin/audit-logs/export"):
        assert ("GET", path) in routes


def test_audit_log_admin_api_aliases_enforce_admin_access(client, admin_token, manager_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    assert client.get("/api/admin/audit-logs", headers=headers).status_code == 200
    assert client.get("/api/admin/audit-logs/export?format=json&period=all", headers=headers).status_code == 200

    manager_headers = {"Authorization": f"Bearer {manager_token}"}
    assert client.get("/api/admin/audit-logs", headers=manager_headers).status_code == 403
    assert client.get("/api/admin/audit-logs/export?format=json&period=all", headers=manager_headers).status_code == 403


def test_audit_log_export_uses_admin_namespace_without_bearer_csrf_sentinel():
    content = (ROOT / "static" / "js" / "audit-logs.js").read_text(encoding="utf-8")
    assert "/api/admin/audit-logs/export" in content
    assert "Authorization:" not in content


def test_key_accessibility_contrast_pairs_meet_wcag_aa():
    assert contrast_ratio("#1e293b", "#f8fafc") >= 4.5
    assert contrast_ratio("#64748b", "#ffffff") >= 4.5
    assert contrast_ratio("#64748b", "#f8fafc") >= 4.5
    assert contrast_ratio("#cbd5e1", "#111827") >= 4.5
    assert contrast_ratio("#e5e7eb", "#0f172a") >= 4.5
    assert contrast_ratio("#ffffff", "#2563eb") >= 4.5
    assert contrast_ratio("#ffffff", "#1d4ed8") >= 4.5
    assert contrast_ratio("#065f46", "#d1fae5") >= 4.5
    assert contrast_ratio("#92400e", "#fef3c7") >= 4.5
    assert contrast_ratio("#991b1b", "#fee2e2") >= 4.5
    assert contrast_ratio("#155e75", "#cffafe") >= 4.5
