import re
import runpy
from pathlib import Path

from main import app


ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE = ROOT / "templates" / "admin_base.html"
ADMIN_TEMPLATE_ROOT = ROOT / "templates" / "admin"
ADMIN_TEMPLATES = [
    ROOT / "templates" / "admin_dashboard.html",
    *[
        p
        for p in ADMIN_TEMPLATE_ROOT.rglob("*.html")
        if not any(part.startswith("_") for part in p.relative_to(ADMIN_TEMPLATE_ROOT).parts)
    ],
]
FIRST_PARTY_ADMIN_JS = [
    path
    for path in (ROOT / "static" / "js").glob("*.js")
    if path.name.startswith("admin_") or path.name in {"audit-logs.js", "kg_overview.js"}
]
LEGACY_KINJO_CSS = ROOT / "static" / "css" / "kinjo.css"


def _iter_effective_routes(route, prefix=""):
    included = getattr(route, "original_router", None)
    context = getattr(route, "include_context", None)
    if included is not None and context is not None:
        next_prefix = f"{prefix}{context.prefix or ''}"
        for child in included.routes:
            yield from _iter_effective_routes(child, next_prefix)
        return
    path = getattr(route, "path", None)
    if path:
        yield route, f"{prefix}{path}"


def _route_patterns():
    patterns = set()
    for route in app.routes:
        for effective_route, path in _iter_effective_routes(route):
            methods = getattr(effective_route, "methods", set()) or set()
            if not path or not methods:
                continue
            escaped = re.escape(path)
            escaped = re.sub(r"\\\{[^}]+\\\}", r"[^/?#]+", escaped)
            patterns.add(re.compile(f"^{escaped}(?:[?#].*)?$"))
    return patterns


def _is_registered_path(path):
    normalized = path.split("#", 1)[0]
    if not normalized or normalized == "#":
        return True
    return any(pattern.match(normalized) for pattern in _route_patterns())


def _registered_paths():
    paths = set()
    for route in app.routes:
        for effective_route, path in _iter_effective_routes(route):
            methods = getattr(effective_route, "methods", set()) or set()
            if path and methods:
                paths.add(path)
    return paths


def _is_registered_path_or_prefix(path):
    normalized = path.split("#", 1)[0].split("?", 1)[0]
    if _is_registered_path(normalized):
        return True
    # Strip a trailing slash so a base path used for JS string-concatenation
    # (e.g. "/api/admin/agency-reports/" + agencyCode + "/reports") is still
    # recognised as a prefix of registered routes like
    # "/api/admin/agency-reports/{agency_code}/reports". Without this the
    # f"{normalized}/" below would produce a double slash and never match.
    prefix = normalized.rstrip("/")
    return any(route_path.startswith(f"{prefix}/") for route_path in _registered_paths())


def test_effective_route_inventory_includes_nested_admin_routers():
    route_paths = _registered_paths()

    assert len(route_paths) >= 600
    assert "/admin/dashboard" in route_paths
    assert "/admin/kindergartens/new" in route_paths
    assert "/api/admin/users/{user_id:int}/admin-reset-password" in route_paths
    assert "/api/admin/charts/render" in route_paths


def test_no_duplicate_registered_method_path_pairs():
    seen = set()
    duplicates = set()
    for route in app.routes:
        for effective_route, path in _iter_effective_routes(route):
            for method in getattr(effective_route, "methods", set()) or set():
                if method in {"HEAD", "OPTIONS"}:
                    continue
                key = (method, path)
                if key in seen:
                    duplicates.add(key)
                seen.add(key)
    assert duplicates == set()


def test_generated_admin_api_reference_matches_registered_openapi():
    generator = runpy.run_path(str(ROOT / "scripts" / "manual-diagnostics" / "generate_admin_api_reference.py"))
    expected = generator["generate"]()
    actual = (ROOT / "docs" / "ADMIN_API_REFERENCE.md").read_text(encoding="utf-8")
    assert actual == expected


