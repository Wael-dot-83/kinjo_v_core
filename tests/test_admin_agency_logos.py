"""Tests for official KinJo logo usage across Admin surfaces.

Verifies:
- kinjo-logo asset exists
- Logo component renders with correct sizes
- Agency logo assets exist
- No KJ/Kj visual brand marks remain in admin UI
- Dashboard and agency-reports pages use correct logo assets
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
IMG = STATIC / "img"
AGENCY_IMG = IMG / "agencies"


def test_kinjo_logo_asset_exists():
    assert (IMG / "kinjo-logo.png").is_file(), "official kinjo-logo.png missing"


def test_kinjo_logo_component_renders():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    tmpl = env.get_template("components/kinjo_logo.html")
    # Should render without error for each size
    for size in ("small", "medium", "large"):
        html = tmpl.render(size=size, variant="full", showText=True)
        assert "kinjo-logo" in html
        assert 'alt="شعار KinJo"' in html


def test_agency_logo_assets_exist():
    expected = ("moe.jpg", "moh.jpg", "gsd.jpg", "ncfa.png", "mol.png", "mosd.jpg")
    for filename in expected:
        assert (AGENCY_IMG / filename).is_file(), f"missing agency logo asset {filename}"


def test_no_kj_brand_marks_in_admin_templates():
    admin_templates = list((TEMPLATES / "admin").rglob("*.html"))
    admin_templates.append(TEMPLATES / "admin_base.html")
    admin_templates.append(TEMPLATES / "admin_dashboard.html")
    for path in admin_templates:
        text = path.read_text(encoding="utf-8")
        # KJ/Kj as visual brand marks (not part of readable "KinJo" text)
        assert " KJ" not in text, f"KJ brand mark in {path}"
        assert " Kj" not in text, f"Kj brand mark in {path}"


def test_dashboard_uses_correct_logo():
    dashboard = (TEMPLATES / "admin_dashboard.html").read_text(encoding="utf-8")
    # Dashboard should use official-agencies-logo.svg or kinjo-logo, not KJ text
    assert "official-agencies-logo.svg" in dashboard or "kinjo-logo" in dashboard


def test_agency_reports_index_uses_correct_logo():
    index = (TEMPLATES / "admin" / "agency_reports" / "index.html").read_text(encoding="utf-8")
    assert "official-agencies-logo.svg" in index or "kinjo-logo" in index
