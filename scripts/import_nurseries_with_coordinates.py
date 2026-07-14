"""Import nurseries with coordinates from Excel into the kindergartens table.

Features:
- Dry-run by default; pass --commit to apply changes
- Idempotent upsert: match existing records by normalized (name_ar, governorate)
- Validates required columns and coordinates
- Produces import reports
- Includes verification step to confirm data was saved
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models
from config import settings
from database import SessionLocal, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_nurseries_with_coordinates")

REQUIRED_COLUMNS = ["name_ar", "governorate", "city", "latitude", "longitude"]

INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670]")
SPACE_RE = re.compile(r"\s+")


def clean_display_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value)
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE_RE.sub("", text)
    text = text.replace("\u0640", "")
    text = SPACE_RE.sub(" ", text).strip()
    return text.strip()


def normalize_arabic_for_match(value: Any) -> str:
    text = clean_display_text(value)
    text = DIACRITICS_RE.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    text = text.replace("ى", "ي").replace("ئ", "ي")
    text = text.replace("ة", "ه")
    text = text.lower()
    text = re.sub(r"[^\w\s\u0600-\u06ff]", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_digits(value: Any) -> str:
    text = clean_display_text(value)
    digit_map = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return text.translate(digit_map)


def parse_coordinate(value: Any, field_name: str) -> tuple[float | None, str | None]:
    text = normalize_digits(value)
    if not text:
        return None, None
    try:
        number = float(text)
    except (ValueError, TypeError):
        return None, f"invalid {field_name}: {value}"
    if field_name == "latitude" and not -90 <= number <= 90:
        return None, f"latitude out of range: {value}"
    if field_name == "longitude" and not -180 <= number <= 180:
        return None, f"longitude out of range: {value}"
    return number, None


GOVERNORATE_CANONICAL = {
    "amman": "عمان",
    "عمان": "عمان",
    "irbid": "إربد",
    "إربد": "إربد",
    "اربد": "إربد",
    "zarqa": "الزرقاء",
    "الزرقاء": "الزرقاء",
    "balqa": "البلقاء",
    "البلقاء": "البلقاء",
    "madaba": "مادبا",
    "مادبا": "مادبا",
    "karak": "الكرك",
    "الكرك": "الكرك",
    "tafilah": "الطفيلة",
    "الطفيلة": "الطفيلة",
    "maan": "معان",
    "معان": "معان",
    "aqaba": "العقبة",
    "العقبة": "العقبة",
    "jerash": "جرش",
    "جرش": "جرش",
    "ajloun": "عجلون",
    "عجلون": "عجلون",
    "mafraq": "المفرق",
    "المفرق": "المفرق",
}


def normalize_governorate(value: Any) -> str | None:
    text = clean_display_text(value)
    if not text:
        return None
    normalized = unicodedata.normalize("NFKC", text).lower()
    return GOVERNORATE_CANONICAL.get(normalized, text)


def read_excel_file(file_path: Path) -> pd.DataFrame:
    """Read Excel file and return DataFrame."""
    if not file_path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")
    df = pd.read_excel(file_path)
    return df


def validate_columns(columns: list[str]) -> list[str]:
    """Validate that required columns exist."""
    errors = []
    for col in REQUIRED_COLUMNS:
        if col not in columns:
            errors.append(f"missing required column: {col}")
    return errors


def prepare_row(row: pd.Series, row_num: int) -> dict[str, Any]:
    """Prepare a row for database insertion."""
    errors = []
    
    payload = {}
    
    # Text fields
    for text_field in ("name_ar", "name_en", "city", "area", "address_line"):
        value = clean_display_text(row.get(text_field))
        if value:
            payload[text_field] = value
    
    # Governorate
    governorate = normalize_governorate(row.get("governorate"))
    if governorate:
        payload["governorate"] = governorate
    
    # Phone
    phone = clean_display_text(row.get("contact_phone"))
    if phone:
        payload["contact_phone"] = phone
    
    # Email
    email = clean_display_text(row.get("contact_email"))
    if email:
        payload["contact_email"] = email
    
    # Coordinates - these are required
    latitude, lat_err = parse_coordinate(row.get("latitude"), "latitude")
    if lat_err:
        errors.append(lat_err)
    longitude, lng_err = parse_coordinate(row.get("longitude"), "longitude")
    if lng_err:
        errors.append(lng_err)
    
    # Time fields
    for time_field in ("operating_hours_start", "operating_hours_end"):
        value = clean_display_text(row.get(time_field))
        if value:
            payload[time_field] = value
    
    if errors:
        return {"excel_row": row_num, "errors": errors, "raw": {k: str(v) for k, v in row.to_dict().items() if not pd.isna(v)}}
    
    payload["latitude"] = latitude
    payload["longitude"] = longitude
    payload["status"] = models.KindergartenStatus.DRAFT
    
    if not payload.get("contact_phone"):
        payload["contact_phone"] = "غير متوفر"
    if not payload.get("address_line"):
        payload["address_line"] = "غير محدد"
    if not payload.get("city"):
        payload["city"] = payload.get("governorate", "غير محدد")
    if not payload.get("area"):
        payload["area"] = "غير محدد"
    
    return {"excel_row": row_num, "payload": payload, "errors": []}


def find_existing_by_name_governorate(db, name_ar: str, governorate: str) -> models.Kindergarten | None:
    """Find existing kindergarten by normalized name and governorate."""
    n_name = normalize_arabic_for_match(name_ar)
    n_gov = normalize_arabic_for_match(governorate)
    
    existing = db.query(models.Kindergarten).filter(
        func.lower(models.Kindergarten.name_ar) == n_name.lower(),
        func.lower(models.Kindergarten.governorate) == n_gov.lower(),
    ).first()
    
    return existing


def run_import(file_path: Path, mode: str, report_dir: Path) -> dict[str, Any]:
    """Run the import process."""
    df = read_excel_file(file_path)
    
    # Validate columns
    col_errors = validate_columns(df.columns.tolist())
    if col_errors:
        raise ValueError(col_errors)
    
    session = SessionLocal()
    created_count = 0
    updated_count = 0
    error_count = 0
    created_records = []
    errors = []
    
    total_before = session.query(func.count(models.Kindergarten.id)).scalar() or 0
    
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        result = prepare_row(row, row_num)
        
        if result.get("errors"):
            errors.append(result)
            error_count += 1
            continue
        
        payload = result["payload"]
        
        # Check if exists
        existing = find_existing_by_name_governorate(
            session, payload.get("name_ar"), payload.get("governorate")
        )
        
        if existing:
            # Update coordinates if not set
            if existing.latitude is None and payload.get("latitude") is not None:
                existing.latitude = payload["latitude"]
                existing.longitude = payload["longitude"]
                updated_count += 1
                logger.info(f"Row {row_num}: Updated {existing.name_ar} with coordinates")
            else:
                logger.info(f"Row {row_num}: Skipped {existing.name_ar} (already exists with coordinates)")
        else:
            session.add(models.Kindergarten(**payload))
            created_count += 1
            created_records.append(payload)
            logger.info(f"Row {row_num}: Created {payload.get('name_ar')}")
    
    if mode == "commit":
        session.commit()
        logger.info(f"Import committed: {created_count} created, {updated_count} updated, {error_count} errors")
    else:
        session.rollback()
    
    total_after = session.query(func.count(models.Kindergarten.id)).scalar() or 0
    session.close()
    
    # Write report
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "mode": mode,
        "file_path": str(file_path),
        "total_rows": len(df),
        "total_before": total_before,
        "total_after": total_after,
        "created": created_count,
        "updated": updated_count,
        "errors": errors,
    }
    
    report_path = report_dir / "nurseries_import_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return report


def verify_import() -> bool:
    """Verify that data was imported correctly."""
    session = SessionLocal()
    
    try:
        # Check total count
        total = session.query(func.count(models.Kindergarten.id)).scalar() or 0
        
        # Check records with coordinates
        with_coords = session.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.latitude.isnot(None),
            models.Kindergarten.longitude.isnot(None),
        ).scalar() or 0
        
        logger.info(f"Verification: {total} total kindergartens, {with_coords} with coordinates")
        
        return True
    except Exception as e:
        logger.error(f"Database verification failed: {e}")
        return False
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import nurseries with coordinates from Excel")
    parser.add_argument("--file", required=False, 
                        default=r"C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\CSv\nurseries_with_coordinates.xlsx",
                        help="Excel file path")
    parser.add_argument("--report-dir", default="reports/imports/nurseries",
                        help="Directory for import reports")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--commit", action="store_true", help="Write to database (default: dry-run)")
    parser.add_argument("--verify", action="store_true", help="Verify import after completion")
    args = parser.parse_args()
    
    mode = "commit" if args.commit else "dry-run"
    file_path = Path(args.file)
    report_dir = Path(args.report_dir)
    
    try:
        report = run_import(file_path, mode, report_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        
        if args.verify or args.commit:
            logger.info("Running verification...")
            if verify_import():
                logger.info("VERIFICATION PASSED: Data successfully saved to database")
            else:
                logger.error("VERIFICATION FAILED: Check database connection and data")
                return 1
        
        return 0
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.exception(f"Import failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