def _literal_paths(source):
    patterns = [
        r"""(?:href|src|action)=["']([^"'{}]+)["']""",
        r"""fetch(?:WithAuth)?\(\s*["'`]([^"'`$]+)["'`]""",
        r"""api\.(?:get|post|put|patch|delete)\(\s*["'`]([^"'`$]+)["'`]""",
        r"""["'`]((?:/api|/admin)/[^"'`$\s<>)]+)["'`]""",
    ]
    values = []
    for pattern in patterns:
        values.extend(re.findall(pattern, source))
    return values


def _local_paths(paths):
    ignored_prefixes = ("http://", "https://", "mailto:", "tel:", "javascript:", "data:")
    for path in paths:
        if path.startswith(ignored_prefixes) or path.startswith("#") or path == "":
            continue
        yield path


def _static_file_path(asset_path):
    clean = asset_path.split("?", 1)[0].split("#", 1)[0]
    if not clean.startswith("/static/"):
        return None
    return ROOT / clean.lstrip("/")


def test_admin_base_loads_csrf_aware_dependencies_in_order():
    source = ADMIN_BASE.read_text(encoding="utf-8")
    auth_index = source.index("/static/js/auth.js")
    api_index = source.index("/static/js/kinjo-api.js")
    assert '<meta name="csrf-token"' in source
    assert auth_index < api_index

    auth_source = (ROOT / "static" / "js" / "auth.js").read_text(encoding="utf-8")
    assert "window.fetch = async function patchedFetch" in auth_source
    assert "X-CSRF-Token" in auth_source
    assert "window.fetchWithAuth = fetchWithAuth" in auth_source

    api_source = (ROOT / "static" / "js" / "kinjo-api.js").read_text(encoding="utf-8")
    assert "fetchWithAuth(`${this.baseURL}${endpoint}`, options)" in api_source


def test_premium_admin_base_delegates_to_canonical_shell():
    source = (ROOT / "templates" / "admin_base_premium.html").read_text(encoding="utf-8")
    assert '{% extends "admin_base.html" %}' in source
    assert "tailwind.config" not in source
    assert "/auth/logout" not in source
    assert "WebGL Background" not in source


def test_legacy_fade_in_keeps_dashboard_content_visible():
    source = LEGACY_KINJO_CSS.read_text(encoding="utf-8")
    match = re.search(r"\.fade-in\s*\{(?P<body>[^}]+)\}", source)
    assert match is not None
    body = match.group("body")
    assert re.search(r"animation\s*:[^;]*(?:\bboth\b|\bforwards\b)", body)


def test_admin_alerts_use_english_labels_without_language_branches():
    source = (ROOT / "static" / "js" / "admin_alerts.js").read_text(encoding="utf-8")
    assert 'label: "Critical"' in source
    assert 'label: "Acknowledged"' in source
    assert 'toLocaleString("en-US")' in source
    assert "isRtl" not in source
    assert not any("\u0600" <= char <= "\u06ff" for char in source)


def test_admin_profile_uses_configured_csrf_cookie_name():
    source = (ROOT / "static" / "js" / "auth.js").read_text(encoding="utf-8")
    assert "kinjo_csrf_token" in source
    assert r"(?:^|;\s*)csrf_token=([^;]+)" not in source


def test_all_admin_templates_extend_admin_base():
    offenders = []
    for template in ADMIN_TEMPLATES:
        source = template.read_text(encoding="utf-8")
        if not re.search(r"""{%\s*extends\s+['"]admin_base\.html['"]\s*%}""", source):
            offenders.append(str(template.relative_to(ROOT)))
    assert offenders == []


def test_admin_static_assets_referenced_by_templates_exist():
    missing = []
    for template in [ADMIN_BASE, *ADMIN_TEMPLATES]:
        for path in _literal_paths(template.read_text(encoding="utf-8")):
            asset = _static_file_path(path)
            if asset is not None and not asset.exists():
                missing.append(f"{template.relative_to(ROOT)} -> {path}")
    assert missing == []


