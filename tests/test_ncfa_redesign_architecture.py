"""Test: verify no duplicate agency-report route registrations."""
import os

# Ensure testing env is set before importing app (conftest may not have run yet
# if this module is imported in a different order).
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from main import app


def _all_paths() -> set[str]:
    """Return all registered route paths."""
    return {r.path for r in app.routes if hasattr(r, "path")}


def test_no_duplicate_agency_report_routes():
    """No (method, path) pair should be registered twice for agency-reports."""
    seen = {}
    duplicates = []
    for route in app.routes:
        if not hasattr(route, "path") or "agency-report" not in route.path:
            continue
        for method in sorted(route.methods or []):
            key = (method, route.path)
            if key in seen:
                duplicates.append(f"{method} {route.path}")
            else:
                seen[key] = True
    assert duplicates == [], f"Duplicate agency-report routes: {duplicates}"


def test_ncfa_report_endpoint_accessible(client, admin_user):
    """The NCFA child_family_profile report endpoint must return 200."""
    from dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.get("/api/admin/agency-reports/ncfa/reports/child_family_profile")
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.clear()


def test_governance_overview_endpoint_accessible(client, admin_user):
    """The governance overview endpoint must return 200."""
    from dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.get("/api/admin/agency-reports/governance/overview")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "source" in body
        assert "governorate" in body
    finally:
        app.dependency_overrides.clear()


def test_unified_export_endpoint_accessible(client, admin_user):
    """The unified export endpoint with ?format=json must return 200."""
    from dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.get("/api/admin/agency-reports/ncfa/reports/child_family_profile/export?format=json")
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.clear()


def test_ncfa_service_is_extracted():
    """The NCFA service must be registered in the service registry."""
    from services.agency_reports.registry import _AGENCY_SERVICES
    assert "ncfa" in _AGENCY_SERVICES
    from services.agency_reports.ncfa_service import NCFAAgencyReportService
    assert _AGENCY_SERVICES["ncfa"] is NCFAAgencyReportService


def test_export_module_consolidated():
    """The old export module re-exports from the new consolidated exporter."""
    import agency_reports_export
    from services.agency_reports.exporter import to_csv, to_json, to_xlsx, custom_report_to_csv
    assert agency_reports_export.to_csv is to_csv
    assert agency_reports_export.to_json is to_json
    assert agency_reports_export.custom_report_to_csv is custom_report_to_csv


def test_snapshot_models_exist():
    """The new ORM models for snapshots and cache must be importable."""
    import models
    assert hasattr(models, "AgencyReportSnapshot")
    assert hasattr(models, "UnifiedMetricCache")
    assert hasattr(models, "SnapshotMetadata")


def test_unified_export_endpoint_supports_formats():
    """The unified export endpoint accepts ?format=csv|json|xlsx."""
    from api.agency_reports_api import agency_report_export_unified
    import inspect
    sig = inspect.signature(agency_report_export_unified)
    assert "fmt" in sig.parameters


def test_governance_overview_endpoint_exists():
    """The governance overview endpoint is accessible (verified via client test above)."""
    # This is a structural assertion — the actual accessibility is tested in
    # test_governance_overview_endpoint_accessible.
    from api.agency_reports_api import agency_report_governance_overview
    import inspect
    sig = inspect.signature(agency_report_governance_overview)
    assert "governorate" in sig.parameters


def test_celery_snapshot_task_registered():
    """The nightly snapshot task must be in the Celery beat schedule."""
    from celery_app import celery_app
    assert "run-agency-report-snapshots" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["run-agency-report-snapshots"]
    assert entry["task"] == "agency_report_snapshot_task.run_daily_snapshots"


def test_shared_js_components_file_exists():
    """The shared agency_report_components.js must exist on disk."""
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    assert (ROOT / "static" / "js" / "agency_report_components.js").exists()


def test_shared_css_file_exists():
    """The shared agency_report_components.css must exist on disk."""
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    assert (ROOT / "static" / "css" / "agency_report_components.css").exists()


def test_shared_template_macros_exist():
    """The shared Jinja2 macro file must exist."""
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    assert (ROOT / "templates" / "admin" / "agency_reports" / "_components" / "report_components.html").exists()


def test_pydantic_schemas_defined():
    """The unified ReportResult contract schemas must be importable."""
    from schemas.agency_reports import ReportResult, KPI, ChartSpec, ReportFilters
    assert ReportResult is not None
    assert KPI is not None
    assert ChartSpec is not None
    assert ReportFilters is not None


def test_alembic_migration_exists():
    """The agency report snapshots migration must exist."""
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    migration = ROOT / "alembic" / "versions" / "ncfa_snap_01_agency_report_snapshots.py"
    assert migration.exists()
    content = migration.read_text(encoding="utf-8")
    assert "agency_report_snapshots" in content
    assert "unified_metric_cache" in content
    assert "snapshot_metadata" in content
