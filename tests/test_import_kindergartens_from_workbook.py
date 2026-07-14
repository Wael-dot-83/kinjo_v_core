"""Tests for scripts/import_kindergartens_from_workbook."""
import importlib.util
import os

import models

_SPEC = importlib.util.spec_from_file_location(
    "import_kindergartens_from_workbook",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "import_kindergartens_from_workbook.py"),
)
imp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(imp)


def test_map_row_maps_city_to_district_and_fills_defaults():
    payload = imp.map_row({
        "name_ar": "روضة الاختبار", "governorate": "عمان", "city": "القويسمة",
        "name_en": "Test KG",
    })
    assert payload is not None
    assert payload["name_ar"] == "روضة الاختبار"
    assert payload["district"] == "القويسمة"          # city -> district
    assert payload["area"] == "غير محدد"               # required default filled
    assert payload["contact_phone"] == "0000000000"    # required default filled
    assert payload["status"] == models.KindergartenStatus.DRAFT


def test_map_row_district_falls_back_to_governorate():
    payload = imp.map_row({"name_ar": "روضة ب", "governorate": "إربد"})
    assert payload["district"] == "إربد"


def test_map_row_rejects_rows_missing_name_or_governorate():
    assert imp.map_row({"governorate": "عمان"}) is None          # no name
    assert imp.map_row({"name_ar": "بلا محافظة"}) is None          # no governorate
    assert imp.map_row({"name_ar": "  ", "governorate": "عمان"}) is None  # blank name


def test_import_rows_inserts_valid_skips_invalid_and_dedups(test_db):
    rows = [
        {"name_ar": "روضة 1", "governorate": "عمان", "city": "عمان"},
        {"name_ar": "روضة 2", "governorate": "إربد"},
        {"name_ar": "روضة 1", "governorate": "عمان"},   # duplicate name
        {"governorate": "عمان"},                          # invalid (no name)
    ]
    stats = imp.import_rows(test_db, rows)
    assert stats["created"] == 2
    assert stats["duplicate"] == 1
    assert stats["skipped_invalid"] == 1
    assert test_db.query(models.Kindergarten).filter_by(name_ar="روضة 1").count() == 1

    # idempotent: a second run creates nothing
    stats2 = imp.import_rows(test_db, rows)
    assert stats2["created"] == 0
