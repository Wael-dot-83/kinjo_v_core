"""Import kindergartens from a CSV into the database.

Features:
- Dry-run by default; pass --commit to apply changes
- Idempotent upsert: match existing records by normalized (name_ar, city, area)
- Update existing records with non-empty CSV values, or insert new records
- Validates required columns and phone format (Jordan pattern)
- Produces a summary and optional backup of affected records
"""
from __future__ import annotations
import argparse
import csv
import logging
import sys
import os
from datetime import datetime
import re
import unicodedata
from pathlib import Path
from typing import Dict, Optional, Tuple, List

# Add the project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import SessionLocal
import models
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_kindergartens")

REQUIRED_COLUMNS = [
    "name_ar",
    "governorate",
    "city",
    "area",
    "address_line",
    "contact_phone",
]

# Mapping for Arabic column names to English
COLUMN_MAPPING = {
    "اسم الروضة (عربي)": "name_ar",
    "اسم الروضة (إنجليزي)": "name_en",
    "المحافظة": "governorate",
    "المدينة": "city",
    "المنطقة": "area",
    "العنوان التفصيلي": "address_line",
    "رقم الهاتف": "contact_phone",
}

PHONE_RE = re.compile(settings.JORDAN_PHONE_PATTERN)


def normalize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.strip()
    s = unicodedata.normalize("NFKC", s)
    # collapse whitespace
    s = " ".join(s.split())
    return s.lower()


def normalize_phone(ph: Optional[str]) -> Optional[str]:
    if not ph:
        return None
    ph = ph.strip().replace(" ", "").replace("-", "")
    if PHONE_RE.match(ph):
        return ph
    # try to prepend 0 if missing and looks local
    if ph.isdigit() and len(ph) == 9:
        ph = "0" + ph
        if PHONE_RE.match(ph):
            return ph
    return ph  # return raw if we can't validate


def read_csv(path: str) -> Tuple[List[Dict[str, str]], List[str]]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        for r in reader:
            # Apply column mapping
            mapped_row = {}
            for k, v in r.items():
                mapped_key = COLUMN_MAPPING.get(k, k)  # Use mapped key if exists, else original
                mapped_row[mapped_key] = v
            rows.append(mapped_row)
    return rows, headers


def find_existing(session, name_ar: str, city: str, area: str) -> Optional[models.Kindergarten]:
    n_name = normalize_text(name_ar)
    n_city = normalize_text(city)
    n_area = normalize_text(area)
    # Match by lower(trim(name_ar)) and city and area
    q = session.query(models.Kindergarten).filter(
        models.Kindergarten.name_ar != None,
        models.Kindergarten.district != None,
        models.Kindergarten.area != None,
        (models.Kindergarten.name_ar.ilike(n_name)) | (models.Kindergarten.name_en.ilike(n_name))
    ).filter(
        models.Kindergarten.district.ilike(n_city),
        models.Kindergarten.area.ilike(n_area)
    )
    # Return first exact-ish match
    return q.first()


def build_payload(row: Dict[str, str]) -> Dict:
    payload = {}
    for k in [
        "name_ar",
        "name_en",
        "governorate",
        "city",
        "area",
        "address_line",
        "contact_phone",
        "contact_email",
        "license_number",
        "license_valid_until",
    ]:
        val = row.get(k) if k in row else None
        if isinstance(val, str):
            val = val.strip() or None
        payload[k] = val
    # normalize phone
    payload["contact_phone"] = normalize_phone(payload.get("contact_phone"))
    # parse date
    if payload.get("license_valid_until"):
        try:
            payload["license_valid_until"] = datetime.fromisoformat(payload["license_valid_until"]).date()
        except (ValueError, TypeError):
            # leave as None and warn
            logger.warning("Invalid date for license_valid_until: %s", payload.get("license_valid_until"))
            payload["license_valid_until"] = None
    # Set default for missing address_line
    if not payload.get("address_line"):
        payload["address_line"] = "Not provided"
    return payload


