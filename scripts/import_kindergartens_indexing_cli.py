#!/usr/bin/env python3
"""
CLI script for importing kindergartens from Excel.
Integrates with the kindergarten indexing pipeline.

Usage:
    python import_kindergartens.py --path "C:\\path\\to\\final.xlsx"
    python import_kindergartens.py --path "C:\\path\\to\\final.xlsx" --commit
"""
import argparse
import csv
import hashlib
import logging
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("import_kindergartens")

DB_COLUMNS = [
    "id",
    "unique_key",
    "kindergarten_index",
    "name_ar",
    "name_en",
    "governorate",
    "city",
    "area",
    "address_line",
    "contact_phone",
    "contact_email",
    "status",
    "operating_hours_start",
    "operating_hours_end",
    "license_number",
    "license_valid_until",
    "latitude",
    "longitude",
    "manager_name",
    "registration_id",
    "created_at",
    "updated_at",
]

HEADER_ALIASES = {
    "id": "id",
    "kindergarten_id": "id",
    "kg_id": "id",
    "رقم": "id",
    "المعرف": "id",
    "name_ar": "name_ar",
    "arabic_name": "name_ar",
    "kindergarten_name_ar": "name_ar",
    "اسم الروضة": "name_ar",
    "اسم الروضة عربي": "name_ar",
    "اسم الروضة (عربي)": "name_ar",
    "اسم الروضة باللغة العربية": "name_ar",
    "name_en": "name_en",
    "english_name": "name_en",
    "kindergarten_name_en": "name_en",
    "اسم الروضة انجليزي": "name_en",
    "اسم الروضة (إنجليزي)": "name_en",
    "اسم الروضة باللغة الإنجليزية": "name_en",
    "governorate": "governorate",
    "المحافظة": "governorate",
    "city": "city",
    "المدينة": "city",
    "district": "area",
    "area": "area",
    "المنطقة": "area",
    "الحي": "area",
    "address": "address_line",
    "address_line": "address_line",
    "detailed_address": "address_line",
    "العنوان": "address_line",
    "العنوان التفصيلي": "address_line",
    "phone": "contact_phone",
    "contact_phone": "contact_phone",
    "mobile": "contact_phone",
    "telephone": "contact_phone",
    "رقم الهاتف": "contact_phone",
    "الهاتف": "contact_phone",
    "email": "contact_email",
    "contact_email": "contact_email",
    "البريد الإلكتروني": "contact_email",
    "license": "license_number",
    "license_number": "license_number",
    "registration_number": "license_number",
    "رقم الترخيص": "license_number",
    "رقم التسجيل": "license_number",
    "license_valid_until": "license_valid_until",
    "license_expiry": "license_valid_until",
    "تاريخ انتهاء الترخيص": "license_valid_until",
    "status": "status",
    "الحالة": "status",
    "operating_hours_start": "operating_hours_start",
    "وقت بدء الدوام": "operating_hours_start",
    "operating_hours_end": "operating_hours_end",
    "وقت انتهاء الدوام": "operating_hours_end",
    "latitude": "latitude",
    "lat": "latitude",
    "خط العرض": "latitude",
    "longitude": "longitude",
    "lng": "longitude",
    "long": "longitude",
    "خط الطول": "longitude",
    "manager": "manager_name",
    "manager_name": "manager_name",
    "اسم المدير": "manager_name",
    "registration_id": "registration_id",
    "رقم التسجيل": "registration_id",
    "رقم الترخيص": "registration_id",
    "kindergarten index": "kindergarten_index",
    "commercial no": "kindergarten_index",
    "commercial number": "kindergarten_index",
    "رقم تجاري": "kindergarten_index",
    "رقم السجل": "kindergarten_index",
    "registration id": "kindergarten_index",
}

REQUIRED_FIELDS = ["name_ar", "governorate", "city", "contact_phone"]

MISSING_DB_TEXT = "غير محدد"
MISSING_PHONE_TEXT = "غير متوفر"

INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
SPACE_RE = re.compile(r"\s+")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{_ts()}] {msg}")


def log_error(msg: str) -> None:
    print(f"[{_ts()}] ERROR: {msg}")


def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip()
    s = unicodedata.normalize("NFKC", s)
    s = INVISIBLE_RE.sub("", s)
    s = SPACE_RE.sub(" ", s)
    return s.lower()


def normalize_key(s: str | None) -> str:
    if not s:
        return ""
    s = str(s).strip()
    s = unicodedata.normalize("NFKC", s)
    s = INVISIBLE_RE.sub("", s)
    s = SPACE_RE.sub(" ", s)
    s = re.sub(r"[^\w\-\/]", "", s)
    return s.lower()


def clean_identifier(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s)
    s = INVISIBLE_RE.sub("", s)
    s = SPACE_RE.sub(" ", s)
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def is_missing(value: str | None) -> bool:
    if value is None:
        return True
    return normalize_text(value).lower() in {"", "nan", "n/a", "none", "—", "-", "null", "na"}


