"""
Database Migration: Add kindergarten_index Column
==================================================
Reads the indexed CSV output from the indexing pipeline and updates the
SQLite database's `kindergartens` table with the `kindergarten_index` column.

Steps:
    1. Locate kindergartens.db (DATs folder or D:/Final Version)
    2. Add kindergarten_index TEXT UNIQUE column if not present
    3. Create an index on it
    4. Read final_kindergartens_indexed.csv and UPDATE matching rows
    5. Report results

Usage:
    python scripts/add_index_column_migration.py
"""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Force UTF-8 output so Unicode characters (checkmarks etc.) don't crash on
# Windows consoles that default to cp1252.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ── Constants ──────────────────────────────────────────────────────────────────

DB_CANDIDATE_PATHS: List[str] = [
    r"C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\Project-Kinjo-seed\DATS\kindergartens.db",
    r"D:\Final Version\kindergartens.db",
    r"D:\Final Version\data\kinjo.db",
]

CSV_CANDIDATE_PATHS: List[str] = [
    r"D:\Final Version\scripts\final_kindergartens_indexed.csv",
    r"D:\Final Version\final_kindergartens_indexed.csv",
]

MATCH_COLUMNS = ["name_ar", "governorate"]
INDEX_COLUMN = "kindergarten_index"

# Maps Arabic CSV headers → English DB column names.
# The pipeline stores the generated index in the last column (originally
# labeled "رقم الهاتف" / phone number) but repurposes it as the index field.
CSV_TO_DB_COLUMN_MAP: Dict[str, str] = {
    "اسم الحضانة (عربي)": "name_ar",
    "اسم الحضانة (إنجليزي)": "name_en",
    "المحافظة": "governorate",
    "المدينة": "city",
    "المنطقة": "area",
    "العنوان التفصيلي": "address_line",
    "رقم الهاتف": "kindergarten_index",  # pipeline repurposed this col for the index
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg: str) -> None:
    print(f"[{_ts()}] {msg}")


def log_error(msg: str) -> None:
    print(f"[{_ts()}] ERROR: {msg}")


def log_warning(msg: str) -> None:
    print(f"[{_ts()}] WARNING: {msg}")


def find_db() -> Optional[Path]:
    for path_str in DB_CANDIDATE_PATHS:
        p = Path(path_str)
        if p.exists():
            log(f"Database found: {p} ({p.stat().st_size:,} bytes)")
            return p
    # Fallback: search for any .db files in project
    for root_dir in [Path(r"D:\Final Version"), Path.cwd()]:
        if root_dir.is_dir():
            for db_file in root_dir.rglob("*.db"):
                if db_file.exists():
                    log(f"Database found (fallback): {db_file}")
                    return db_file
    return None


def find_csv() -> Optional[Path]:
    for path_str in CSV_CANDIDATE_PATHS:
        p = Path(path_str)
        if p.exists():
            log(f"CSV found: {p}")
            return p
    log_warning("No indexed CSV found. Run kindergarten_indexing_pipeline.py first.")
    return None


