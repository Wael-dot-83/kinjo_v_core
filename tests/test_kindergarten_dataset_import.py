"""Tests for the KINJORDAN geocoded kindergartens dataset v2 importer."""

import pytest
from pathlib import Path
from sqlalchemy.orm import Session

import models
from scripts.import_kindergartens_dataset_v2 import (
    clean_text,
    normalize_governorate,
    normalize_digits,
    parse_phone,
    parse_float,
    parse_int,
    wipe_all_kindergartens,
    import_kindergartens_dataset,
    find_excel_file,
)


def test_normalization_utilities():
    """Test text, governorate, digits, phone, coordinate normalization."""
    assert clean_text("  حضانة النور  ") == "حضانة النور"
    assert clean_text("None") == ""
    assert clean_text("ــــــــــــــــ") == ""

    # Governorate canonicalization
    assert normalize_governorate("عمّان") == "العاصمة"
    assert normalize_governorate("عمان") == "العاصمة"
    assert normalize_governorate("العاصمة") == "العاصمة"
    assert normalize_governorate("مأدبا") == "مادبا"
    assert normalize_governorate("مادبا") == "مادبا"
    assert normalize_governorate("إربد") == "إربد"
    assert normalize_governorate("الزرقاء") == "الزرقاء"
    assert normalize_governorate("البلقاء") == "البلقاء"
    assert normalize_governorate("معان") == "معان"
    assert normalize_governorate("الطفيلة") == "الطفيلة"
    assert normalize_governorate("الكرك") == "الكرك"
    assert normalize_governorate("العقبة") == "العقبة"
    assert normalize_governorate("جرش") == "جرش"
    assert normalize_governorate("عجلون") == "عجلون"
    assert normalize_governorate("المفرق") == "المفرق"

    # Digits and phone parsing
    assert normalize_digits("٠٧٩١٢٣٤٥٦٧") == "0791234567"
    assert parse_phone("079-123-4567") == "0791234567"
    assert parse_phone("none") == "غير متوفر"

    # Coordinates and capacity
    assert parse_float("31.9539") == 31.9539
    assert parse_int("25.0") == 25
    assert parse_int("غير محدد") is None


def test_find_excel_file():
    """Ensure the dataset Excel file is discovered correctly."""
    file_path = find_excel_file()
    assert file_path.exists()
    assert "KINJORDAN" in file_path.name


def test_import_dataset_dry_run_and_wipe(test_db: Session):
    """Test wiping existing kindergartens and dry-run importing dataset."""
    # Create sample existing kindergarten
    kg_old = models.Kindergarten(
        name_ar="حضانة تجريبية سابقة",
        governorate="العاصمة",
        district="عمان",
        area="الجبيهة",
        address_line="شارع الجامعة",
        contact_phone="0790000000",
        status=models.KindergartenStatus.DRAFT,
    )
    test_db.add(kg_old)
    test_db.commit()
    test_db.refresh(kg_old)

    # Test wipe
    stats = wipe_all_kindergartens(test_db)
    test_db.commit()
    assert stats["deleted_kindergartens"] >= 1
    assert test_db.query(models.Kindergarten).count() == 0

    # Test dry-run import
    report = import_kindergartens_dataset(wipe_existing=False, commit=False)
    assert report["valid_rows_count"] == 1375
    assert report["imported_count"] == 1375
    assert report["commit"] is False
    assert "العاصمة" in report["governorates_distribution"]
    assert report["governorates_distribution"]["العاصمة"] == 738


def test_public_kindergartens_api(client, auth_headers_admin):
    """Test that /api/kindergartens returns standard success response with auth."""
    response = client.get("/api/kindergartens?status=ACTIVE&limit=10", headers=auth_headers_admin)
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "items" in data.get("data", {}) or "kindergartens" in data


