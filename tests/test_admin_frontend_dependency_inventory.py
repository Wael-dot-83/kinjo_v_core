"""Repository-wide Admin form and JavaScript dependency inventory."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_TEMPLATES = [
    ROOT / "templates" / "admin_dashboard.html",
    *(ROOT / "templates" / "admin").rglob("*.html"),
]
FORM_RE = re.compile(r"<form\b(?P<attrs>[^>]*)>(?P<body>.*?)</form>", re.I | re.S)
ATTR_RE = re.compile(r"(?P<name>[\w:-]+)\s*=\s*([\"'])(?P<value>.*?)\2", re.S)


def attributes(raw: str) -> dict[str, str]:
    return {match.group("name").lower(): match.group("value") for match in ATTR_RE.finditer(raw)}


def test_native_admin_forms_cannot_submit_unsafe_requests_without_csrf():
    discovered = 0
    for path in ADMIN_TEMPLATES:
        source = path.read_text(encoding="utf-8")
        for match in FORM_RE.finditer(source):
            discovered += 1
            attrs = attributes(match.group("attrs"))
            method = attrs.get("method", "get").lower()
            if method in {"post", "put", "patch", "delete"}:
                form_source = match.group(0)
                assert "csrf_token" in form_source or "X-CSRF-Token" in form_source, (
                    f"{path.relative_to(ROOT)} has an unsafe native {method.upper()} form without CSRF"
                )
    assert discovered >= 19, "Admin form inventory unexpectedly became vacuous"


def test_admin_globals_are_loaded_by_the_shared_shell_or_page():
    base = (ROOT / "templates" / "admin_base.html").read_text(encoding="utf-8")
    shared_providers = {
        "Chart": "/static/vendor/chartjs/chart.umd.min.js",
        "Swal": "/static/vendor/sweetalert2/sweetalert2.all.min.js",
        "bootstrap": "/static/vendor/bootstrap/bootstrap.bundle.min.js",
        "fetchWithAuth": "/static/js/auth.js",
        "api": "/static/js/kinjo-api.js",
        "AdminComponents": "/static/js/admin_components.js",
        "AdminI18n": "/static/js/admin_i18n.js",
    }
    for global_name, provider in shared_providers.items():
        consumers = [
            path for path in ADMIN_TEMPLATES
            if re.search(rf"\b{re.escape(global_name)}\b", path.read_text(encoding="utf-8"))
        ]
        if consumers:
            assert provider in base, f"{global_name} is used but {provider} is absent from Admin shell"

    page_providers = (
        (
            "templates/admin/analytics/charts_dashboard.html",
            "templates/admin/analytics/charts_dashboard.html",
            "Plotly",
            "/static/vendor/plotly-2.35.2.min.js",
        ),
        (
            "templates/admin/agency_reports/report.html",
            "static/js/admin_agency_reports.js",
            "Plotly",
            "/static/vendor/plotly-2.35.2.min.js",
        ),
        (
            "templates/admin/analytics/drilldown.html",
            "static/js/admin_analytics_drilldown.js",
            "Tablesort",
            "/static/vendor/tablesort/tablesort.min.js",
        ),
    )
    for page, consumer, global_name, provider in page_providers:
        page_source = (ROOT / page).read_text(encoding="utf-8")
        consumer_source = (ROOT / consumer).read_text(encoding="utf-8")
        assert re.search(rf"\b{global_name}\b", consumer_source)
        assert provider in page_source, f"{page} uses {global_name} without loading {provider}"
