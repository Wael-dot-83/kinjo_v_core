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
    """The logo renders per size, decoratively, from the optimised mark asset.

    Two expectations here were stale and asserting the opposite of the intended
    behaviour:

    * `alt="شعار KinJo"` — the macro deliberately emits `alt=""` with
      `role="presentation"`. Every call site wraps it in a link that already has
      an accessible name (see test_kinjo_logo_call_sites_supply_accessible_name),
      so alt text would make a screen reader announce the brand twice. Restoring
      alt text to satisfy the old assertion would have been an accessibility
      regression, not a fix.
    * `/static/img/kinjo-logo.png` — the macro now serves
      kinjo-logo-mark-320.png, a cropped 320x320 mark of 57 KB, replacing a
      1254x1254 997 KB original that was downloaded on every admin page to be
      drawn at 64px.
    """
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    kinjo_logo = env.get_template("components/kinjo_logo.html").module.kinjo_logo
    for size in ("navbar", "sidebar", "login"):
        html = str(kinjo_logo(size=size))
        assert f"kinjo-logo--{size}" in html
        assert 'alt=""' in html, f"{size}: logo must be decorative"
        assert 'role="presentation"' in html, f"{size}: logo must be decorative"
        assert "/static/img/kinjo-logo-mark-320.png" in html
        # Intrinsic-ratio hints must be present so the header reserves space and
        # does not shift while the image loads.
        assert "width=" in html and "height=" in html


def test_kinjo_logo_call_sites_supply_accessible_name():
    """A decorative logo is only correct if its link is named some other way.

    This is the invariant that makes `alt=""` safe. If a call site ever drops its
    aria-label without adding visible text, the brand link becomes unlabelled and
    the decorative alt turns into a real accessibility defect.
    """
    import re

    call_sites = []
    for path in TEMPLATES.rglob("*.html"):
        if path.name == "kinjo_logo.html":
            continue  # defines the macro; its docstring mentions the call form
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"kinjo_logo\(", text):
            start = max(0, text.rfind("<a", 0, match.start()))
            window = text[start:match.end() + 400]
            named = 'aria-label' in window or re.search(r"<span[^>]*>[^<]", window)
            call_sites.append((path.name, bool(named)))

    assert call_sites, "no kinjo_logo call sites found — the search is broken"
    unnamed = [name for name, named in call_sites if not named]
    assert not unnamed, f"logo links without an accessible name: {unnamed}"


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
