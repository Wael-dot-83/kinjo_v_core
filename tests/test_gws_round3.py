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


def test_admin_templates_under_templates_admin_extend_admin_base():
    for path in (ROOT / "templates" / "admin").rglob("*.html"):
        content = path.read_text(encoding="utf-8-sig")
        first_line = next(line.strip() for line in content.splitlines() if line.strip())
        assert "admin_base.html" in first_line, f"{path.relative_to(ROOT)} does not extend admin_base.html"


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
