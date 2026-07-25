"""Regression contracts for the 2026-07-24 admin-module audit fix batch.

Pins the surgical fixes so they cannot silently regress:
1. charts_dashboard.html (a bilingual page) carries no hardcoded English-only
   user-facing strings in its loading state, drilldown breadcrumb, empty-table
   state, or interpretation panel.
2. The immunization-schedule upload on the agency report page submits through
   the canonical fetchWithAuth helper (CSRF auto-injection + 401 handling),
   not a raw fetch with a hand-rolled CSRF header.
3. The enrollment review route keeps both its canonical path and its
   documented plural compatibility alias.
4. The bulk user import row-failure handler logs the failure instead of
   silently swallowing it.
5. The child-level analytics endpoint (restricted PII) is hard-gated with
   require_admin like every sibling in its router (was bare get_current_user,
   answering PARENT callers with 200).
"""

import re
from pathlib import Path

from main import app

ROOT = Path(__file__).resolve().parents[1]
CHARTS_DASHBOARD = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"
AGENCY_REPORT = ROOT / "templates" / "admin" / "agency_reports" / "report.html"


def test_charts_dashboard_has_no_hardcoded_english_only_strings():
    html = CHARTS_DASHBOARD.read_text(encoding="utf-8")
    assert '<span class="visually-hidden">Loading...' not in html
    assert "<em>Level:" not in html
    assert "'<p class=\"text-muted\">No data</p>'" not in html
    # The drilldown breadcrumb's final segment is bilingual now.
    assert "الحضانات" in html
    assert "بدون بيانات" in html
    # The scope-level enum localises through TRANSLATIONS (network was missing).
    assert '"network": LANG === \'en\' ? "Network" : "الشبكة"' in html


def test_immunization_upload_uses_canonical_fetch_helper():
    html = AGENCY_REPORT.read_text(encoding="utf-8")
    script_start = html.index("/api/admin/agency-reports/moh/immunization-schedule")
    script = html[script_start:]
    assert "fetchWithAuth(base" in script
    # The hand-rolled CSRF header and its now-dead getCookie helper are gone.
    assert "getCookie" not in script
    assert 'headers: { "X-CSRF-Token"' not in script


def test_enrollment_review_keeps_canonical_and_alias_routes():
    source = (ROOT / "api" / "enrollment.py").read_text(encoding="utf-8")
    assert "compatibility alias" in source
    paths = set()
    for route in app.routes:
        included = getattr(route, "original_router", None)
        context = getattr(route, "include_context", None)
        if included is not None and context is not None:
            prefix = context.prefix or ""
            for child in included.routes:
                child_path = getattr(child, "path", None)
                methods = getattr(child, "methods", set()) or set()
                if child_path and "POST" in methods:
                    paths.add(f"{prefix}{child_path}")
        else:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", set()) or set()
            if path and "POST" in methods:
                paths.add(path)
    assert "/api/enrollment/{enrollment_id}/review" in paths
    assert "/api/enrollments/{enrollment_id}/review" in paths


def test_bulk_import_row_failure_is_logged():
    source = (ROOT / "admin_endpoints.py").read_text(encoding="utf-8")
    handler = re.search(
        r"except \(SQLAlchemyError, AttributeError, ValueError, KeyError\) as e:.*?failed\.append\(row_num\)",
        source,
        re.DOTALL,
    )
    assert handler is not None
    assert "logger.warning" in handler.group(0)


def test_child_analytics_endpoint_is_hard_gated_admin():
    source = (ROOT / "admin_advanced_analytics_endpoints.py").read_text(encoding="utf-8")
    handler = source[source.index("async def get_child_analytics"):source.index("@router.get", source.index("async def get_child_analytics"))]
    assert "Depends(require_admin)" in handler
    assert "get_current_user" not in handler


# --------------------------------------------------------------------------
# /api/kindergartens list ecosystem — the cap must cover the platform's real
# scale (635 kindergartens) and every consumer must read the envelope's
# data.items rows (several read a non-existent top-level "kindergartens" key
# and silently rendered empty filters/wizards).
# --------------------------------------------------------------------------
def test_kindergartens_list_limit_covers_platform_scale(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    ok = client.get("/api/kindergartens?limit=1000", headers=headers)
    assert ok.status_code == 200, ok.text
    body = ok.json()["data"]
    assert set(body) >= {"items", "total", "skip", "limit", "returned"}

    too_much = client.get("/api/kindergartens?limit=1001", headers=headers)
    assert too_much.status_code == 422


def test_kindergartens_consumers_read_envelope_items():
    expectations = {
        "static/js/admin_daily_reports_organization.js": ["data?.items", "limit: 1000"],
        "templates/communication/modals/new_message.html": ["data.data.items", "limit=1000"],
        "templates/admin/incident_reports_list.html": ["data.data.items", "limit=1000"],
        "templates/admin/safety_analytics.html": ["data.data.items", "limit=1000"],
        "templates/parent/wizard/kindergarten_select.html": ["data.data.items", "limit=1000"],
        "templates/enrollment/create.html": ["data.data.items"],
        "static/js/dashboard.js": ["data.data.items", "limit=1000"],
    }
    for rel_path, needles in expectations.items():
        source = (ROOT / rel_path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in source, f"{rel_path} missing {needle!r}"


def test_search_kindergartens_uses_real_parameter_names():
    source = (ROOT / "static/js/kinjo-api.js").read_text(encoding="utf-8")
    start = source.index("async searchKindergartens")
    end = source.index("}", source.index("return this.get(\"/api/kindergartens\"", start))
    helper = source[start:end]
    assert "queryParams.q = params.search" in helper
    assert "queryParams.name" not in helper
    assert "queryParams.city" not in helper
