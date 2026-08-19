"""Import verified geocoded kindergartens from KINJORDAN dataset into the database.

Features:
- Reads Excel workbook (e.g. KINJORDAN_geocoded_verified_LATEST.xlsx / KINJORDAN_geocoded_verified_LATEST_v2.xlsx)
- Optional --wipe-existing flag to cleanly wipe all current kindergarten records and related dependencies
- Normalizes Arabic text, Jordan governorates, phone numbers, and coordinates
- Sets imported kindergartens to ACTIVE so they appear on www.kinjordan.org
- Supports dry-run (default) and --commit
- Provides detailed import summary and governorate distribution breakdown
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models
from config import settings
from database import SessionLocal, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("import_kindergartens_dataset_v2")

INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670\u0651\u0640]")  # includes shaddah & tatweel
SPACE_RE = re.compile(r"\s+")

GOVERNORATE_CANONICAL = {
    "amman": "العاصمة",
    "عمان": "العاصمة",
    "عمّان": "العاصمة",
    "العاصمة": "العاصمة",
    "عاصمة": "العاصمة",
    "irbid": "إربد",
    "إربد": "إربد",
    "اربد": "إربد",
    "zarqa": "الزرقاء",
    "zarqaa": "الزرقاء",
    "الزرقاء": "الزرقاء",
    "الزرقا": "الزرقاء",
    "balqa": "البلقاء",
    "البلقاء": "البلقاء",
    "السلط": "البلقاء",
    "madaba": "مادبا",
    "مادبا": "مادبا",
    "مأدبا": "مادبا",
    "karak": "الكرك",
    "الكرك": "الكرك",
    "كرك": "الكرك",
    "tafilah": "الطفيلة",
    "tafila": "الطفيلة",
    "الطفيلة": "الطفيلة",
    "الطفيله": "الطفيلة",
    "معان": "معان",
    "maan": "معان",
    "aqaba": "العقبة",
    "العقبة": "العقبة",
    "العقبه": "العقبة",
    "jerash": "جرش",
    "جرش": "جرش",
    "ajloun": "عجلون",
    "عجلون": "عجلون",
    "mafraq": "المفرق",
    "المفرق": "المفرق",
    "مفرق": "المفرق",
}


def clean_text(value: Any) -> str:
    """Normalize and clean string data."""
    if value is None or pd.isna(value):
        return ""
    text_val = str(value).strip()
    if text_val.endswith(".0") and text_val[:-2].isdigit():
        text_val = text_val[:-2]
    if text_val.lower() in ("none", "nan", "null", "ــــــــــــــــ", "---", "-"):
        return ""
    text_val = unicodedata.normalize("NFKC", text_val)
    text_val = INVISIBLE_RE.sub("", text_val)
    text_val = SPACE_RE.sub(" ", text_val).strip()
    return text_val


def normalize_governorate(gov_raw: Any) -> str:
    """Normalize raw governorate input to canonical Jordanian governorate name."""
    cleaned = clean_text(gov_raw)
    if not cleaned:
        return "العاصمة"
    
    # Strip diacritics for dictionary lookup
    stripped = DIACRITICS_RE.sub("", cleaned).lower().strip()
    if stripped in GOVERNORATE_CANONICAL:
        return GOVERNORATE_CANONICAL[stripped]
    
    if cleaned in GOVERNORATE_CANONICAL:
        return GOVERNORATE_CANONICAL[cleaned]
    
    # Fallback to config alias matching
    for alias, canonical in settings.JORDAN_GOVERNORATE_ALIASES.items():
        if alias in stripped or stripped in alias:
            return canonical
            
    return cleaned


def normalize_digits(value: Any) -> str:
    """Convert Eastern Arabic digits to standard ASCII digits."""
    text_val = clean_text(value)
    digit_map = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return text_val.translate(digit_map)


def parse_phone(value: Any) -> str:
    """Clean and standardize phone numbers."""
    digits = normalize_digits(value)
    digits = re.sub(r"[^\d+]", "", digits)
    if not digits:
        return "غير متوفر"
    return digits


def parse_float(value: Any) -> Optional[float]:
    """Parse float coordinate safely."""
    digits = normalize_digits(value)
    if not digits:
        return None
    try:
        return float(digits)
    except (ValueError, TypeError):
        return None


def parse_int(value: Any) -> Optional[int]:
    """Parse integer capacity safely."""
    digits = normalize_digits(value)
    if not digits:
        return None
    try:
        return int(float(digits))
    except (ValueError, TypeError):
        return None


def wipe_all_kindergartens(db: Session) -> dict[str, Any]:
    """Cleanly wipe all existing kindergartens and their foreign key dependencies."""
    logger.info("Wiping all existing kindergarten records and unlinking dependencies...")
    stats: dict[str, Any] = {}
    dialect_name = db.bind.dialect.name if db.bind else ""
    is_postgres = dialect_name == "postgresql"
    is_sqlite = dialect_name == "sqlite"
    
    if is_postgres:
        logger.info("Performing PostgreSQL fast CASCADE wipe...")
        db.execute(text("DELETE FROM user_dashboard_preferences WHERE user_id IN (SELECT id FROM users WHERE role IN ('MANAGER', 'SUPERVISOR') OR kindergarten_id IS NOT NULL);"))
        db.execute(text("DELETE FROM user_filter_preferences WHERE user_id IN (SELECT id FROM users WHERE role IN ('MANAGER', 'SUPERVISOR') OR kindergarten_id IS NOT NULL);"))
        db.execute(text("DELETE FROM users WHERE role IN ('MANAGER', 'SUPERVISOR') OR kindergarten_id IS NOT NULL;"))
        db.execute(text("UPDATE users SET kindergarten_id = NULL WHERE kindergarten_id IS NOT NULL;"))
        db.execute(text("TRUNCATE TABLE kindergartens CASCADE;"))
        db.flush()
        stats["wiped_postgresql_cascade"] = True
        logger.info("PostgreSQL CASCADE wipe completed.")
        return stats

    if is_sqlite:
        db.execute(text("PRAGMA foreign_keys = OFF;"))
    
    try:
        # Delete dependent operational and transactional data first
        tables_to_clear = [
            models.DailyReportView,
            models.AIParentRecommendation,
            models.Notification,
            models.AttendanceLog,
            models.DailyReport,
            models.AbsenceRequest,
            models.SupervisorAssignment,
            models.WaitlistEntry,
            models.IncidentHistory,
            models.Incident,
            models.EnrollmentApplication,
            models.Child,
            models.Event,
            models.MessageAttachment,
            models.MessageUserState,
            models.MessageRecipient,
            models.Message,
            models.SurveyResponse,
            models.Survey,
            models.Class,
            models.SupervisorProfile,
            models.KindergartenService,
            models.OperatingCalendar,
            models.StaffPresenceLog,
            models.RatioCompliance,
            models.KPISnapshot,
            models.GovernanceScore,
            models.SafeguardingCase,
            models.Task,
            models.StaffTrainingCompletion,
            models.KPITarget,
        ]
        for tbl in tables_to_clear:
            try:
                cnt = db.query(tbl).delete(synchronize_session=False)
                stats[f"deleted_{tbl.__tablename__}"] = cnt
            except Exception as e:
                logger.debug(f"Table {tbl} wipe skipped or empty: {e}")

        # Delete MANAGER and SUPERVISOR users associated with old kindergartens
        kg_user_ids = [u.id for u in db.query(models.User.id).filter(
            (models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR])) |
            (models.User.kindergarten_id.isnot(None))
        ).all()]
        
        if kg_user_ids:
            db.query(models.UserDashboardPreference).filter(models.UserDashboardPreference.user_id.in_(kg_user_ids)).delete(synchronize_session=False)
            db.query(models.UserFilterPreference).filter(models.UserFilterPreference.user_id.in_(kg_user_ids)).delete(synchronize_session=False)
            deleted_users = db.query(models.User).filter(models.User.id.in_(kg_user_ids)).delete(synchronize_session=False)
            stats["deleted_kg_staff_users"] = deleted_users

        # Unlink any remaining users
        db.query(models.User).filter(models.User.kindergarten_id.isnot(None)).update(
            {models.User.kindergarten_id: None}, synchronize_session=False
        )

        # Finally, delete all kindergartens
        deleted_kg = db.query(models.Kindergarten).delete(synchronize_session=False)
        stats["deleted_kindergartens"] = deleted_kg

        db.flush()
    finally:
        if is_sqlite:
            db.execute(text("PRAGMA foreign_keys = ON;"))

    logger.info(f"Wipe completed: {stats}")
    return stats


def find_excel_file(candidate_path: Optional[str] = None) -> Path:
    """Find the dataset Excel file."""
    if candidate_path and os.path.exists(candidate_path):
        return Path(candidate_path)
        
    candidates = [
        ROOT / "KINJORDAN_geocoded_verified_LATEST_v2.xlsx",
        ROOT / "KINJORDAN_geocoded_verified_LATEST.xlsx",
        ROOT / "KINJORDAN_geocoded_verified.xlsx",
        Path("C:/Users/waelj/Downloads/KINJORDAN_geocoded_verified_LATEST.xlsx"),
        Path("C:/Users/waelj/Downloads/KINJORDAN_geocoded_verified.xlsx"),
    ]
    for p in candidates:
        if p.exists():
            return p
            
    raise FileNotFoundError(f"Could not locate dataset Excel file in candidate locations: {candidates}")


def load_dataset(file_path: Path, sheet_name: Any = 0) -> pd.DataFrame:
    """Load DataFrame from Excel."""
    logger.info(f"Loading dataset from {file_path} (sheet: {sheet_name})")
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df


def import_kindergartens_dataset(
    file_path: Optional[str] = None,
    sheet_name: Any = 0,
    wipe_existing: bool = False,
    commit: bool = False,
) -> dict[str, Any]:
    """Main function to import kindergartens."""
    target_file = find_excel_file(file_path)
    logger.info(f"Using Excel file: {target_file}")
    
    df = load_dataset(target_file, sheet_name=sheet_name)
    logger.info(f"Total rows in Excel sheet: {len(df)}")
    
    # Filter out empty rows where name_ar is blank
    name_col = "الاسم (عربي)"
    if name_col not in df.columns:
        # Try alternate names
        for col in df.columns:
            if "عربي" in str(col) or "name_ar" in str(col).lower():
                name_col = col
                break
                
    valid_df = df[df[name_col].notna()].copy()
    logger.info(f"Valid kindergarten rows with Arabic name: {len(valid_df)}")
    
    db: Session = SessionLocal()
    report = {
        "source_file": str(target_file),
        "total_sheet_rows": len(df),
        "valid_rows_count": len(valid_df),
        "commit": commit,
        "wipe_existing": wipe_existing,
        "imported_count": 0,
        "governorates_distribution": {},
        "wipe_stats": {},
    }
    
    try:
        if wipe_existing:
            report["wipe_stats"] = wipe_all_kindergartens(db)
            
        imported_count = 0
        gov_dist: dict[str, int] = {}
        
        for idx, row in valid_df.iterrows():
            name_ar = clean_text(row.get("الاسم (عربي)"))
            if not name_ar:
                continue
                
            name_en = clean_text(row.get("الاسم (إنجليزي)")) or None
            kg_type = clean_text(row.get("النوع")) or "خاص"
            gov_raw = row.get("المحافظة")
            governorate = normalize_governorate(gov_raw)
            
            district = clean_text(row.get("اللواء / المدينة")) or governorate
            area = clean_text(row.get("المنطقة")) or district
            
            address_detail = clean_text(row.get("العنوان التفصيلي"))
            address_line = address_detail if address_detail else f"{governorate} - {district} - {area}"
            
            lat = parse_float(row.get("LAT"))
            lng = parse_float(row.get("LONG"))
            
            phone = parse_phone(row.get("الهاتف"))
            owner_name = clean_text(row.get("اسم المالك")) or None
            manager_name = clean_text(row.get("اسم المدير")) or None
            capacity = parse_int(row.get("السعة الإجمالية"))
            
            # Additional metadata in administrative notes
            accuracy = clean_text(row.get("دقة الإحداثيات"))
            source = clean_text(row.get("مصدر الإحداثيات"))
            method = clean_text(row.get("طريقة التحقق"))
            
            notes_parts = []
            if accuracy:
                notes_parts.append(f"Accuracy: {accuracy}")
            if source:
                notes_parts.append(f"Source: {source}")
            if method:
                notes_parts.append(f"Verification: {method}")
            admin_notes = " | ".join(notes_parts) if notes_parts else None
            
            kg = models.Kindergarten(
                name_ar=name_ar,
                name_en=name_en,
                type=kg_type,
                governorate=governorate,
                district=district,
                area=area,
                address_line=address_line,
                latitude=lat,
                longitude=lng,
                contact_phone=phone,
                owner_name=owner_name,
                manager_name=manager_name,
                total_capacity=capacity,
                administrative_notes=admin_notes,
                status=models.KindergartenStatus.ACTIVE,
            )
            db.add(kg)
            imported_count += 1
            gov_dist[governorate] = gov_dist.get(governorate, 0) + 1
            
        report["imported_count"] = imported_count
        report["governorates_distribution"] = gov_dist
        
        if commit:
            db.commit()
            logger.info(f"Successfully committed {imported_count} kindergartens to database.")
        else:
            db.rollback()
            logger.info(f"DRY RUN completed. {imported_count} kindergartens would be imported. (Pass --commit to save)")
            
    except Exception as exc:
        db.rollback()
        logger.error(f"Error during import: {exc}", exc_info=True)
        raise
    finally:
        db.close()
        
    return report


def main():
    parser = argparse.ArgumentParser(description="Import verified geocoded kindergartens from Excel dataset v2.")
    parser.add_argument("--file", "-f", help="Path to Excel dataset file (default: KINJORDAN_geocoded_verified_LATEST.xlsx)", default=None)
    parser.add_argument("--sheet", "-s", help="Sheet name or 0-based index", default="قاعدة البيانات المحدثة (Data)")
    parser.add_argument("--wipe-existing", action="store_true", help="Wipe all existing kindergarten records before importing")
    parser.add_argument("--commit", action="store_true", help="Persist changes to database (without this, dry-run is performed)")
    
    args = parser.parse_args()
    
    sheet_val: Any = args.sheet
    if str(sheet_val).isdigit():
        sheet_val = int(sheet_val)
        
    report = import_kindergartens_dataset(
        file_path=args.file,
        sheet_name=sheet_val,
        wipe_existing=args.wipe_existing,
        commit=args.commit,
    )
    
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY REPORT")
    print("=" * 60)
    print(f"Source file:             {report['source_file']}")
    print(f"Total rows in sheet:     {report['total_sheet_rows']}")
    print(f"Valid kindergarten rows: {report['valid_rows_count']}")
    print(f"Imported records:        {report['imported_count']}")
    print(f"Wipe existing:           {report['wipe_existing']}")
    print(f"Committed to DB:         {report['commit']}")
    print("\nGovernorate breakdown:")
    for gov, count in sorted(report["governorates_distribution"].items(), key=lambda x: -x[1]):
        print(f"  - {gov}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
