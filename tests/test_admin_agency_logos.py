"""Tests for official-agency logo metadata, catalog/summary contract, and
the no-fabrication / no-broken-image guarantees required by the redesign."""
import os

from agency_reports_registry import AGENCY_LOGOS, OFFICIAL_AGENCY_CODES, AGENCY_DISPLAY_ORDER
from agency_reports_service import AgencyReportsService


class _FakeDB:
    """catalog()/summary() never touch the DB, so a no-op db is sufficient."""


REQUIRED_OFFICIAL = {"mosd", "moe", "moh", "mol", "ssc", "dos", "ncfa"}


def _catalog():
    return AgencyReportsService(_FakeDB()).catalog()


def _summary():
    return AgencyReportsService(_FakeDB()).summary()


def test_agency_logos_mapping_has_required_keys():
    for code in REQUIRED_OFFICIAL:
        meta = AGENCY_LOGOS[code]
        for key in ("name_ar", "name_en", "logo", "fallback", "alt_ar", "alt_en"):
            assert key in meta, f"{code} missing logo key {key}"
        assert meta["logo"].startswith("/static/img/agencies/")
        assert meta["fallback"] and isinstance(meta["fallback"], str)


def test_catalog_returns_only_official_agencies_and_count_seven():
    cat = _catalog()
    codes = {a["code"] for a in cat["agencies"]}
    assert codes == REQUIRED_OFFICIAL, f"unexpected catalog codes: {codes}"
    assert len(cat["agencies"]) == 7


def test_catalog_carries_logo_metadata_per_agency():
    for agency in _catalog()["agencies"]:
        logo = agency["logo"]
        assert logo is not None
        for key in ("path", "alt_ar", "alt_en", "available", "official", "fallback_label"):
            assert key in logo, f"{agency['code']} logo missing {key}"
        assert agency["is_official"] is True
        # Name is always present as real text (never logo-only identity).
        assert agency["name_ar"]


def test_summary_carries_logo_metadata_and_count():
    sm = _summary()
    assert sm["agency_count"] == 7
    assert len(sm["agencies"]) == 7
    for agency in sm["agencies"]:
        assert agency["logo"]["fallback_label"]
        assert agency["name_ar"]


def test_no_logo_is_presented_as_official_when_asset_missing():
    """Every configured logo path must either exist on disk (official) or be
    represented as a missing asset with an explicit, non-official fallback."""
    for code in REQUIRED_OFFICIAL:
        logo = next(a["logo"] for a in _catalog()["agencies"] if a["code"] == code)
        if logo["available"]:
            # available=True requires the real SVG to exist on disk.
            rel = logo["path"].lstrip("/static/")
            assert os.path.exists(os.path.join("static", rel)), (
                f"{code}: available=True but asset missing at {logo['path']}"
            )
            assert logo["official"] is True
        else:
            # Missing asset: must NOT claim to be an official logo and must
            # carry a fallback label so the UI never breaks.
            assert logo["path"] is None
            assert logo["official"] is False
            assert logo["fallback_label"]


def test_agency_logo_paths_resolve_under_static_img_agencies():
    for code in REQUIRED_OFFICIAL:
        path = AGENCY_LOGOS[code]["logo"]
        assert path.startswith("/static/img/agencies/")
        assert path.endswith((".svg", ".png"))


def test_display_order_matches_required_official_scope():
    assert AGENCY_DISPLAY_ORDER == ["mosd", "moe", "moh", "mol", "ssc", "dos", "ncfa"]


def test_custom_report_schema_includes_logo_and_description():
    from agency_reports_registry import custom_report_schema
    agencies = custom_report_schema()["agencies"]
    codes = {a["code"] for a in agencies}
    assert REQUIRED_OFFICIAL.issubset(codes)
    for a in agencies:
        assert "logo" in a
        assert a["logo"]["fallback_label"]