def resolve_header(raw: str) -> str | None:
    cleaned = SPACE_RE.sub(" ", normalize_text(raw)).strip()
    aliases = {normalize_text(k): v for k, v in HEADER_ALIASES.items()}
    result = aliases.get(cleaned)
    if result:
        return result
    compact = cleaned.replace(" ", "")
    for key, target in aliases.items():
        if compact == key.replace(" ", ""):
            return target
    return None


def create_schema(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS kindergartens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_key TEXT UNIQUE,
            kindergarten_index TEXT,
            name_ar TEXT NOT NULL,
            name_en TEXT,
            governorate TEXT NOT NULL,
            city TEXT NOT NULL,
            area TEXT,
            address_line TEXT,
            contact_phone TEXT,
            contact_email TEXT,
            status TEXT DEFAULT 'ACTIVE',
            operating_hours_start TEXT,
            operating_hours_end TEXT,
            license_number TEXT,
            license_valid_until TEXT,
            latitude REAL,
            longitude REAL,
            manager_name TEXT,
            registration_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_kindergartens_index
        ON kindergartens(kindergarten_index)
        WHERE kindergarten_index IS NOT NULL
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_kindergartens_unique_key
        ON kindergartens(unique_key)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_kindergartens_name_ar
        ON kindergartens(name_ar)
    """)

    conn.commit()
    return conn


def make_unique_key(
    registration_id: str | None,
    kindergarten_index: str | None,
    normalized_name: str | None,
    normalized_address: str | None,
    mapped: dict[str, str | None],
) -> str | None:
    if kindergarten_index:
        return f"index:{normalize_key(kindergarten_index)}"
    if registration_id:
        return f"registration:{normalize_key(registration_id)}"
    if normalized_name and normalized_address:
        combined = f"{normalize_key(normalized_name)}|{normalize_key(normalized_address)}"
        return f"hash:{hashlib.md5(combined.encode()).hexdigest()[:12]}"
    if normalized_name:
        combined = f"{normalize_key(normalized_name)}|{normalize_key(mapped.get('governorate', ''))}|{normalize_key(mapped.get('city', ''))}"
        return f"hash:{hashlib.md5(combined.encode()).hexdigest()[:12]}"
    return None


def find_duplicate(
    conn: sqlite3.Connection,
    registration_id: str | None,
    kindergarten_index: str | None,
    normalized_name: str | None,
    normalized_address: str | None,
    normalized_phone: str | None,
) -> tuple[int, str] | None:
    checks: list[tuple[str, tuple, str, Any]] = []

    if kindergarten_index:
        checks.append((
            "SELECT id, unique_key FROM kindergartens WHERE kindergarten_index = ?",
            (kindergarten_index,),
            "kindergarten_index",
            kindergarten_index,
        ))

    if registration_id:
        checks.append((
            "SELECT id, unique_key FROM kindergartens WHERE registration_id = ?",
            (registration_id,),
            "registration_id",
            registration_id,
        ))
    if normalized_name and normalized_phone:
        checks.append((
            "SELECT id, unique_key FROM kindergartens WHERE name_ar = ? AND contact_phone = ?",
            (normalized_name, normalized_phone),
            "name_ar + contact_phone",
            f"{normalized_name} / {normalized_phone}",
        ))
    if normalized_name and normalized_address:
        checks.append((
            "SELECT id, unique_key FROM kindergartens WHERE name_ar = ? AND address_line = ?",
            (normalized_name, normalized_address),
            "name_ar + address_line",
            f"{normalized_name} / {normalized_address}",
        ))

    for query, params, check_name, check_value in checks:
        row = conn.execute(query, params).fetchone()
        if row:
            return int(row[0]), str(row[1])

    return None


def import_files(
    db_path: str,
    file_paths: list[str],
    commit: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    conn = create_schema(db_path)
    total_inserted = 0
    total_updated = 0
    total_skipped = 0
    total_errors = 0
    all_errors: list[dict[str, Any]] = []

    for file_path in file_paths:
        log(f"Processing: {file_path}")

        if not os.path.exists(file_path):
            log_error(f"File not found: {file_path}")
            total_errors += 1
            all_errors.append({"file": file_path, "error": "File not found"})
            continue

        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            rows = _read_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            rows = _read_excel(file_path)
        else:
            log_error(f"Unsupported file format: {ext}")
            total_errors += 1
            all_errors.append({"file": file_path, "error": f"Unsupported format: {ext}"})
            continue

        if not rows:
            log(f"  No data rows found — skipped")
            total_skipped += 1
            continue

        if verbose:
            log(f"  {len(rows)} rows loaded")

        for i, row in enumerate(rows, start=1):
            mapped = _map_row_to_columns(row)
            if mapped is None:
                total_skipped += 1
                continue

            name_ar = normalize_text(mapped.get("name_ar"))
            if not name_ar:
                if verbose:
                    log(f"  Row {i}: skipped — missing name_ar")
                total_skipped += 1
                continue

            address = normalize_text(mapped.get("address_line"))
            phone = normalize_text(mapped.get("contact_phone"))

            registration_id = clean_identifier(mapped.get("registration_id"))
            kindergarten_index = clean_identifier(mapped.get("kindergarten_index"))

            unique_key = make_unique_key(
                registration_id, kindergarten_index, name_ar, address, mapped
            )

            if not unique_key:
                if verbose:
                    log(f"  Row {i}: skipped — could not generate unique_key")
                total_skipped += 1
                continue

            dup = find_duplicate(
                conn, registration_id, kindergarten_index, name_ar, address, phone
            )

            mapped.update({
                "unique_key": unique_key,
                "registration_id": registration_id,
                "kindergarten_index": kindergarten_index,
            })

            if dup:
                existing_id, existing_key = dup
                if commit:
                    _update_row(conn, existing_id, mapped)
                total_updated += 1
                if verbose:
                    log(f"  Row {i}: UPDATE id={existing_id}")
            else:
                if commit:
                    _insert_row(conn, mapped)
                total_inserted += 1
                if verbose:
                    log(f"  Row {i}: INSERT key={unique_key}")

    if commit:
        log("Changes committed to database")
    else:
        conn.rollback()
        log("Dry-run: no changes committed")

    conn.close()

    return {
        "inserted": total_inserted,
        "updated": total_updated,
        "skipped": total_skipped,
        "errors": total_errors,
        "error_details": all_errors,
    }


def _read_csv(file_path: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k.strip(): v.strip() for k, v in r.items()})
    return rows


def _read_excel(file_path: str) -> list[dict[str, str]]:
    import pandas as pd
    df = pd.read_excel(file_path, sheet_name=0, header=0, dtype=str)
    df = df.fillna("")
    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        rows.append({str(k).strip(): str(v).strip() for k, v in row.to_dict().items()})
    return rows


def _map_row_to_columns(row: dict[str, str]) -> dict[str, str | None] | None:
    mapped: dict[str, str | None] = {}
    seen: set[str] = set()

    for raw_key, raw_value in row.items():
        field = resolve_header(raw_key)
        if field and field not in seen:
            val = raw_value.strip() if raw_value and raw_value.lower() not in {"nan", "n/a", "none", "null", "na", "—", "-", ""} else None
            mapped[field] = val
            seen.add(field)

    return mapped


def _insert_row(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    cols = [c for c in DB_COLUMNS if c != "id" and c in data and data.get(c) is not None]
    placeholders = ", ".join(f"?:{c}" for c in cols)
    names = ", ".join(cols)
    values = [data[c] for c in cols]

    conn.execute(
        f"INSERT INTO kindergartens ({names}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _update_row(conn: sqlite3.Connection, row_id: int, data: dict[str, Any]) -> None:
    cols = [c for c in DB_COLUMNS if c != "id" and c in data and data.get(c) is not None]
    sets = ", ".join(f"{c} = ?" for c in cols)
    values = [data[c] for c in cols] + [row_id]

    conn.execute(
        f"UPDATE kindergartens SET {sets}, updated_at = datetime('now') WHERE id = ?",
        values,
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Import kindergartens from Excel/CSV files")
    parser.add_argument("--path", required=True, help="Path to Excel or CSV file (or directory of files)")
    parser.add_argument("--db", default="kindergartens.db", help="Path to SQLite database")
    parser.add_argument("--commit", action="store_true", help="Apply changes to database (default: dry-run)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    path = args.path
    if not os.path.exists(path):
        log_error(f"Path not found: {path}")
        sys.exit(1)

    if os.path.isdir(path):
        files = sorted(
            [str(p) for p in Path(path).glob("*") if p.suffix.lower() in (".csv", ".xlsx", ".xls")]
        )
        if not files:
            log_error(f"No CSV or Excel files found in directory: {path}")
            sys.exit(1)
        log(f"Found {len(files)} files in directory: {path}")
    else:
        files = [path]

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    result = import_files(
        db_path=args.db,
        file_paths=files,
        commit=args.commit,
        verbose=args.verbose,
    )

    print()
    print("=" * 50)
    print("  IMPORT SUMMARY")
    print("=" * 50)
    print(f"  Mode:             {'COMMIT' if args.commit else 'DRY-RUN'}")
    print(f"  Database:         {args.db}")
    print(f"  Files processed:  {len(files)}")
    print(f"  Inserted:         {result['inserted']}")
    print(f"  Updated:          {result['updated']}")
    print(f"  Skipped:          {result['skipped']}")
    print(f"  Errors:           {result['errors']}")
    if result["error_details"]:
        for e in result["error_details"]:
            print(f"    - {e['file']}: {e['error']}")
    print("=" * 50)


if __name__ == "__main__":
    main()