def normalize_for_match(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


# ── Migration ──────────────────────────────────────────────────────────────────

def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def run_migration() -> None:
    log("=" * 70)
    log("DATABASE MIGRATION — Add kindergarten_index Column")
    log("=" * 70)

    db_path = find_db()
    if db_path is None:
        log_error("No database found. Exiting.")
        sys.exit(1)

    csv_path = find_csv()
    if csv_path is None:
        log_error("No indexed CSV found. Exiting.")
        sys.exit(1)

    # ── Connect to DB ──────────────────────────────────────────────────────
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    table_name = "kindergartens"

    try:
        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if not cursor.fetchone():
            log_error(f"Table '{table_name}' does not exist in {db_path.name}")
            conn.close()
            sys.exit(1)

        # Check existing columns
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = [row[1] for row in cursor.fetchall()]
        log(f"Table '{table_name}' has {len(existing_columns)} columns: {existing_columns}")

        # Add column if not present
        # SQLite does not support ALTER TABLE ADD COLUMN ... UNIQUE on a table
        # with existing rows. Add the column without the constraint, then create
        # a separate UNIQUE INDEX (which SQLite does support).
        if INDEX_COLUMN not in existing_columns:
            log(f"Adding column '{INDEX_COLUMN}' to {table_name}...")
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {INDEX_COLUMN} TEXT"
            )
            conn.commit()
            log(f"✓ Column '{INDEX_COLUMN}' added")
        else:
            log(f"Column '{INDEX_COLUMN}' already exists — skipping ADD")

        # Create unique index (enforces uniqueness without ALTER TABLE limitation)
        index_name = f"ix_{table_name}_index"
        cursor.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name}({INDEX_COLUMN})"
        )
        conn.commit()
        log(f"✓ Unique index '{index_name}' created/confirmed")

        # ── Read CSV and update ────────────────────────────────────────────
        log(f"\nReading CSV: {csv_path}")
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)

        if not csv_rows:
            log_warning("CSV is empty — nothing to update")
            conn.close()
            return

        log(f"CSV has {len(csv_rows)} rows")

        # Translate Arabic CSV headers → English DB column names and remap rows
        raw_fieldnames = list(reader.fieldnames or csv_rows[0].keys())
        log(f"CSV columns (raw): {raw_fieldnames}")

        translated_fieldnames = [CSV_TO_DB_COLUMN_MAP.get(c, c) for c in raw_fieldnames]
        log(f"CSV columns (mapped): {translated_fieldnames}")

        # Rebuild rows with translated keys
        csv_rows = [
            {CSV_TO_DB_COLUMN_MAP.get(k, k): v for k, v in row.items()}
            for row in csv_rows
        ]
        csv_fieldnames = translated_fieldnames

        # Determine which columns to use for matching
        match_cols = [c for c in MATCH_COLUMNS if c in csv_fieldnames and c in existing_columns]
        if not match_cols:
            log_error(f"No matching columns found. CSV (mapped): {csv_fieldnames}, DB: {existing_columns}")
            conn.close()
            sys.exit(1)

        # The index column is now always INDEX_COLUMN after translation
        index_field = INDEX_COLUMN
        if index_field not in csv_fieldnames:
            log_error(f"Index column '{INDEX_COLUMN}' not found after column mapping. Mapped columns: {csv_fieldnames}")
            conn.close()
            sys.exit(1)

        log(f"Using match columns: {match_cols}")
        log(f"Using index column: {index_field}")

        # Build match set from DB for fast lookup
        log("Building DB match lookup...")
        db_matches: Dict[Tuple[str, ...], int] = {}
        col_list = match_cols + ["id"]
        cursor.execute(f"SELECT {', '.join(col_list)} FROM {table_name}")
        for row in cursor.fetchall():
            key = tuple(normalize_for_match(row[c]) for c in match_cols)
            db_matches[key] = row["id"]

        log(f"DB has {len(db_matches)} existing rows with match columns")

        # Attempt updates
        updated = 0
        not_found = 0
        skipped_empty = 0
        errors = 0

        log("\nUpdating rows from CSV...")
        for i, csv_row in enumerate(csv_rows, start=1):
            index_value = (csv_row.get(index_field) or "").strip()
            if not index_value:
                skipped_empty += 1
                continue

            key = tuple(normalize_for_match(csv_row.get(c)) for c in match_cols)
            db_rowid = db_matches.get(key)

            if db_rowid is None:
                not_found += 1
                if i <= 5 or i % 1000 == 0:
                    log_warning(f"  Row {i}: not found in DB — key=({key})")
                continue

            try:
                cursor.execute("SAVEPOINT sp_row")
                cursor.execute(
                    f"UPDATE {table_name} SET {INDEX_COLUMN} = ? WHERE id = ?",
                    (index_value, db_rowid),
                )
                cursor.execute("RELEASE sp_row")
                updated += 1
                if i % 500 == 0:
                    conn.commit()
                    log(f"  ... {updated} updated so far")
            except Exception as e:
                cursor.execute("ROLLBACK TO sp_row")
                cursor.execute("RELEASE sp_row")
                log_error(f"Row {i}: DB error for key=({key}): {e}")
                errors += 1

        conn.commit()

        total_in_db = cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        indexed_in_db = cursor.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE {INDEX_COLUMN} IS NOT NULL"
        ).fetchone()[0]

        # ── Report ─────────────────────────────────────────────────────────
        print()
        print("=" * 70)
        print("  MIGRATION SUMMARY")
        print("=" * 70)
        print(f"  Database:        {db_path.name}")
        print(f"  CSV rows:        {len(csv_rows)}")
        print(f"  Updated:         {updated}")
        print(f"  Not found in DB: {not_found}")
        print(f"  Skipped (empty): {skipped_empty}")
        print(f"  Errors:          {errors}")
        print(f"  Total in DB:     {total_in_db}")
        print(f"  With index:      {indexed_in_db}")
        print("=" * 70)

    except sqlite3.Error as e:
        conn.rollback()
        log_error(f"SQLite error: {e}")
        raise
    except Exception as e:
        conn.rollback()
        log_error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()
        log("Database connection closed")


def main() -> None:
    try:
        run_migration()
    except KeyboardInterrupt:
        log("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        log_error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()