def import_file(path: str, commit: bool = False, default_status: str = "ACTIVE", backup: Optional[str] = None, verbose: bool = False) -> Dict:
    rows, headers = read_csv(path)
    # Check if required columns are present after mapping
    if rows:
        sample_row = rows[0]
        missing = [c for c in REQUIRED_COLUMNS if c not in sample_row]
        if missing:
            raise SystemExit(f"CSV is missing required columns after mapping: {missing}")
    else:
        raise SystemExit("CSV file is empty")

    session = SessionLocal()
    inserted = 0
    updated = 0
    skipped = 0
    updates: List[Tuple[int, Dict]] = []
    inserts: List[Dict] = []
    affected_existing_records = []

    for i, row in enumerate(rows, start=1):
        payload = build_payload(row)
        if not payload.get("name_ar"):
            logger.warning("Skipping row %d: missing name_ar", i)
            skipped += 1
            continue
        existing = find_existing(session, payload["name_ar"], payload["city"], payload["area"])
        if existing:
            # Prepare update: only set fields that are non-empty in CSV and different
            changed = {}
            for k, v in payload.items():
                if k == "name_ar":
                    continue
                if v is not None and getattr(existing, k, None) != v:
                    setattr(existing, k, v)
                    changed[k] = v
            # status if provided
            if default_status and existing.status != getattr(models.KindergartenStatus, default_status):
                try:
                    existing.status = models.KindergartenStatus(default_status)
                    changed["status"] = default_status
                except (ValueError, TypeError, AttributeError):
                    pass
            if changed:
                updates.append((existing.id, changed))
                affected_existing_records.append(existing)
                updated += 1
                if verbose:
                    logger.info("Row %d -> UPDATE id=%s changes=%s", i, existing.id, changed)
            else:
                skipped += 1
                if verbose:
                    logger.debug("Row %d -> SKIP (no changes detected for existing id=%s)", i, existing.id)
        else:
            kg = models.Kindergarten(
                name_ar=payload.get("name_ar"),
                name_en=payload.get("name_en"),
                governorate=payload.get("governorate"),
                city=payload.get("city"),
                area=payload.get("area"),
                address_line=payload.get("address_line"),
                contact_phone=payload.get("contact_phone"),
                contact_email=payload.get("contact_email"),
                license_number=payload.get("license_number"),
                license_valid_until=payload.get("license_valid_until"),
                status=models.KindergartenStatus(default_status)
            )
            session.add(kg)
            inserts.append(payload)
            inserted += 1
            if verbose:
                logger.info("Row %d -> INSERT name_ar=%s city=%s area=%s", i, payload.get("name_ar"), payload.get("city"), payload.get("area"))

    summary = {
        "rows": len(rows),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }

    logger.info("Summary (dry-run=%s): %s", not commit, summary)

    if verbose:
        # Provide short previews of planned changes
        if inserts:
            logger.info("Planned inserts: %d. Example rows: %s", len(inserts), inserts[:5])
        if updates:
            logger.info("Planned updates: %d. Example (id, changes): %s", len(updates), updates[:5])

    if backup and affected_existing_records and commit:
        # Export affected existing records to CSV as backup
        bpath = Path(backup)
        logger.info("Writing backup of %d existing records to %s", len(affected_existing_records), bpath)
        with bpath.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "name_ar", "name_en", "governorate", "city", "area", "address_line", "contact_phone", "contact_email", "license_number", "license_valid_until", "status"])
            for r in affected_existing_records:
                w.writerow([
                    r.id, r.name_ar, r.name_en, r.governorate, r.district, r.area, r.address_line, r.contact_phone, r.contact_email, r.license_number, r.license_valid_until, getattr(r.status, "value", None)
                ])

    if commit:
        try:
            session.commit()
            logger.info("Changes committed to database")
        except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
            session.rollback()
            logger.error("Failed to commit changes: %s", exc)
            raise
    else:
        session.rollback()  # don't persist in dry-run

    session.close()

    return summary


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="Import kindergartens from CSV into KinJo DB")
    parser.add_argument("--file", "-f", required=True, help="Path to CSV file")
    parser.add_argument("--commit", action="store_true", help="Apply changes to database (default: dry-run)")
    parser.add_argument("--status", choices=[s.name for s in models.KindergartenStatus], default="ACTIVE", help="Status for new records (default: ACTIVE)")
    parser.add_argument("--backup", help="If provided and --commit, backup affected existing records to path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output: list inserts/updates and per-row info")
    args = parser.parse_args(argv)

    path = args.file
    if not Path(path).exists():
        logger.error("File not found: %s", path)
        sys.exit(2)

    try:
        summary = import_file(path, commit=args.commit, default_status=args.status, backup=args.backup, verbose=args.verbose)
        logger.info("Import finished: %s", summary)
    except SystemExit as e:
        logger.error("Import aborted: %s", e)
        sys.exit(1)
    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as exc:
        logger.exception("Unexpected error during import: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
