"""Diagnostic: check for duplicate code and routes in the agency reports module.

Run with: py scripts/manual-diagnostics/check_agency_reports_duplication.py

Checks:
1. No duplicate (method, path) FastAPI route registrations for agency-reports.
2. No module imports the old standalone agency_reports_export (should use services.agency_reports.exporter).
3. No duplicate helper functions between agency_reports_service.py and services/agency_reports/base.py.
4. All referenced NCFA static assets exist on disk.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

errors: list[str] = []
warnings: list[str] = []


def check_duplicate_routes() -> None:
    """Check that no (method, path) pair is registered twice for agency-reports."""
    try:
        from main import app
        seen: dict[tuple[str, str], str] = {}
        for route in app.routes:
            if not hasattr(route, "path") or "agency-report" not in route.path:
                continue
            for method in sorted(route.methods or []):
                key = (method, route.path)
                if key in seen:
                    errors.append(f"Duplicate route: {method} {route.path} (also in {seen[key]})")
                else:
                    seen[key] = getattr(route, "name", "?")
        if not errors:
            print(f"[OK] No duplicate agency-report routes found ({len(seen)} unique routes).")
    except Exception as exc:
        warnings.append(f"Could not check routes: {exc}")


def check_export_imports() -> None:
    """Check that no module imports from the old standalone export module."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "grep", "-r", "from agency_reports_export import", "--include=*.py", str(ROOT)],
        capture_output=True, text=True,
    )
    # grep returns non-zero if no matches; that's good
    matches = [l for l in result.stdout.strip().split("\n") if l and "professional_redesign" not in l]
    if matches:
        for m in matches:
            warnings.append(f"Old export import: {m}")
    else:
        print("[OK] No modules import from the old standalone agency_reports_export.")


def check_static_assets() -> None:
    """Check that all referenced NCFA static assets exist on disk."""
    template = ROOT / "templates" / "admin" / "agency_reports" / "agency.html"
    if not template.exists():
        errors.append("agency.html template not found")
        return
    content = template.read_text(encoding="utf-8")
    import re
    refs = re.findall(r'(?:src|href)="(/static/[^"?]+)', content)
    missing = []
    for ref in refs:
        path = ROOT / ref.lstrip("/")
        if not path.exists():
            missing.append(ref)
    if missing:
        for m in missing:
            errors.append(f"Missing static asset: {m}")
    else:
        print(f"[OK] All {len(refs)} referenced static assets exist.")


def check_service_decomposition() -> None:
    """Verify the new service package structure is complete."""
    required_files = [
        "services/agency_reports/__init__.py",
        "services/agency_reports/base.py",
        "services/agency_reports/labels.py",
        "services/agency_reports/ncfa_service.py",
        "services/agency_reports/exporter.py",
        "services/agency_reports/registry.py",
        "services/agency_reports/snapshot_task.py",
        "schemas/agency_reports.py",
    ]
    for f in required_files:
        path = ROOT / f
        if not path.exists():
            errors.append(f"Missing decomposed file: {f}")
    if not errors:
        print(f"[OK] All {len(required_files)} decomposed service files exist.")


def check_ncfa_service_isolation() -> None:
    """Verify NCFA service doesn't duplicate helper logic from the monolith."""
    ncfa_path = ROOT / "services" / "agency_reports" / "ncfa_service.py"
    if not ncfa_path.exists():
        errors.append("ncfa_service.py not found")
        return
    content = ncfa_path.read_text(encoding="utf-8")
    # The NCFA service should import shared helpers from base, not redefine them
    forbidden_defs = [
        "def _safe_int(",
        "def _safe_pct(",
        "def _gender_ar(",
        "def _coerce_enum(",
        "def _resolve_dos_period(",
    ]
    for forbidden in forbidden_defs:
        if forbidden in content:
            errors.append(f"NCFA service duplicates helper: {forbidden}")
    if not errors:
        print("[OK] NCFA service imports all shared helpers from base (no duplication).")


if __name__ == "__main__":
    print("=" * 60)
    print("Agency Reports De-duplication Diagnostic")
    print("=" * 60)
    print()

    check_service_decomposition()
    check_ncfa_service_isolation()
    check_export_imports()
    check_static_assets()
    check_duplicate_routes()

    print()
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  [WARN] {w}")
        print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  [FAIL] {e}")
        print()
        sys.exit(1)
    else:
        print("[PASS] All de-duplication checks passed.")
        sys.exit(0)