def test_admin_links_and_form_actions_resolve_to_registered_routes():
    broken = []
    for template in [ADMIN_BASE, *ADMIN_TEMPLATES]:
        source = template.read_text(encoding="utf-8")
        for path in _local_paths(re.findall(r"""(?:href|(?<!data-)action)=["']([^"'{}]+)["']""", source)):
            if path.startswith("/static/") or "." in Path(path.split("?", 1)[0]).name:
                continue
            if not _is_registered_path(path):
                broken.append(f"{template.relative_to(ROOT)} -> {path}")
    assert broken == []


def test_admin_api_calls_resolve_to_registered_backend_routes():
    broken = []
    for source_path in [*ADMIN_TEMPLATES, *FIRST_PARTY_ADMIN_JS]:
        source = source_path.read_text(encoding="utf-8")
        for path in _local_paths(_literal_paths(source)):
            if not (path.startswith("/api/") or path.startswith("/admin/charts")):
                continue
            if not _is_registered_path_or_prefix(path):
                broken.append(f"{source_path.relative_to(ROOT)} -> {path}")
    assert broken == []


def test_runtime_generated_admin_links_resolve_to_registered_frontend_routes():
    """Cover links emitted from JS and backend service payloads, not only HTML hrefs."""
    runtime_sources = [
        *ADMIN_TEMPLATES,
        *FIRST_PARTY_ADMIN_JS,
        ROOT / "analytics_service.py",
    ]
    broken = []
    for source_path in runtime_sources:
        source = source_path.read_text(encoding="utf-8")
        # Capture both complete literals and the static prefix of template
        # literals (for example `/admin/users/${id}/edit`).
        for path in re.findall(r'''["'`](/admin(?:/[^"'`$?\s<>)]+)?)''', source):
            resolves = _is_registered_path_or_prefix(path)
            if not resolves and path.endswith("/"):
                resolves = _is_registered_path(f"{path}1")
            if not resolves:
                broken.append(f"{source_path.relative_to(ROOT)} -> {path}")
    assert broken == []


def test_templates_using_api_global_inherit_its_defining_script():
    base_source = ADMIN_BASE.read_text(encoding="utf-8")
    assert "/static/js/kinjo-api.js" in base_source

    offenders = []
    for template in ADMIN_TEMPLATES:
        source = template.read_text(encoding="utf-8")
        if re.search(r"\bapi\.(?:get|post|put|patch|delete)\s*\(", source):
            if not re.search(r'''{%\s*extends\s+["']admin_base\.html["']\s*%}''', source):
                offenders.append(str(template.relative_to(ROOT)))
    assert offenders == []


def test_admin_settings_uses_configured_session_timeout_global():
    frontend_source = (ROOT / "scripts" / "compat" / "frontend_orig.py").read_text(encoding="utf-8")
    settings_source = (ADMIN_TEMPLATE_ROOT / "settings.html").read_text(encoding="utf-8")
    assert "templates.env.globals['session_timeout_minutes'] = settings.SESSION_TIMEOUT_MINUTES" in frontend_source
    assert "{{ session_timeout_minutes" in settings_source


def test_admin_user_form_uses_bounded_remote_kindergarten_lookup():
    frontend_source = (ROOT / "scripts" / "compat" / "frontend_orig.py").read_text(encoding="utf-8")
    template_source = (ADMIN_TEMPLATE_ROOT / "users" / "form.html").read_text(encoding="utf-8")
    assert "db.query(Kindergarten).all()" not in frontend_source
    assert "'/api/admin/options/kindergartens'" in template_source
    assert "page_size: 50" in template_source


def test_first_party_static_javascript_contains_no_jinja_control_syntax():
    offenders = []
    for source_path in (ROOT / "static" / "js").rglob("*.js"):
        source = source_path.read_text(encoding="utf-8")
        if "{%" in source:
            offenders.append(str(source_path.relative_to(ROOT)))
    assert offenders == []


