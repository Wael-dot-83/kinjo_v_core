"""
Seed kindergartens from Excel dataset files.
Reads all .xlsx files in the Dataset folder, deduplicates by Arabic name,
then inserts only records not already present in the database.
"""
import openpyxl
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
import models

DATASET_PATH = r"C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\Dataset"

HEADERS = [
    "اسم الروضة (عربي)",
    "اسم الروضة (إنجليزي)",
    "المحافظة",
    "المدينة",
    "المنطقة",
    "العنوان التفصيلي",
    "رقم الهاتف",
]

# Files to process (most complete/updated first for priority)
PRIORITY_FILES = [
    "روضات_وحضانات_محدث.xlsx",
    "merged_all_uploads.xlsx",
    "_محدث روضات_وحضانات_محدث.xlsx",
]


def collect_from_excel() -> list[dict]:
    """Read all Excel files and return deduplicated list of kindergartens."""
    all_rows: list[dict] = []
    seen: set[str] = set()

    all_files = [f for f in os.listdir(DATASET_PATH) if f.endswith(".xlsx")]
    ordered = PRIORITY_FILES + [f for f in all_files if f not in PRIORITY_FILES]

    for fname in ordered:
        fpath = os.path.join(DATASET_PATH, fname)
        try:
            wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        except Exception as e:
            print(f"  [SKIP] Cannot open {fname}: {e}")
            continue

        for sheet_name in wb.sheetnames:
            if "Summary" in sheet_name or "ورقة" in sheet_name:
                continue
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue

            # Find header row (scan first 3 rows)
            header_row_idx = None
            for i, row in enumerate(rows[:3]):
                if row and any(
                    v and "اسم الروضة" in str(v) for v in row
                ):
                    header_row_idx = i
                    break
            if header_row_idx is None:
                continue

            header = [
                str(v).strip() if v else "" for v in rows[header_row_idx]
            ]

            # Map wanted column names to indices
            col_map: dict[str, int] = {}
            for j, h in enumerate(header):
                for wanted in HEADERS:
                    if wanted in h:
                        col_map[wanted] = j
                        break

            if "اسم الروضة (عربي)" not in col_map:
                print(f"  [SKIP] {fname}::{sheet_name} — cannot map Arabic name column")
                continue

            added_from_sheet = 0
            for row in rows[header_row_idx + 1 :]:
                if not row:
                    continue

                idx_ar = col_map["اسم الروضة (عربي)"]
                raw_ar = row[idx_ar] if idx_ar < len(row) else None
                name_ar = str(raw_ar).strip() if raw_ar and str(raw_ar).strip() != "None" else ""

                if not name_ar or name_ar.startswith("اسم"):
                    continue

                key = name_ar
                if key in seen:
                    continue
                seen.add(key)

                def get_col(col_name: str) -> str:
                    idx = col_map.get(col_name)
                    if idx is None or idx >= len(row):
                        return ""
                    v = row[idx]
                    return str(v).strip() if v and str(v).strip() not in ("None", "") else ""

                all_rows.append(
                    {
                        "name_ar": name_ar,
                        "name_en": get_col("اسم الروضة (إنجليزي)") or None,
                        "governorate": get_col("المحافظة") or "غير محدد",
                        "city": get_col("المدينة") or "غير محدد",
                        "area": get_col("المنطقة") or "غير محدد",
                        "address_line": get_col("العنوان التفصيلي") or "غير محدد",
                        "contact_phone": get_col("رقم الهاتف") or "غير محدد",
                    }
                )
                added_from_sheet += 1

            print(f"  {fname}::{sheet_name} → {added_from_sheet} new unique records")

        wb.close()

    return all_rows


def seed():
    db = SessionLocal()
    try:
        # Get all existing Arabic names (case-sensitive, stripped)
        existing_names: set[str] = {
            row[0].strip()
            for row in db.query(models.Kindergarten.name_ar).all()
            if row[0]
        }
        print(f"\nExisting in DB: {len(existing_names)} kindergartens")

        excel_records = collect_from_excel()
        print(f"\nUnique from Excel: {len(excel_records)} kindergartens")

        to_insert = [r for r in excel_records if r["name_ar"] not in existing_names]
        print(f"New to insert:     {len(to_insert)} kindergartens")

        if not to_insert:
            print("\nNothing to insert — all records already in database.")
            return

        inserted = 0
        skipped = 0
        for rec in to_insert:
            try:
                kg = models.Kindergarten(
                    name_ar=rec["name_ar"],
                    name_en=rec["name_en"],
                    governorate=rec["governorate"],
                    city=rec["city"],
                    area=rec["area"],
                    address_line=rec["address_line"],
                    contact_phone=rec["contact_phone"],
                    contact_email=None,
                    status=models.KindergartenStatus.ACTIVE,
                )
                db.add(kg)
                inserted += 1
            except Exception as e:
                print(f"  [ERROR] Cannot insert '{rec['name_ar']}': {e}")
                skipped += 1

        db.commit()
        print(f"\n✓ Inserted {inserted} new kindergartens ({skipped} errors)")
        total = db.query(models.Kindergarten).count()
        print(f"✓ Total kindergartens in DB now: {total}")

    except Exception as e:
        db.rollback()
        print(f"\n[FATAL] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
