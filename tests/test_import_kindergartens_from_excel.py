from pathlib import Path

import pandas as pd

import models
from scripts.import_kindergartens_from_excel import (
    build_import_plan,
    normalize_arabic_for_match,
    normalize_governorate,
    normalize_phone,
    run_import,
)


def _write_excel(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "kindergartens.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def _kindergarten(
    db,
    *,
    name_ar="روضة الأمل",
    name_en="Hope KG",
    governorate="عمان",
    city="عمان",
    area="وسط البلد",
    address_line="عنوان قديم",
    contact_phone="0791111111",
    contact_email="old@example.com",
    license_number=None,
):
    kg = models.Kindergarten(
        name_ar=name_ar,
        name_en=name_en,
        governorate=governorate,
        city=city,
        area=area,
        address_line=address_line,
        contact_phone=contact_phone,
        contact_email=contact_email,
        license_number=license_number,
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def test_arabic_name_normalization():
    assert normalize_arabic_for_match("إربد") == normalize_arabic_for_match("اربد")
    assert normalize_arabic_for_match("روضة   الأمل") == normalize_arabic_for_match("روضه الامل")


def test_phone_normalization():
    assert normalize_phone("+962791234567")[0] == "0791234567"
    assert normalize_phone("00962791234567")[0] == "0791234567"
    assert normalize_phone("791234567")[0] == "0791234567"
    assert normalize_phone("5695093", "عمان")[0] == "065695093"


def test_governorate_normalization():
    assert normalize_governorate("Amman") == "عمان"
    assert normalize_governorate("اربد") == "إربد"
    assert normalize_governorate("Irbid") == "إربد"


def test_duplicate_matching_by_license_number(test_db, tmp_path):
    existing = _kindergarten(test_db, license_number="LIC-1", contact_email="keep@example.com")
    file_path = _write_excel(
        tmp_path,
        [
            {
                "name_ar": "روضة الأمل الجديدة",
                "governorate": "عمان",
                "city": "عمان",
                "area": "الجبيهة",
                "address_line": "عنوان جديد",
                "contact_phone": "0792222222",
                "contact_email": "",
                "license_number": "LIC-1",
            }
        ],
    )

    plan = build_import_plan(test_db, file_path, mode="dry-run")

    assert len(plan.updated) == 1
    assert plan.updated[0]["id"] == existing.id
    assert plan.updated[0]["matched_by"] == "license_number"
    assert plan.updated[0]["changes"]["address_line"] == "عنوان جديد"
    assert "contact_email" not in plan.updated[0]["changes"]


def test_duplicate_matching_by_arabic_name_and_governorate(test_db, tmp_path):
    existing = _kindergarten(test_db, name_ar="روضة الأمل", governorate="عمان", city="عمان")
    file_path = _write_excel(
        tmp_path,
        [
            {
                "name_ar": "روضة الامل",
                "governorate": "Amman",
                "city": "خلدا",
                "address_line": "عنوان محدث",
                "contact_phone": "0793333333",
            }
        ],
    )

    plan = build_import_plan(test_db, file_path, mode="dry-run")

    assert len(plan.updated) == 1
    assert plan.updated[0]["id"] == existing.id
    assert plan.updated[0]["matched_by"] == "name_ar_governorate"


def test_invalid_phone_does_not_overwrite_existing_phone(test_db, tmp_path):
    existing = _kindergarten(test_db, name_ar="روضة الهاتف", governorate="عمان", contact_phone="0791234567")
    file_path = _write_excel(
        tmp_path,
        [
            {
                "name_ar": "روضة الهاتف",
                "governorate": "عمان",
                "city": "عمان",
                "address_line": "عنوان محدث",
                "contact_phone": "5555",
            }
        ],
    )

    plan = build_import_plan(test_db, file_path, mode="dry-run")

    assert len(plan.updated) == 1
    assert plan.updated[0]["id"] == existing.id
    assert "contact_phone" not in plan.updated[0]["changes"]
    assert "warnings" in plan.updated[0]["extra"]


def test_create_new_kindergarten_when_no_match(test_db, tmp_path):
    file_path = _write_excel(
        tmp_path,
        [
            {
                "name_ar": "روضة جديدة",
                "governorate": "الزرقاء",
                "city": "الزرقاء",
                "area": "الوسط",
                "address_line": "شارع الاختبار",
                "contact_phone": "0794444444",
            }
        ],
    )

    plan = build_import_plan(test_db, file_path, mode="dry-run")

    assert len(plan.created) == 1
    assert plan.created[0]["payload"]["name_ar"] == "روضة جديدة"


def test_ambiguous_match_is_skipped(test_db, tmp_path):
    _kindergarten(test_db, name_ar="روضة مشتركة", governorate="عمان", city="عمان", contact_phone="0795555551")
    _kindergarten(test_db, name_ar="روضه مشتركه", governorate="عمان", city="خلدا", contact_phone="0795555552")
    file_path = _write_excel(tmp_path, [{"name_ar": "روضة مشتركة", "governorate": "عمان"}])

    plan = build_import_plan(test_db, file_path, mode="dry-run")

    assert len(plan.ambiguous) == 1
    assert not plan.created
    assert not plan.updated


def test_existing_record_first_excel_match_wins_for_idempotency(test_db, tmp_path):
    existing = _kindergarten(
        test_db,
        name_ar="روضة مكررة",
        governorate="عمان",
        city="عمان",
        area="الجبيهة",
        address_line="العنوان الأول",
        contact_phone="0795656565",
    )
    file_path = _write_excel(
        tmp_path,
        [
            {
                "name_ar": "روضة مكررة",
                "governorate": "عمان",
                "city": "عمان",
                "area": "الجبيهة",
                "address_line": "العنوان الأول",
                "contact_phone": "0795656565",
            },
            {
                "name_ar": "روضة مكررة",
                "governorate": "عمان",
                "city": "عمان",
                "area": "خلدا",
                "address_line": "عنوان لاحق",
                "contact_phone": "0795656565",
            },
        ],
    )

    plan = build_import_plan(test_db, file_path, mode="dry-run")

    assert not plan.updated
    assert any(row["reason"] == "no_changes" and row["matched_id"] == existing.id for row in plan.skipped)
    assert any(row["reason"].startswith("duplicate_of_excel_row_") for row in plan.skipped)


def test_dry_run_does_not_write(test_db, tmp_path):
    file_path = _write_excel(
        tmp_path,
        [{"name_ar": "روضة جافة", "governorate": "عمان", "city": "عمان", "contact_phone": "0796666666"}],
    )
    before = test_db.query(models.Kindergarten).count()

    plan = run_import(file_path=file_path, mode="dry-run", report_dir=tmp_path / "reports", db=test_db)

    assert len(plan.created) == 1
    assert test_db.query(models.Kindergarten).count() == before
    assert (Path(plan.report_dir) / "import_summary.json").exists()


def test_commit_writes_expected_rows(test_db, tmp_path):
    file_path = _write_excel(
        tmp_path,
        [{"name_ar": "روضة ملتزمة", "governorate": "عمان", "city": "عمان", "contact_phone": "0797777777"}],
    )
    before = test_db.query(models.Kindergarten).count()

    plan = run_import(file_path=file_path, mode="commit", report_dir=tmp_path / "reports", db=test_db)

    assert len(plan.created) == 1
    assert test_db.query(models.Kindergarten).count() == before + 1
    assert test_db.query(models.Kindergarten).filter_by(name_ar="روضة ملتزمة").one()
    assert (Path(plan.report_dir) / "created_kindergartens.csv").exists()