def test_admin_unsafe_requests_use_csrf_aware_helpers():
    auth_source = (ROOT / "static" / "js" / "auth.js").read_text(encoding="utf-8")
    assert "if (![\"GET\", \"HEAD\", \"OPTIONS\"].includes(method))" in auth_source
    assert "options.headers[\"X-CSRF-Token\"] = csrfToken;" in auth_source

    # Raw fetch is also safe on admin pages because auth.js installs the
    # wrapper globally before any page scripts execute. Guard that indirect
    # contract explicitly so a future base-template change cannot silently
    # remove CSRF protection from inline fetch calls.
    base_source = ADMIN_BASE.read_text(encoding="utf-8")
    assert base_source.index("/static/js/auth.js") < base_source.index("{% block extra_scripts %}")

    offenders = []
    unsafe_pattern = re.compile(
        r"""(?P<call>fetch|fetchWithAuth|api\.(?:post|put|patch|delete))\([^;\n]+method\s*:\s*['"](?P<method>POST|PUT|PATCH|DELETE)['"]""",
        re.IGNORECASE | re.DOTALL,
    )
    for source_path in [*ADMIN_TEMPLATES, *FIRST_PARTY_ADMIN_JS]:
        source = source_path.read_text(encoding="utf-8")
        for match in unsafe_pattern.finditer(source):
            call = match.group("call")
            if call == "fetch":
                continue
            if call == "fetchWithAuth":
                continue
            if call.startswith("api."):
                continue
            offenders.append(f"{source_path.relative_to(ROOT)}:{source[:match.start()].count(chr(10)) + 1}")
    assert offenders == []


def test_kg_overview_uses_real_admin_api_not_mock_data():
    template = (ROOT / "templates" / "admin" / "kg_overview.html").read_text(encoding="utf-8")
    source = (ROOT / "static" / "js" / "kg_overview.js").read_text(encoding="utf-8")

    assert "/static/js/kg_overview.js" in template
    assert "/api/admin/kg-overview" in source
    assert "MOCK_KGS" not in source
    assert "MOCK_ALERTS" not in source
    assert "MOCK DATA ENGINE" not in source
    assert "Math.random()" not in source


def test_admin_compatibility_aliases_delegate_or_are_documented():
    route_paths = _registered_paths()
    assert "/api/admin/charts/render" in route_paths
    assert "/api/admin/charts/suggest" in route_paths
    assert "/api/admin/charts/task/{task_id}" in route_paths
    assert "/api/admin/kpi/backfill-governance" in route_paths

    users_source = (ROOT / "api" / "users.py").read_text(encoding="utf-8")
    legacy_block = users_source[users_source.index('@router.post("/users/{user_id}/admin-reset-password"'):]
    legacy_block = legacy_block[: legacy_block.index('@router.post("/users/request-password-reset")')]
    assert "include_in_schema=False" in legacy_block
    assert "canonical_admin_reset_password" in legacy_block
    assert "verify_password" not in legacy_block
    assert "change_user_password" not in legacy_block


def test_contact_message_resolve_is_js_only_csrf_safe_action():
    source = (ROOT / "templates" / "admin" / "contact_messages.html").read_text(encoding="utf-8")
    assert 'data-resolve-url="/api/admin/contact-messages/{{ msg.id }}/resolve"' in source
    assert 'fetchWithAuth(button.dataset.resolveUrl, { method: ' in source
    assert 'method="post"' not in source.lower()


def test_heatmap_api_strings_are_escaped_before_inner_html_rendering():
    source = (ROOT / "static" / "js" / "jordan_cesium_map.js").read_text(encoding="utf-8")
    assert "function esc(value)" in source
    assert "${esc(g.name_ar || g.name_en)}" in source
    assert "${esc(k.name_ar || k.name_en || 'منشأة')}" in source
    assert "${esc(a.message || '')}" in source
    assert "${esc(c.district || '')}" in source or "const cityName = esc(c.district || '')" in source
    assert "${esc(message)}" in source
